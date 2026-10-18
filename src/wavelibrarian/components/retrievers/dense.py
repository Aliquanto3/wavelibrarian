"""Retriever `dense` : les k Passages les plus proches de la requête dans le store vectoriel."""

from typing import Any

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import ScoredPassage
from wavelibrarian.ports.components import SearchIndex
from wavelibrarian.registry import register


@register("retriever", "dense")
class DenseRetriever:
    """Recherche dense ; sans `query_vector`, la requête passe par `embed_queries`."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, params: "DenseRetriever.Params", ctx: Any) -> None:
        pass

    def retrieve(
        self,
        query: str,
        k: int,
        index: SearchIndex,
        query_vector: NDArray[np.float32] | None = None,
    ) -> list[ScoredPassage]:
        if index.vectors is None:
            raise WlError("le retriever `dense` exige un store vectoriel")
        vecteur = query_vector
        if vecteur is None:
            if index.embedder is None:
                raise WlError("le retriever `dense` exige un embedder sans `query_vector`")
            vecteur = index.embedder.embed_queries([query])[0]
        demande = k
        while True:
            bruts = index.vectors.search(vecteur, demande)
            trouves = [(i, s) for i, s in bruts if i in index.passages][:k]
            if len(trouves) >= k or len(bruts) < demande:
                break
            demande *= 2
        return [
            ScoredPassage(passage=index.passages[i], score=s, rank=r)
            for r, (i, s) in enumerate(trouves, start=1)
        ]

