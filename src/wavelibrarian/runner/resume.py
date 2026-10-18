"""Reprise d'une Exécution (`wl run --reprendre <run_id>`, contracts.md §7, AD-9, AD-11).

La reprise relit le dossier `runs/<run_id>/` : elle ne refait que les clés absentes de
`answers.jsonl`, sans jamais réécrire `traces.jsonl`. Ce module contient les contrôles qui
précèdent tout appel (code 2) et la lecture des traces d'une Question interrompue.
"""

import json
from pathlib import Path

import yaml

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.experiment import ResolvedExperiment
from wavelibrarian.config.resolve import fingerprint
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import canonical_json, sha16
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.corpus.scenario import corpus_apres
from wavelibrarian.runner.rundir import RUN_ID, resolve_parsers

# (config_id, condition, tier, phase, question_id) : la clé d'un `Answer` sans le run_id.
Cle = tuple[str, str, int | None, str, str]


# Libellés des empreintes d'entrée du manifeste (`inputs`), pour le message de refus.
_ENTREES = {
    "corpus_fingerprint": "le Corpus",
    "scenario_fingerprint": "le Scénario",
    "catalog_fingerprint": "le Catalogue de modèles",
}


def dossier_de(wl_home: Path, run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):  # `--reprendre ../x` : jamais hors de runs/
        raise ConfigError("reprendre", f"run_id invalide : {run_id!r} (lettres, chiffres, - et _)")
    return wl_home / "runs" / run_id


def empreintes_entrees(experience: ResolvedExperiment, wl_home: Path) -> dict[str, str]:
    """Empreintes du contenu que l'empreinte de l'Expérience ne couvre pas (elle ne porte que
    les chemins) : Corpus ingéré, Corpus après Scénario, Catalogue de modèles (tarifs compris).
    Écrites au manifeste (`inputs`) au départ, comparées à la reprise. `experience` a ses
    parsers résolus (`resolve_parsers`)."""
    parser = experience.configurations[0].parser.name
    parse = ingest(declare(Path(experience.corpus)), parser, wl_home=wl_home)
    catalogue = load_catalog(Path(experience.catalog) if experience.catalog else None)
    entrees = {
        "corpus_fingerprint": parse.fingerprint,
        "catalog_fingerprint": sha16(canonical_json(catalogue.model_dump(mode="json"))),
    }
    if experience.scenario:
        apres = corpus_apres(parse, Path(experience.scenario), parser=parser)
        entrees["scenario_fingerprint"] = apres.fingerprint
    return entrees


def lire_manifeste(wl_home: Path, run_id: str) -> dict[str, object]:
    dossier = dossier_de(wl_home, run_id)
    try:
        return json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError("reprendre", f"Exécution {run_id} introuvable ou illisible") from exc


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
    manifeste = lire_manifeste(wl_home, run_id)
    if manifeste.get("freeze_sha256") != freeze_sha256:
        raise ConfigError(
            "reprendre", f"le Jeu de Questions n'est plus celui de l'Exécution {run_id} (Gel)"
        )
    stockee = charger_resolue(dossier)
    try:
        attendue = (dossier / "experiment.sha256").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError("reprendre", f"experiment.sha256 illisible : {exc}") from exc
    resolue = resolve_parsers(experience, declare(Path(experience.corpus)))
    if fingerprint(resolue.model_copy(update={"budget": stockee.budget})) != attendue:
        raise ConfigError(
            "reprendre",
            f"l'Expérience diffère de celle de l'Exécution {run_id} "
            "(empreinte différente de experiment.sha256, plafonds exceptés)",
        )
    stockees = manifeste.get("inputs")
    if isinstance(stockees, dict):  # contenu du Corpus, du Scénario et du Catalogue
        actuelles = empreintes_entrees(resolue, wl_home)
        for cle in sorted(set(stockees) | set(actuelles)):
            if stockees.get(cle) != actuelles.get(cle):
                quoi = _ENTREES.get(cle, cle)
                raise ConfigError(
                    "reprendre", f"{quoi} n'est plus celui de l'Exécution {run_id} ({cle})"
                )
    return dossier


def deja_terminee(wl_home: Path, run_id: str) -> bool:
    """Exécution `completed` : une reprise n'a rien à refaire (code 0 dans la CLI)."""
    return lire_manifeste(wl_home, run_id).get("status") == "completed"


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
