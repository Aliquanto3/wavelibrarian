"""Port Architecture (contracts.md §2.1). Aucune entrée-sortie."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.types import (
    ArchAnswer,
    CorpusProfile,
    ParsedCorpus,
    ParsedDocument,
    Passage,
    QuestionInput,
)
from wavelibrarian.ports.arch_answer import build_arch_answer, passages_fournis
from wavelibrarian.ports.components import ContextBuilder, Generator
from wavelibrarian.ports.context import RunContext


class ArchCapabilities(BaseModel):
    # ClassVar partagé par toutes les instances : gelé, et une faute de frappe lève une erreur.
    model_config = ConfigDict(frozen=True, extra="forbid")

    incremental_update: bool = False  # False : update() = réindexation complète, poste "update"
    retrieval_method: Literal["ranked", "provided", "cited", "none"] = "ranked"
    full_corpus_in_prompt: bool = False  # contexte long, CAG : contrôle de fenêtre et de palier
    requires_prompt_cache: bool = False  # CAG
    requires_hybrid_store: bool = False


class Applicability(BaseModel):
    applicable: bool
    reason: str | None = None


class CorpusChange(BaseModel):
    added: tuple[ParsedDocument, ...] = ()
    removed: tuple[str, ...] = ()  # doc_ids
    modified: tuple[tuple[str, ParsedDocument], ...] = ()  # (ancien doc_id, nouveau document)


class ArchitectureBase(ABC):
    name: ClassVar[str]
    Params: ClassVar[type[BaseModel]]  # extra="forbid" ; sous-Composants en ComponentSpec
    capabilities: ClassVar[ArchCapabilities]
    generator: Generator  # requis : sert à la Condition contexte parfait
    context_builder: ContextBuilder

    query_params: ClassVar[frozenset[str]] = frozenset()  # Params sans effet sur l'index

    def __init__(self, params: BaseModel, ctx: RunContext) -> None:
        self.params = params
        self.ctx = ctx

    def check(self, profile: CorpusProfile) -> Applicability:
        """Défaut : applicable."""
        return Applicability(applicable=True)

    def embedder_dim(self) -> int | None:
        """Dimension de l'embedder de l'index, portée au manifeste (FR-3) ; `None` sans embedder.
        Les Architectures à embeddings (epic 6) la redéfinissent."""
        return None

    def index_key(self) -> dict[str, Any]:
        """Params résolus moins `query_params`, plus parser résolu et nom du tokenizer (AD-10)."""
        params = self.params.model_dump(mode="json", exclude=set(self.query_params))
        return {
            "params": params,
            "parser": self.ctx.parser,
            "tokenizer": self.ctx.tokenizer.name,
        }

    @abstractmethod
    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        """Écrit l'index dans `directory` ; ne garde pas d'état."""

    @abstractmethod
    def load(self, directory: Path) -> None:
        """Seul moyen d'être prêt à répondre."""

    def update(
        self,
        change: CorpusChange,
        corpus_after: ParsedCorpus,
        old_directory: Path,
        new_directory: Path,
    ) -> None:
        """Défaut : réindexation complète dans `new_directory`."""
        self.index(corpus_after, new_directory)

    @abstractmethod
    def answer(self, question: QuestionInput) -> ArchAnswer: ...

    def answer_with_context(
        self, question: QuestionInput, passages: Sequence[Passage]
    ) -> ArchAnswer:
        """Défaut : `context_builder.build` puis `generator.generate` (contexte parfait), avec la
        même assemblée que `answer` (`build_arch_answer` : troncature au-delà de 8 000 tokens)."""
        context = self.context_builder.build(passages)
        result = self.generator.generate(question, context)
        return build_arch_answer(
            context,
            result,
            passages_fournis(passages),
            "provided",
            tokenizer=self.ctx.tokenizer_for(self.generator.model_id),
        )
