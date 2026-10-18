"""Métriques de recherche (FR-35, contracts.md §7) : rappel@k, MRR et nDCG@k.

Un Passage est pertinent dès que ses `anchor_ids` recoupent les Ancrages de référence, quel que
soit le Découpage. Fonctions pures, sans entrée-sortie.

- rappel@k : part des Ancrages de référence recouverts par les k premiers Passages ;
- MRR : inverse du rang du premier Passage pertinent de la liste entière (0 s'il n'y en a pas) ;
- nDCG@k : gain binaire, décompte `1 / log2(rang + 1)` ; l'idéal place `min(k, nb d'Ancrages de
  référence)` Passages pertinents en tête, et la valeur est plafonnée à 1 (plusieurs Passages
  peuvent recouvrir le même Ancrage).

La méthode (`ranked`, `provided`, `cited`, `none`) est reportée telle quelle. `none` et une
Question sans Ancrage de référence (`unanswerable`) ne produisent aucune métrique.
"""

import math
from collections.abc import Collection, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.types import Passage, ScoredPassage

K_PAR_DEFAUT = 5
RetrievalMethod = Literal["ranked", "provided", "cited", "none"]


class RetrievalScores(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: RetrievalMethod
    k: int
    recall: float | None = None
    mrr: float | None = None
    ndcg: float | None = None


def est_pertinent(passage: Passage, reference_anchor_ids: Collection[str]) -> bool:
    return not set(passage.anchor_ids).isdisjoint(reference_anchor_ids)


def retrieval_metrics(
    retrieved: Sequence[ScoredPassage],
    reference_anchor_ids: Collection[str],
    method: RetrievalMethod,
    k: int = K_PAR_DEFAUT,
) -> RetrievalScores:
    """Métriques d'une Question ; `reference_anchor_ids` : `anchor_id` des Ancrages de référence."""
    reference = set(reference_anchor_ids)
    if method == "none" or not reference:
        return RetrievalScores(method=method, k=k)
    classes = sorted(retrieved, key=lambda s: s.rank)
    pertinents = [est_pertinent(s.passage, reference) for s in classes]
    couverts = {a for s in classes[:k] for a in s.passage.anchor_ids if a in reference}
    premier = next((i for i, p in enumerate(pertinents, start=1) if p), None)
    dcg = sum(1 / math.log2(i + 1) for i, p in enumerate(pertinents[:k], start=1) if p)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, len(reference)) + 1))
    return RetrievalScores(
        method=method,
        k=k,
        recall=len(couverts) / len(reference),
        mrr=0.0 if premier is None else 1 / premier,
        ndcg=min(1.0, dcg / ideal),
    )
