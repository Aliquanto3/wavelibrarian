"""Architecture `long_context` : tout le Corpus dans le prompt, system en cache (FR-16)."""

import math
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.architectures._passages import ecrire_passages, lire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import (
    ArchAnswer,
    CorpusProfile,
    ParsedCorpus,
    Passage,
    QuestionInput,
    ScoredPassage,
)
from wavelibrarian.ports.architecture import Applicability, ArchCapabilities, ArchitectureBase
from wavelibrarian.ports.components import ComponentSpec, Context
from wavelibrarian.registry import register


def _passages_par_ancrage(corpus: ParsedCorpus) -> list[Passage]:
    """Un Passage par Ancrage non vide, dans l'ordre des Documents puis des Ancrages."""
    passages: list[Passage] = []
    for doc in corpus.documents:
        for anchor_id in doc.anchors:
            texte = "\n\n".join(b.text for b in doc.blocks if b.anchor_id == anchor_id)
            if texte.strip():
                passages.append(
                    Passage(
                        passage_id=sha16(doc.doc_id, "long_context", anchor_id),
                        doc_id=doc.doc_id,
                        text=texte,
                        anchor_ids=(anchor_id,),
                    )
                )
    return passages


@register("architecture", "long_context")
class LongContext(ArchitectureBase):
    """Baseline « tout le Corpus » : un bloc étiqueté par Ancrage, Réponse `cited`."""

    name = "long_context"
    capabilities = ArchCapabilities(retrieval_method="cited", full_corpus_in_prompt=True)

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        generator: ComponentSpec = Field(
            default_factory=lambda: ComponentSpec(name="llm", params={"cache_system": True})
        )
        context_builder: ComponentSpec = Field(
            default_factory=lambda: ComponentSpec(name="labeled")
        )

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.generator = ctx.build("generator", params.generator)
        self.context_builder = ctx.build("context_builder", params.context_builder)
        self._contexte: Context | None = None
        self._par_ancrage: dict[str, Passage] = {}

    def check(self, profile: CorpusProfile) -> Applicability:
        """Inapplicable si le Corpus dépasse la fenêtre du modèle ou un palier tarifaire."""
        modele = self.generator.model_id
        entree = self.ctx.catalog.get(modele)
        tokens = profile.tokens_for(modele, self.ctx.catalog)
        if entree.tokenizer == "reference":
            # `tokens_for` rend les tokens de référence tels quels : on applique le facteur du
            # Catalogue, comme l'estimation avant appel de la passerelle (contracts §4.2).
            tokens = math.ceil(Decimal(tokens) * entree.token_factor)
        fenetre = entree.context_window
        if fenetre is not None and tokens > fenetre:
            return Applicability(
                applicable=False,
                reason=(
                    f"le Corpus (environ {tokens} tokens pour {modele}) dépasse la fenêtre "
                    f"de {fenetre} tokens"
                ),
            )
        if entree.pricing is not None:
            for palier in entree.pricing.tiers:
                if tokens > palier.above_prompt_tokens:
                    return Applicability(
                        applicable=False,
                        reason=(
                            f"le prompt estimé (environ {tokens} tokens pour {modele}) dépasse "
                            f"le palier tarifaire de {palier.above_prompt_tokens} tokens "
                            f"(prix ×{palier.multiplier})"
                        ),
                    )
        return Applicability(applicable=True)

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        ecrire_passages(directory, _passages_par_ancrage(corpus))

    def load(self, directory: Path) -> None:
        passages = lire_passages(directory)
        self._par_ancrage = {p.anchor_ids[0]: p for p in passages}
        self._contexte = self.context_builder.build(passages)

    def answer(self, question: QuestionInput) -> ArchAnswer:
        contexte = self._contexte
        if contexte is None:
            raise RuntimeError("`load` doit précéder `answer`")
        resultat = self.generator.generate(question, contexte)
        cites = [
            ScoredPassage(passage=self._par_ancrage[c.anchor_id], score=1.0, rank=rang)
            for rang, c in enumerate(resultat.citations, start=1)
            if c.anchor_id in self._par_ancrage
        ]
        return build_arch_answer(
            contexte,
            resultat,
            cites,
            "cited",
            tokenizer=self.ctx.tokenizer_for(self.generator.model_id),
        )
