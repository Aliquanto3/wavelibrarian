"""Assemblage de l'`ArchAnswer` à partir du Contexte et du résultat du Generator (AD-6, FR-36)."""

from collections.abc import Sequence
from typing import Literal

from wavelibrarian.core.types import ArchAnswer, Passage, ScoredPassage
from wavelibrarian.ports.components import Context, GenerationResult
from wavelibrarian.ports.measure import Tokenizer

MAX_CONTEXT_TOKENS = 8_000


def build_arch_answer(
    context: Context,
    result: GenerationResult,
    retrieved: Sequence[ScoredPassage],
    method: Literal["ranked", "provided", "cited", "none"],
    *,
    tokenizer: Tokenizer,
    max_context_tokens: int = MAX_CONTEXT_TOKENS,
) -> ArchAnswer:
    """Réponse d'Architecture : `context_texts` reprend `Context.blocks`, sauf au-delà de
    `max_context_tokens` où seuls les blocs dont un Ancrage est cité sont gardés."""
    tronque = tokenizer.count(context.text) > max_context_tokens
    blocs = context.blocks
    if tronque:
        cites = {c.anchor_id for c in result.citations}
        blocs = tuple(
            bloc
            for etiquette, bloc in zip(context.labels, context.blocks, strict=True)
            if cites.intersection(context.labels[etiquette])
        )
    ancrages = dict.fromkeys(a for anchors in context.labels.values() for a in anchors)
    return ArchAnswer(
        text=result.text,
        abstained=result.abstained,
        citations=result.citations,
        retrieved=tuple(retrieved),
        retrieval_method=method,
        context_anchor_ids=tuple(ancrages),
        context_texts=blocs,
        context_truncated=tronque,
        invalid_citations=result.invalid_citations,
    )


def passages_fournis(passages: Sequence[Passage]) -> tuple[ScoredPassage, ...]:
    """`retrieved` de la méthode `provided` : les Passages fournis, dans l'ordre (rang 1 en
    tête, score 1.0)."""
    return tuple(ScoredPassage(passage=p, score=1.0, rank=i) for i, p in enumerate(passages, 1))
