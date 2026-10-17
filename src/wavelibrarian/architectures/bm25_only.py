"""Architecture `bm25_only` : recherche lexicale BM25 seule, sans embedding (FR-14)."""

from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.architectures._passages import ecrire_passages, lire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.core.types import ArchAnswer, ParsedCorpus, QuestionInput
from wavelibrarian.ports.architecture import ArchCapabilities, ArchitectureBase
from wavelibrarian.ports.components import ComponentSpec, LexicalIndex, SearchIndex
from wavelibrarian.registry import register

_SOUS_DOSSIER = "lexical"


def _spec(nom: str) -> Any:
    return Field(default_factory=lambda: ComponentSpec(name=nom))


@register("architecture", "bm25_only")
class Bm25Only(ArchitectureBase):
    """Baseline « BM25 seul » : découpage, index lexical, les k meilleurs Passages au Generator."""

    name = "bm25_only"
    capabilities = ArchCapabilities(retrieval_method="ranked")
    query_params: ClassVar[frozenset[str]] = frozenset({"k"})

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        chunker: ComponentSpec = _spec("fixed_tokens")
        lexical_index: ComponentSpec = _spec("bm25")
        retriever: ComponentSpec = _spec("lexical")
        context_builder: ComponentSpec = _spec("labeled")
        generator: ComponentSpec = _spec("llm")
        k: int = Field(default=5, gt=0)

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.chunker = ctx.build("chunker", params.chunker)
        self.retriever = ctx.build("retriever", params.retriever)
        self.context_builder = ctx.build("context_builder", params.context_builder)
        self.generator = ctx.build("generator", params.generator)
        self._index: SearchIndex | None = None

    def _nouvel_index_lexical(self) -> LexicalIndex:
        index: LexicalIndex = self.ctx.build("lexical_index", self.params.lexical_index)  # type: ignore[attr-defined]
        return index

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        passages = [p for doc in corpus.documents for p in self.chunker.chunk(doc)]
        lexical = self._nouvel_index_lexical()
        lexical.add(passages)
        ecrire_passages(directory, passages)
        lexical.save(directory / _SOUS_DOSSIER)

    def load(self, directory: Path) -> None:
        lexical = self._nouvel_index_lexical()
        lexical.load(directory / _SOUS_DOSSIER)
        passages = {p.passage_id: p for p in lire_passages(directory)}
        self._index = SearchIndex(passages=passages, lexical=lexical)

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if self._index is None:
            raise RuntimeError("`load` doit précéder `answer`")
        classes = self.retriever.retrieve(question.text, self.params.k, self._index)  # type: ignore[attr-defined]
        contexte = self.context_builder.build([s.passage for s in classes])
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(
            contexte,
            resultat,
            classes,
            "ranked",
            tokenizer=self.ctx.tokenizer_for(self.generator.model_id),
        )
