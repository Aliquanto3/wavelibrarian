"""Retriever `hybrid` : fusion des classements dense et lexical (RRF ou pondérée min-max)."""

from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.components.retrievers.dense import DenseRetriever
from wavelibrarian.components.retrievers.lexical import LexicalRetriever
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import ScoredPassage
from wavelibrarian.ports.components import SearchIndex
from wavelibrarian.registry import register


def fusion_rrf(listes: list[list[ScoredPassage]], rrf_k: int) -> dict[str, float]:
    """Pour chaque Passage, somme de 1 ÷ (rrf_k + rang) sur les listes où il apparaît."""
    scores: dict[str, float] = {}
    for liste in listes:
        for s in liste:
            i = s.passage.passage_id
            scores[i] = scores.get(i, 0.0) + 1.0 / (rrf_k + s.rank)
    return scores


def _min_max(liste: list[ScoredPassage]) -> dict[str, float]:
    """Scores ramenés dans [0, 1] ; liste à scores égaux : 1,0 pour chacun."""
    if not liste:
        return {}
    bas = min(s.score for s in liste)
    ecart = max(s.score for s in liste) - bas
    return {s.passage.passage_id: (s.score - bas) / ecart if ecart > 0 else 1.0 for s in liste}


def fusion_ponderee(
    dense: list[ScoredPassage], lexical: list[ScoredPassage], weight_dense: float
) -> dict[str, float]:
    """`weight_dense` × dense normalisé + (1 − `weight_dense`) × lexical normalisé (0 si absent)."""
    d, lex = _min_max(dense), _min_max(lexical)
    return {
        i: weight_dense * d.get(i, 0.0) + (1.0 - weight_dense) * lex.get(i, 0.0)
        for i in d.keys() | lex.keys()
    }


@register("retriever", "hybrid")
class HybridRetriever:
    """Interroge les index dense et lexical sur `candidates` Passages chacun, puis fusionne."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        fusion: Literal["rrf", "weighted"] = "rrf"
        rrf_k: int = Field(default=60, gt=0)
        weight_dense: float = Field(default=0.5, ge=0.0, le=1.0)
        candidates: int = Field(default=50, gt=0)  # profondeur de chaque liste avant fusion

    def __init__(self, params: "HybridRetriever.Params", ctx: Any) -> None:
        self.params = params
        self._dense = DenseRetriever(DenseRetriever.Params(), ctx)
        self._lexical = LexicalRetriever(LexicalRetriever.Params(), ctx)

    def retrieve(
        self,
        query: str,
        k: int,
        index: SearchIndex,
        query_vector: NDArray[np.float32] | None = None,
    ) -> list[ScoredPassage]:
        if index.vectors is None or index.lexical is None:
            raise WlError("le retriever `hybrid` exige un store vectoriel et un index lexical")
        p = self.params
        profondeur = max(k, p.candidates)
        dense = self._dense.retrieve(query, profondeur, index, query_vector)
        lexical = self._lexical.retrieve(query, profondeur, index)
        if p.fusion == "rrf":
            scores = fusion_rrf([dense, lexical], p.rrf_k)
        else:
            scores = fusion_ponderee(dense, lexical, p.weight_dense)
        classes = sorted(scores.items(), key=lambda t: (-t[1], t[0]))[:k]
        return [
            ScoredPassage(passage=index.passages[i], score=s, rank=r)
            for r, (i, s) in enumerate(classes, start=1)
        ]
