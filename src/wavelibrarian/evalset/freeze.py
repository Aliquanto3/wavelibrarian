"""Gel du Jeu d'évaluation et séparation dev / test (FR-13, AD-15, AD-20, contracts §4.5).

`geler` attribue `split` (stratifié par `type`, déterministe par la graine) et écrit `freeze`.
`verify_frozen` (appelée par le runner) refuse un jeu non gelé ou modifié. `select_questions`
ne rend que les Questions `validated` ou `corrected` de la partie demandée.
Rien n'est écrit ici : l'écriture reste à `io.save`.
"""

import hashlib
import random
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import canonical_json
from wavelibrarian.core.types import Question
from wavelibrarian.evalset.io import Freeze, QuestionsFile

PARTICIPANTES = frozenset({"validated", "corrected"})
DEV_RATIO_DEFAUT = 0.4


def empreinte(doc: QuestionsFile) -> str:
    """SHA-256 de `canonical_json` du document sans `freeze` ni `contaminated_by` (AD-15)."""
    brut = doc.model_dump(mode="json", exclude={"freeze": True})
    for q in brut["questions"]:
        del q["contaminated_by"]
    return hashlib.sha256(canonical_json(brut).encode("utf-8")).hexdigest()


def nb_dev(n: int, dev_ratio: float) -> int:
    """Questions dev d'un Type de `n` Questions : `n * dev_ratio` arrondi à l'entier le plus proche,
    la moitié vers le haut (10 x 0,4 = 4 ; 3 x 0,5 = 2 ; 1 x 0,4 = 0)."""
    return int((Decimal(n) * Decimal(str(dev_ratio))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _partager(ids: Sequence[str], type_: str, dev_ratio: float, seed: int) -> set[str]:
    """Identifiants dev d'un Type : tirage sur les ids triés, graine propre au Type (AD-20)."""
    ordre = sorted(ids)
    graine = hashlib.sha256(f"{seed}\x1f{type_}".encode()).digest()
    random.Random(graine).shuffle(ordre)
    return set(ordre[: nb_dev(len(ordre), dev_ratio)])


def geler(
    doc: QuestionsFile,
    dev_ratio: float = DEV_RATIO_DEFAUT,
    seed: int = 42,
    at: datetime | None = None,
) -> QuestionsFile:
    """Répartit les Questions `validated` / `corrected` en dev et test, puis écrit `freeze`.

    Refus (`ConfigError`) tant qu'il reste des Questions `generated`. Les Questions `rejected`
    ne participent pas : leur `split` reste vide. Un nouveau Gel sur le même contenu avec la même
    graine redonne la même répartition, quel que soit l'ordre des Questions.
    """
    if not 0 <= dev_ratio <= 1:
        raise ConfigError("--dev-ratio", f"un nombre entre 0 et 1 est attendu, reçu {dev_ratio}")
    generees = [q.id for q in doc.questions if q.status == "generated"]
    if generees:
        raise ConfigError(
            "questions",
            f"{len(generees)} Question(s) `generated` à valider, corriger ou rejeter avant le "
            f"Gel : {', '.join(generees)}",
        )
    par_type: dict[str, list[str]] = {}
    for q in doc.questions:
        if q.status in PARTICIPANTES:
            par_type.setdefault(q.type, []).append(q.id)
    dev: set[str] = set()
    for type_, ids in par_type.items():
        dev |= _partager(ids, type_, dev_ratio, seed)
    questions = tuple(
        q.model_copy(update={"split": ("dev" if q.id in dev else "test")})
        if q.status in PARTICIPANTES
        else q.model_copy(update={"split": None})
        for q in doc.questions
    )
    nouveau = doc.model_copy(update={"questions": questions, "freeze": None})
    instant = (at or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    gel = Freeze(sha256=empreinte(nouveau), at=instant, seed=seed, dev_ratio=dev_ratio)
    return nouveau.model_copy(update={"freeze": gel})


def verify_frozen(doc: QuestionsFile) -> None:
    """`ConfigError` si le jeu n'est pas gelé ou si son empreinte a changé."""
    if doc.freeze is None:
        raise ConfigError("freeze", "jeu non gelé : lancer `wl questions geler` avant l'Exécution")
    actuelle = empreinte(doc)
    if actuelle != doc.freeze.sha256:
        raise ConfigError(
            "freeze.sha256",
            f"empreinte différente : le jeu a été modifié depuis le Gel "
            f"(gelé {doc.freeze.sha256}, actuel {actuelle})",
        )


def select_questions(
    questions: QuestionsFile | Sequence[Question], split: Literal["dev", "test"]
) -> tuple[Question, ...]:
    """Questions `validated` / `corrected` de la partie `split` ; `test` seulement si demandée."""
    if split not in ("dev", "test"):
        raise ConfigError("split", f"`dev` ou `test` attendu, reçu {split!r}")
    liste = questions.questions if isinstance(questions, QuestionsFile) else questions
    return tuple(q for q in liste if q.status in PARTICIPANTES and q.split == split)
