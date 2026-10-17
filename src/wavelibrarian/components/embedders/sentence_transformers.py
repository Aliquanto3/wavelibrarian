"""Embedder sentence-transformers local : préfixes du Catalogue, périphérique du profil."""

import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated, Any

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import ModelRefMeta, Usage
from wavelibrarian.registry import register


@register("embedder", "sentence_transformers")
class SentenceTransformersEmbedder:
    """Vecteurs normalisés (norme 1) d'un modèle sentence-transformers du cache local.

    L'extra `local` n'est requis qu'au premier encodage ; le modèle n'est jamais téléchargé ici
    (`wl installer` s'en charge).
    """

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        model: Annotated[str | None, ModelRefMeta("embedder")] = None
        batch_size: Annotated[int, Field(ge=1)] = 32

    def __init__(self, params: "SentenceTransformersEmbedder.Params", ctx: Any) -> None:
        self._ctx = ctx
        self._batch = params.batch_size
        self.model_id: str = params.model or ctx.profile.defaults.embedder
        entree = ctx.catalog.get(self.model_id)
        self.dim: int = entree.dim
        self._repo: str = entree.hf_repo or self.model_id
        self._prefixe_requete: str = entree.query_prefix
        self._prefixe_passage: str = entree.passage_prefix
        self._device: str = ctx.profile.embedder_device
        self._tokenizer = ctx.tokenizer_for(self.model_id)
        self._modele: Any = None

    def embed_passages(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return self._embed(texts, self._prefixe_passage)

    def embed_queries(self, texts: Sequence[str]) -> NDArray[np.float32]:
        return self._embed(texts, self._prefixe_requete)

    def _charger(self) -> Any:
        if self._modele is None:
            try:
                from sentence_transformers import SentenceTransformer  # pyright: ignore[reportMissingImports]
            except ImportError:
                raise WlError("installer l'extra local") from None
            try:
                self._modele = SentenceTransformer(
                    self._repo, device=self._device, local_files_only=True
                )
            except Exception as exc:  # modèle absent du cache, périphérique inconnu, etc.
                raise WlError(
                    f"embedder {self.model_id} non chargé ({type(exc).__name__}) : "
                    "lancer `wl installer` pour le préparer"
                ) from exc
        return self._modele

    def _embed(self, texts: Sequence[str], prefixe: str) -> NDArray[np.float32]:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        modele = self._charger()
        lots: list[NDArray[np.float32]] = []
        for debut in range(0, len(texts), self._batch):
            lot = [prefixe + t for t in texts[debut : debut + self._batch]]
            t0 = time.perf_counter()
            brut = np.asarray(
                modele.encode(lot, normalize_embeddings=True, convert_to_numpy=True),
                dtype=np.float32,
            )
            latence = time.perf_counter() - t0
            if brut.shape != (len(lot), self.dim):
                raise WlError(
                    f"embedder {self.model_id} : forme {brut.shape} au lieu de "
                    f"({len(lot)}, {self.dim})"
                )
            normes = np.linalg.norm(brut, axis=1, keepdims=True)
            lots.append((brut / np.where(normes == 0.0, 1.0, normes)).astype(np.float32))
            self._ctx.tracer.record(
                "embed",
                "embed",
                model_id=self.model_id,
                provider="sentence_transformers",
                usage=Usage(input_tokens=sum(self._tokenizer.count(t) for t in lot)),
                cost=Decimal(0),
                cost_uncached=Decimal(0),
                currency="EUR",
                latency_s=latence,
                from_cache=False,
            )
        return np.concatenate(lots)
