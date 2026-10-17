"""ContextBuilder `labeled` : blocs `[S1] (ancrage) texte` (AD-7)."""

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.types import Passage
from wavelibrarian.ports.components import Context
from wavelibrarian.registry import register


@register("context_builder", "labeled")
class LabeledContextBuilder:
    """Numérote les Passages reçus `[S1]…[Sn]` dans l'ordre et tient la table des étiquettes."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, params: "LabeledContextBuilder.Params", ctx: Any) -> None:
        pass

    def build(self, passages: Sequence[Passage]) -> Context:
        blocs: list[str] = []
        labels: dict[str, tuple[str, ...]] = {}
        passage_ids: dict[str, str] = {}
        for i, p in enumerate(passages, start=1):
            etiquette = f"S{i}"
            blocs.append(f"[{etiquette}] ({', '.join(p.anchor_ids)}) {p.text}")
            labels[etiquette] = p.anchor_ids
            passage_ids[etiquette] = p.passage_id
        return Context(
            text="\n\n".join(blocs), blocks=tuple(blocs), labels=labels, passage_ids=passage_ids
        )
