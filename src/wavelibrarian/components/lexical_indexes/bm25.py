"""Index lexical `bm25` (bm25s) : recherche par mots, sans modèle (FR-14)."""

import json
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import bm25s
from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import Passage
from wavelibrarian.registry import register

_MOT = re.compile(r"\w+")
_FICHIER = "lexical.json"


def tokeniser(texte: str) -> list[str]:
    """Minuscules, sans accents, mots alphanumériques ; même règle pour l'index et la requête."""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFKD", texte.casefold()) if not unicodedata.combining(c)
    )
    return _MOT.findall(sans_accents)


@register("lexical_index", "bm25")
class Bm25Index:
    """BM25 (bm25s) sur le texte des Passages ; les mots indexés sont sauvegardés, l'index bm25s
    est reconstruit au premier `search` (déterministe), ce qui rend `delete` exact."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, params: "Bm25Index.Params", ctx: Any) -> None:
        self._mots: dict[str, list[str]] = {}  # passage_id -> mots, dans l'ordre d'ajout
        self._moteur: bm25s.BM25 | None = None
        self._ids: list[str] = []

    def add(self, passages: Sequence[Passage]) -> None:
        for p in passages:
            self._mots[p.passage_id] = tokeniser(p.text)
        self._moteur = None

    def delete(self, ids: Sequence[str]) -> None:
        for i in ids:
            self._mots.pop(i, None)
        self._moteur = None

    def search(self, text: str, k: int) -> list[tuple[str, float]]:
        """Au plus `k` couples (id, score > 0), score décroissant, ex æquo par id."""
        requete = tokeniser(text)
        if k <= 0 or not requete or not self._mots:
            return []
        if self._moteur is None:
            self._ids = list(self._mots)
            self._moteur = bm25s.BM25()
            self._moteur.index([self._mots[i] for i in self._ids], show_progress=False)
        scores = self._moteur.get_scores(requete)
        trouves = [(i, float(s)) for i, s in zip(self._ids, scores, strict=True) if s > 0]
        trouves.sort(key=lambda t: (-t[1], t[0]))
        return trouves[:k]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        contenu = json.dumps(self._mots, ensure_ascii=False)
        (directory / _FICHIER).write_bytes(contenu.encode("utf-8"))

    def load(self, directory: Path) -> None:
        chemin = directory / _FICHIER
        try:
            mots = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WlError(f"index lexical illisible : {chemin}") from exc
        self._mots = {str(i): list(m) for i, m in mots.items()}
        self._moteur = None
