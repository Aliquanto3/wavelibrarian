"""Reprise d'une Exécution (`wl run --reprendre <run_id>`, contracts.md §7, AD-9, AD-11).

La reprise relit le dossier `runs/<run_id>/` : elle ne refait que les clés absentes de
`answers.jsonl`, sans jamais réécrire `traces.jsonl`. Ce module contient les contrôles qui
précèdent tout appel (code 2) et la lecture des traces d'une Question interrompue.
"""

import json
from pathlib import Path

import yaml

from wavelibrarian.config.experiment import ResolvedExperiment
from wavelibrarian.config.resolve import fingerprint
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.corpus.declare import declare
from wavelibrarian.runner.rundir import resolve_parsers

# (config_id, condition, tier, phase, question_id) : la clé d'un `Answer` sans le run_id.
Cle = tuple[str, str, int | None, str, str]


def dossier_de(wl_home: Path, run_id: str) -> Path:
    return wl_home / "runs" / run_id


def charger_resolue(dossier: Path) -> ResolvedExperiment:
    """Relit `experiment.resolved.yaml` comme `ResolvedExperiment` (le parser composite
    `markdown+pdf_text` y est un nom de `ComponentSpec` comme un autre)."""
    chemin = dossier / "experiment.resolved.yaml"
    try:
        donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        return ResolvedExperiment.model_validate(donnees)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise ConfigError(str(chemin), f"Expérience résolue illisible : {exc}") from exc


def verifier_reprise(
    experience: ResolvedExperiment, wl_home: Path, run_id: str, freeze_sha256: str
) -> Path:
    """Contrôles d'une reprise, sans verrou ni appel ; `ConfigError` (code 2) sinon. Rend le
    dossier de l'Exécution.

    L'empreinte compare l'Expérience demandée à `experiment.sha256` **à plafonds égaux** : relever
    le plafond est justement la raison d'une reprise après `budget_exceeded` (AC 2 de la 4.8),
    alors que `budget` fait partie de l'empreinte écrite au départ (config/resolve.py). Tout
    autre écart (Configuration, graine, modèles, Corpus, Questions…) est refusé. L'empreinte du
    Gel du Jeu doit aussi être celle du manifeste.
    """
    dossier = dossier_de(wl_home, run_id)
    try:
        manifeste = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError("reprendre", f"Exécution {run_id} introuvable ou illisible") from exc
    if manifeste.get("status") == "completed":
        raise ConfigError("reprendre", f"Exécution {run_id} déjà terminée : rien à reprendre")
    if manifeste.get("freeze_sha256") != freeze_sha256:
        raise ConfigError(
            "reprendre", f"le Jeu de Questions n'est plus celui de l'Exécution {run_id} (Gel)"
        )
    stockee = charger_resolue(dossier)
    attendue = (dossier / "experiment.sha256").read_text(encoding="utf-8").strip()
    resolue = resolve_parsers(experience, declare(Path(experience.corpus)))
    if fingerprint(resolue.model_copy(update={"budget": stockee.budget})) != attendue:
        raise ConfigError(
            "reprendre",
            f"l'Expérience diffère de celle de l'Exécution {run_id} "
            "(empreinte différente de experiment.sha256, plafonds exceptés)",
        )
    return dossier


def cles_tracees(dossier: Path) -> set[Cle]:
    """Clés des Questions qui ont déjà au moins un span du Poste `query` dans `traces.jsonl`."""
    chemin = dossier / "traces.jsonl"
    if not chemin.is_file():
        return set()
    cles: set[Cle] = set()
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if not ligne.strip():
            continue
        span = json.loads(ligne)
        if span.get("wl.post") != "query" or not span.get("wl.question_id"):
            continue
        tier = span.get("wl.tier")
        cles.add(
            (
                span["wl.config_id"],
                span["wl.condition"],
                tier if isinstance(tier, int) else None,
                span["wl.phase"],
                span["wl.question_id"],
            )
        )
    return cles
