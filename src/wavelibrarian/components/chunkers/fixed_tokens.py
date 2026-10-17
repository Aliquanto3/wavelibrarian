"""Chunker `fixed_tokens` : fenêtres de tokens fixes avec recouvrement (FR-15, AD-5, AD-7)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import ParsedDocument, Passage
from wavelibrarian.registry import register


@register("chunker", "fixed_tokens")
class FixedTokenChunker:
    """Découpage en fenêtres de tokens fixes, chaque Passage portant les Ancrages qu'il recouvre."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        size: int = Field(default=300, gt=0)
        overlap: int = Field(default=50, ge=0)

        @model_validator(mode="after")
        def _recouvrement_inferieur_a_la_taille(self) -> "FixedTokenChunker.Params":
            if self.overlap >= self.size:
                raise ValueError("`overlap` doit être inférieur à `size`")
            return self

    def __init__(self, params: "FixedTokenChunker.Params", ctx: Any) -> None:
        self._size = params.size
        self._overlap = params.overlap
        self._tokenizer = ctx.tokenizer

    def key(self) -> str:
        return f"fixed_tokens:size={self._size}:overlap={self._overlap}"

    def chunk(self, doc: ParsedDocument) -> list[Passage]:
        """Fenêtres de mots pesés par le tokenizer du contexte ; un mot n'est jamais coupé.

        Un Passage porte, dans l'ordre du Document, les Ancrages des Blocks dont il contient un mot.
        """
        mots: list[tuple[str, str, int]] = []  # (mot, anchor_id, nombre de tokens)
        for bloc in doc.blocks:
            for mot in bloc.text.split():
                mots.append((mot, bloc.anchor_id, max(1, self._tokenizer.count(mot))))
        passages: list[Passage] = []
        debut, n = 0, len(mots)
        while debut < n:
            fin, poids = debut, 0
            while fin < n and (fin == debut or poids + mots[fin][2] <= self._size):
                poids += mots[fin][2]
                fin += 1
            fenetre = mots[debut:fin]
            ancres = tuple(dict.fromkeys(a for _, a, _ in fenetre))
            passages.append(
                Passage(
                    passage_id=sha16(doc.doc_id, self.key(), str(len(passages))),
                    doc_id=doc.doc_id,
                    text=" ".join(m for m, _, _ in fenetre),
                    anchor_ids=ancres,
                    level=0,
                )
            )
            if fin >= n:
                break
            recul, reculees = 0, fin
            while reculees > debut + 1 and recul < self._overlap:
                reculees -= 1
                recul += mots[reculees][2]
            debut = reculees
        return passages
