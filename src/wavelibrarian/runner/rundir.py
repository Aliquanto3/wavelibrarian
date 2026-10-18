"""Dossier d'Exécution `runs/<run_id>/` (contracts.md §5, AD-11).

Le runner écrit l'Expérience résolue, son empreinte et `manifest.json` avant tout appel, puis
ouvre les JSONL en ajout seulement. Seul le runner écrit dans ces fichiers (`traces.jsonl` est
celui du Tracer).
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, get_args

from wavelibrarian.config.experiment import Budget, ResolvedExperiment
from wavelibrarian.config.resolve import write_resolved
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.ids import canonical_json
from wavelibrarian.core.types import Answer
from wavelibrarian.corpus.declare import DeclaredCorpus
from wavelibrarian.corpus.ingest import nom_parser_resolu, parsers_par_format
from wavelibrarian.llm.gateway import limiter_journaux
from wavelibrarian.ports.components import ComponentSpec

Status = Literal["running", "completed", "budget_exceeded", "failed"]
JsonlName = Literal["answers.jsonl", "verdicts.jsonl", "panel.jsonl"]
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
RUN_ID = _RUN_ID  # forme d'un run_id, aussi contrôlée par `--reprendre`
_SHA256 = re.compile(r"[0-9a-f]{64}")


def resolve_parsers(experience: ResolvedExperiment, corpus: DeclaredCorpus) -> ResolvedExperiment:
    """Remplace chaque `parser: auto` par le nom concret lu sur les formats du Corpus
    (`markdown`, `text`, `html`, `pdf_text`, ou `markdown+pdf_text` si plusieurs), la forme de
    `CorpusProfile.parser`. À appeler avant `write_resolved` et `RunContext.parser`."""
    configurations = tuple(
        c.model_copy(
            update={
                "parser": ComponentSpec(
                    name=nom_parser_resolu(parsers_par_format(corpus.formats, c.parser.name))
                )
            }
        )
        if c.parser.name == "auto"
        else c
        for c in experience.configurations
    )
    return experience.model_copy(update={"configurations": configurations})


def _modeles(experience: ResolvedExperiment) -> list[str]:
    vus: list[str] = []
    sources = [m for c in experience.configurations for m in c.models]
    sources += list(experience.judges.pool or ())
    for m in sources:
        if m not in vus:
            vus.append(m)
    return vus


def _ecrire_manifest(dossier: Path, donnees: dict[str, Any]) -> None:
    tmp = dossier / "manifest.json.tmp"
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(dossier / "manifest.json")


def create_run_dir(
    wl_home: Path,
    run_id: str,
    experience: ResolvedExperiment,
    *,
    freeze_sha256: str,
    inputs: dict[str, str] | None = None,
) -> Path:
    """Crée `runs/<run_id>/` avec `experiment.resolved.yaml`, `experiment.sha256` et
    `manifest.json` (`status: running`, empreinte du Gel `freeze_sha256` exigée par §5) ;
    refuse un dossier `runs/<run_id>/` existant non vide, une empreinte du Gel qui n'est pas un
    sha256 hexadécimal, ou une Expérience dont un parser est encore `auto`."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError(f"run_id invalide : {run_id!r} (lettres, chiffres, - et _)")
    dossier = wl_home / "runs" / run_id
    if dossier.exists() and (not dossier.is_dir() or any(dossier.iterdir())):
        raise WlError(f"Exécution {run_id} déjà initialisée (reprise : --reprendre)")
    if not _SHA256.fullmatch(freeze_sha256):
        raise ValueError(f"freeze_sha256 invalide : {freeze_sha256!r} (sha256 hexadécimal)")
    if any(c.parser.name == "auto" for c in experience.configurations):
        raise WlError("parser « auto » non résolu : appeler resolve_parsers avant create_run_dir")
    empreinte = write_resolved(experience, dossier)
    _ecrire_manifest(
        dossier,
        {
            "run_id": run_id,
            "experiment_id": experience.experiment_id,
            "status": "running",
            "profile": experience.profile,
            "models_frozen_at": experience.models_frozen_at.isoformat(),
            "models": _modeles(experience),
            "experiment_sha256": empreinte,
            "freeze_sha256": freeze_sha256,
            **({} if inputs is None else {"inputs": inputs}),
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    return dossier


def set_status(dossier: Path, status: Status, *, answers: dict[str, int] | None = None) -> None:
    """Met à jour `status` du manifeste (fin d'Exécution) ; `answers` : décompte des Réponses
    par statut (`ok`, `error`, `inapplicable`), pour que les erreurs se voient au manifeste."""
    chemin = dossier / "manifest.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    donnees["status"] = status
    if answers is not None:
        donnees["answers"] = answers
    if status != "running":
        donnees["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    _ecrire_manifest(dossier, donnees)


def reopen_run_dir(dossier: Path, budget: Budget) -> None:
    """Reprise (contracts.md §7) : le manifeste repasse à `running`, sans `finished_at` ; la
    reprise est consignée dans `resumptions` avec les plafonds en vigueur. Les fichiers
    `experiment.resolved.yaml` et `experiment.sha256` restent ceux du départ."""
    chemin = dossier / "manifest.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    donnees["status"] = "running"
    donnees.pop("finished_at", None)
    donnees.pop("answers", None)
    reprises = donnees.setdefault("resumptions", [])
    reprises.append(
        {
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "budget": budget.model_dump(mode="json"),
        }
    )
    _ecrire_manifest(dossier, donnees)


def read_answers(dossier: Path) -> dict[str, Answer]:
    """Réponses effectives de `answers.jsonl`, par `answer_id` : la dernière ligne d'une clé fait
    foi. Le fichier est en ajout seulement : une Question restée `budget_exceeded` est reposée à
    la reprise, et sa nouvelle ligne remplace la précédente."""
    chemin = dossier / "answers.jsonl"
    if not chemin.is_file():
        return {}
    effectives: dict[str, Answer] = {}
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if ligne.strip():
            reponse = Answer.model_validate(json.loads(ligne))
            effectives[reponse.answer_id] = reponse
    return effectives


def attach_run_log(dossier: Path) -> logging.Handler:
    """Ajoute à la racine un handler vers `run.log` (UTF-8, LF) et limite les journaux réseau.
    L'appelant le retire avec `detach_run_log`."""
    handler = logging.FileHandler(dossier / "run.log", mode="a", encoding="utf-8", delay=False)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s : %(message)s"))
    limiter_journaux(handler)
    logging.getLogger().addHandler(handler)
    return handler


def detach_run_log(handler: logging.Handler) -> None:
    logging.getLogger().removeHandler(handler)
    handler.close()


class JsonlWriter:
    """JSONL en ajout seulement, UTF-8 et LF ; une ligne = un objet JSON canonique, vidée sur
    disque. Aucune méthode ne relit ni ne réécrit."""

    def __init__(self, dossier: Path, name: JsonlName) -> None:
        if name not in get_args(JsonlName):
            raise ValueError(f"{name} n'est pas un fichier écrit par le runner")
        self.path = dossier / name
        self._f = open(self.path, "a", encoding="utf-8", newline="\n")  # noqa: SIM115

    def append(self, obj: Any) -> None:
        self._f.write(canonical_json(obj) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "JsonlWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
