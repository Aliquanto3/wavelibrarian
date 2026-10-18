"""Lecture des fichiers d'une Exécution (contracts.md §5, §7) : le Rapport ne lit rien d'autre.

`report` ne dépend pas de `runner` (AD-1) : ces lecteurs refont ceux de `runner/rundir.py`. Comme
eux, la dernière ligne d'une clé fait foi (reprise, story 4.8) ; une dernière ligne tronquée par un
arrêt brutal est ignorée (story 4.11). `budget_exceeded` n'est jamais noté ni compté en erreur.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from wavelibrarian.config.experiment import ResolvedExperiment
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.jsonl import lire_jsonl
from wavelibrarian.core.types import Answer, Question
from wavelibrarian.evalset import io
from wavelibrarian.scoring.panel import PanelVerdict

CleGroupe = tuple[str, str, int | None, str]  # (config_id, condition, tier, phase)


def groupe_de(a: Answer) -> CleGroupe:
    return (a.config_id, a.condition, a.tier, a.phase)


def lire_json(chemin: Path) -> Any:
    """Objet JSON du fichier, ou `None` s'il est absent ou illisible."""
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def lire_reponses(run_dir: Path) -> dict[str, Answer]:
    """Réponses effectives par `answer_id` (la dernière ligne d'une clé fait foi)."""
    effectives: dict[str, Answer] = {}
    for objet in lire_jsonl(run_dir / "answers.jsonl"):
        a = Answer.model_validate(objet)
        effectives[a.answer_id] = a
    return effectives


def lire_panel(run_dir: Path) -> dict[tuple[str, str], PanelVerdict]:
    """Verdicts agrégés par (answer_id, criterion) ; la dernière ligne d'une clé fait foi."""
    effectifs: dict[tuple[str, str], PanelVerdict] = {}
    for objet in lire_jsonl(run_dir / "panel.jsonl"):
        v = PanelVerdict.model_validate(objet)
        effectifs[(v.answer_id, v.criterion)] = v
    return effectifs


def lire_resolue(run_dir: Path) -> ResolvedExperiment:
    chemin = run_dir / "experiment.resolved.yaml"
    try:
        return ResolvedExperiment.model_validate(yaml.safe_load(chemin.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise ConfigError(str(chemin), f"Expérience résolue illisible : {exc}") from exc


def lire_jeu(experience: ResolvedExperiment) -> dict[str, Question]:
    """Questions du Jeu par id (type, contamination, Ancrages de référence). Le Rapport n'en tire
    que ce que le contrat §7 lui demande ; les Réponses viennent d'`answers.jsonl`."""
    return {q.id: q for q in io.load(Path(experience.questions)).questions}


@dataclass
class Execution:
    """Tout ce que le Rapport lit d'une Exécution."""

    run_dir: Path
    experience: ResolvedExperiment
    manifeste: dict[str, Any]
    empreinte: str
    reponses: dict[str, Answer]
    panel: dict[tuple[str, str], PanelVerdict]
    jeu: dict[str, Question]
    profil_corpus: dict[str, Any] | None
    inapplicables: dict[str, Any]
    verdicts_par_reponse: dict[str, dict[str, PanelVerdict]] = field(default_factory=dict)


def charger(run_dir: Path) -> Execution:
    """Charge les fichiers de l'Exécution ; `ConfigError` si l'Expérience résolue ou le Jeu
    manquent."""
    experience = lire_resolue(run_dir)
    try:
        jeu = lire_jeu(experience)
    except ConfigError:
        raise
    except OSError as exc:
        raise ConfigError("questions", f"Jeu illisible : {exc}") from exc
    panel = lire_panel(run_dir)
    par_reponse: dict[str, dict[str, PanelVerdict]] = {}
    for (aid, critere), v in panel.items():
        par_reponse.setdefault(aid, {})[critere] = v
    empreinte_chemin = run_dir / "experiment.sha256"
    empreinte = (
        empreinte_chemin.read_text(encoding="utf-8").strip() if empreinte_chemin.is_file() else ""
    )
    inapplicables = lire_json(run_dir / "applicability.json")
    return Execution(
        run_dir=run_dir,
        experience=experience,
        manifeste=lire_json(run_dir / "manifest.json") or {},
        empreinte=empreinte,
        reponses=lire_reponses(run_dir),
        panel=panel,
        jeu=jeu,
        profil_corpus=lire_json(run_dir / "corpus_profile.json"),
        inapplicables=inapplicables if isinstance(inapplicables, dict) else {},
        verdicts_par_reponse=par_reponse,
    )
