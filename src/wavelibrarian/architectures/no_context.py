"""Architecture `no_context` : le Generator répond sans aucun Contexte (FR-16)."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.architectures._passages import ecrire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.core.types import ArchAnswer, ParsedCorpus, QuestionInput
from wavelibrarian.ports.architecture import ArchCapabilities, ArchitectureBase
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.registry import register


@register("architecture", "no_context")
class NoContext(ArchitectureBase):
    """Baseline « sans contexte » : Contexte vide, aucune recherche."""

    name = "no_context"
    capabilities = ArchCapabilities(retrieval_method="none")

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        generator: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="llm"))
        context_builder: ComponentSpec = Field(
            default_factory=lambda: ComponentSpec(name="labeled")
        )

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.generator = ctx.build("generator", params.generator)
        self.context_builder = ctx.build("context_builder", params.context_builder)

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        ecrire_passages(directory, [])

    def load(self, directory: Path) -> None:
        """Rien à charger."""

    def answer(self, question: QuestionInput) -> ArchAnswer:
        contexte = self.context_builder.build([])
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(
            contexte,
            resultat,
            [],
            "none",
            tokenizer=self.ctx.tokenizer_for(self.generator.model_id),
        )
