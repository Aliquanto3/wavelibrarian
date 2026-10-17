"""Faux embedder : sac de mots haché en dimension fixe, déterministe, sans modèle ni réseau."""

import hashlib
import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated, Any

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.types import ModelRefMeta, Usage
from wavelibrarian.registry import register

_MOT = re.compile(r"\w+")


def _indice_et_signe(mot: str, dim: int) -> tuple[int, float]:
    h = hashlib.blake2b(mot.encode("utf-8"), digest_size=8).digest()
    n = int.from_bytes(h, "big")
    return n % dim, 1.0 if (n >> 32) & 1 else -1.0


@register("embedder", "fake")
class FakeEmbedder:
    """Vecteurs unitaires de dimension du Catalogue, tirés des mots du texte (tests sans réseau)."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        model: Annotated[str | None, ModelRefMeta("embedder")] = None

    def __init__(self, params: "FakeEmbedder.Params", ctx: Any) -> None:
        self._ctx = ctx
        self.model_id: str = params.model or ctx.profile.defaults.embedder
        self.dim: int = ctx.catalog.get(self.model_id).dim
        self._tokenizer = ctx.tokenizer_for(self.model_id)

    def embed_passages(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return self._embed(texts)

    def embed_queries(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return self._embed(texts)

    def _vecteur(self, texte: str) -> NDArray[np.float32]:
        v = np.zeros(self.dim, dtype=np.float64)
        for mot in _MOT.findall(texte.lower()) or [""]:  # texte vide : vecteur fixe, norme 1
            i, signe = _indice_et_signe(mot, self.dim)
            v[i] += signe
        norme = np.linalg.norm(v)
        if norme == 0.0:  # mots qui s'annulent exactement : repli sur le premier axe
            v[0] = 1.0
            norme = 1.0
        return (v / norme).astype(np.float32)

    def _embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        vecteurs = (
            np.stack([self._vecteur(t) for t in texts])
            if texts
            else np.zeros((0, self.dim), dtype=np.float32)
        )
        entree = sum(self._tokenizer.count(t) for t in texts)
        self._ctx.tracer.record(
            "embed",
            "embed",
            model_id=self.model_id,
            provider="fake",
            usage=Usage(input_tokens=entree),
            cost=Decimal(0),
            cost_uncached=Decimal(0),
            currency="EUR",
            latency_s=0.0,
            from_cache=False,
        )
        return vecteurs
