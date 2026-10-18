"""VectorStore `numpy_exact` : produit scalaire exact en mémoire, sauvegardé en `.npy` (FR-18)."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.errors import WlError
from wavelibrarian.ports.components import StoreCapabilities
from wavelibrarian.registry import register

_IDS = "ids.json"
_VECTEURS = "vectors.npy"


@register("vector_store", "numpy_exact")
class NumpyExactStore:
    """Recherche exacte par produit scalaire (vecteurs de norme 1 : similarité cosinus).

    `dim` : dimension attendue ; sans valeur, elle est fixée par le premier ajout ou le `load`.
    """

    capabilities: ClassVar[StoreCapabilities] = StoreCapabilities(hybrid=False, deletions=True)

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        dim: int | None = None

    def __init__(self, params: "NumpyExactStore.Params", ctx: Any) -> None:
        self.dim: int = params.dim if params.dim is not None else 0
        self._ids: list[str] = []
        self._matrice: NDArray[np.float32] = np.zeros((0, self.dim), dtype=np.float32)

    def _verifier(self, vecteurs: NDArray[np.float32]) -> NDArray[np.float32]:
        v = np.asarray(vecteurs, dtype=np.float32)
        if v.ndim != 2:
            raise WlError(f"vecteurs attendus en 2 dimensions, reçu {v.ndim}")
        if self.dim == 0 and not self._ids:
            self.dim = int(v.shape[1])
            self._matrice = np.zeros((0, self.dim), dtype=np.float32)
        if v.shape[1] != self.dim:
            raise WlError(f"dimension {v.shape[1]} différente de celle du store ({self.dim})")
        return v

    def add(self, ids: Sequence[str], vectors: NDArray[np.float32]) -> None:
        v = self._verifier(vectors)
        if len(ids) != v.shape[0]:
            raise WlError(f"{len(ids)} identifiants pour {v.shape[0]} vecteurs")
        if len(set(ids)) != len(ids):
            raise WlError("identifiants dupliqués dans `add`")
        self.delete(ids)  # un id déjà présent est remplacé
        self._ids.extend(ids)
        self._matrice = np.vstack([self._matrice, v])

    def delete(self, ids: Sequence[str]) -> None:
        a_retirer = set(ids)
        garde = [n for n, i in enumerate(self._ids) if i not in a_retirer]
        if len(garde) == len(self._ids):
            return
        self._ids = [self._ids[n] for n in garde]
        self._matrice = self._matrice[garde]

    def search(self, query: NDArray[np.float32], k: int) -> list[tuple[str, float]]:
        """Au plus `k` couples (id, score), score décroissant, ex æquo départagés par id."""
        q = np.asarray(query, dtype=np.float32).reshape(-1)
        if q.shape[0] != self.dim:
            raise WlError(f"dimension {q.shape[0]} différente de celle du store ({self.dim})")
        if k <= 0 or not self._ids:
            return []
        scores = self._matrice @ q
        couples = [(i, float(s)) for i, s in zip(self._ids, scores, strict=True)]
        couples.sort(key=lambda t: (-t[1], t[0]))
        return couples[:k]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        contenu = json.dumps({"dim": self.dim, "ids": self._ids}, ensure_ascii=False)
        (directory / _IDS).write_bytes(contenu.encode("utf-8"))
        np.save(directory / _VECTEURS, self._matrice, allow_pickle=False)

    def load(self, directory: Path) -> None:
        try:
            meta = json.loads((directory / _IDS).read_text(encoding="utf-8"))
            matrice = np.load(directory / _VECTEURS, allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise WlError(f"store vectoriel illisible : {directory}") from exc
        dim = int(meta["dim"])
        if self.dim and dim != self.dim:
            raise WlError(f"dimension {dim} du store sauvegardé différente de {self.dim}")
        ids = [str(i) for i in meta["ids"]]
        if matrice.ndim != 2 or matrice.shape != (len(ids), dim):
            raise WlError(f"store vectoriel incohérent : {directory}")
        self.dim = dim
        self._ids = ids
        self._matrice = matrice.astype(np.float32, copy=False)
