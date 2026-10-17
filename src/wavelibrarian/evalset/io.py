"""Lecture et écriture de `questions.yaml` (contracts §4.5), ordre préservé (FR-9, AD-12)."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from wavelibrarian.config.defaults import charger_yaml
from wavelibrarian.config.schemas import valider
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import Question


class Freeze(BaseModel):
    """Empreinte du Gel, écrite par `wl questions geler` (AD-15)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str
    at: str
    seed: int
    dev_ratio: float


class QuestionsFile(BaseModel):
    """Document `questions.yaml` : un fichier par Corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_id: str
    target_count: int
    freeze: Freeze | None = None
    questions: tuple[Question, ...]


def load(chemin: Path) -> QuestionsFile:
    """Charge `chemin` ; erreur au chemin pointé (`questions[12].type`), id en double refusé."""
    donnees: Any = charger_yaml(chemin)
    if not isinstance(donnees, dict):
        raise ConfigError(str(chemin), "un fichier de Questions doit être un dictionnaire YAML")
    doc = valider(QuestionsFile, donnees, str(chemin))
    vus: dict[str, int] = {}
    for i, q in enumerate(doc.questions):
        if q.id in vus:
            raise ConfigError(
                f"questions[{i}].id",
                f"identifiant en double : {q.id!r} (déjà à questions[{vus[q.id]}]) ; "
                "un id n'est jamais réutilisé",
            )
        vus[q.id] = i
    return doc


def save(chemin: Path, doc: QuestionsFile) -> None:
    """Écrit `doc` (écriture atomique). Ordre des Questions et des clés : celui du contrat §4.5."""
    brut = doc.model_dump(mode="json")
    for q in brut["questions"]:
        q["reference_anchors"] = [
            {k: v for k, v in a.items() if not (k == "page" and v is None)}
            for a in q["reference_anchors"]
        ]
    texte = yaml.safe_dump(brut, sort_keys=False, allow_unicode=True, width=100)
    tmp = chemin.with_name(f"{chemin.name}.{os.getpid()}.tmp")
    tmp.write_text(texte, encoding="utf-8", newline="\n")
    tmp.replace(chemin)
