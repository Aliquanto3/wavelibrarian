"""Reranker `fake` : score de recouvrement de mots avec la requête, déterministe, sans modèle."""

import re
import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.types import ScoredPassage, Usage
from wavelibrarian.registry import register

_MOT = re.compile(r"\w+")


def _mots(texte: str) -> set[str]:
    return set(_MOT.findall(texte.casefold()))


@register("reranker", "fake")
class FakeReranker:
    """Reclasse les `top_n` premiers candidats par part des mots de la requête retrouvés dans le
    Passage ; égalités départagées par le rang d'origine. Trace un span `rerank` par appel."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, params: "FakeReranker.Params", ctx: Any) -> None:
        self._ctx = ctx

    def rerank(
        self, query: str, passages: Sequence[ScoredPassage], top_n: int
    ) -> list[ScoredPassage]:
        debut = time.perf_counter()
        requete = _mots(query)
        candidats = list(passages)[: max(top_n, 0)]

        def recouvrement(s: ScoredPassage) -> float:
            return len(requete & _mots(s.passage.text)) / len(requete) if requete else 0.0

        notes = [(recouvrement(s), i, s) for i, s in enumerate(candidats)]
        notes.sort(key=lambda t: (-t[0], t[1]))
        resultat = [
            ScoredPassage(passage=s.passage, score=note, rank=r)
            for r, (note, _, s) in enumerate(notes, start=1)
        ]
        self._ctx.tracer.record(
            "rerank",
            "rerank",
            model_id=None,
            provider="fake",
            usage=Usage(input_tokens=sum(len(_mots(s.passage.text)) for s in candidats)),
            cost=Decimal(0),
            cost_uncached=Decimal(0),
            currency="EUR",
            latency_s=time.perf_counter() - debut,
            from_cache=False,
            extra={"wl.candidates": len(candidats)},
        )
        return resultat
