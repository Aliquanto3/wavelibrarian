"""Architecture `naive_rag` : recherche dense des k meilleurs Passages puis génération citée."""

from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.architectures._passages import ecrire_passages, lire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.core.types import ArchAnswer, ParsedCorpus, Passage, QuestionInput
from wavelibrarian.ports.architecture import ArchCapabilities, ArchitectureBase, CorpusChange
from wavelibrarian.ports.components import ComponentSpec, Embedder, SearchIndex, VectorStore
from wavelibrarian.registry import register

_SOUS_DOSSIER = "vectors"
_LOT = 64  # Passages encodés par appel à l'Embedder


def _spec(nom: str) -> Any:
    return Field(default_factory=lambda: ComponentSpec(name=nom))


@register("architecture", "naive_rag")
class NaiveRag(ArchitectureBase):
    """Référence du niveau 1 : découpage, embeddings, store vectoriel, k plus proches voisins."""

    name = "naive_rag"
    capabilities = ArchCapabilities(incremental_update=True, retrieval_method="ranked")
    query_params: ClassVar[frozenset[str]] = frozenset({"k"})

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        chunker: ComponentSpec = _spec("fixed_tokens")
        embedder: ComponentSpec = _spec("sentence_transformers")
        store: ComponentSpec = _spec("numpy_exact")
        retriever: ComponentSpec = _spec("dense")
        context_builder: ComponentSpec = _spec("labeled")
        generator: ComponentSpec = _spec("llm")
        k: int = Field(default=5, gt=0)

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.chunker = ctx.build("chunker", params.chunker)
        self.embedder: Embedder = ctx.build("embedder", params.embedder)
        self.retriever = ctx.build("retriever", params.retriever)
        self.context_builder = ctx.build("context_builder", params.context_builder)
        self.generator = ctx.build("generator", params.generator)
        self._index: SearchIndex | None = None

    def embedder_dim(self) -> int | None:
        return int(self.embedder.dim)

    def _nouveau_store(self) -> VectorStore:
        spec = self.params.store  # type: ignore[attr-defined]
        avec_dim = ComponentSpec(name=spec.name, params={"dim": self.embedder.dim, **spec.params})
        store: VectorStore = self.ctx.build("vector_store", avec_dim)  # type: ignore[attr-defined]
        return store

    def _encoder(self, store: VectorStore, passages: list[Passage]) -> None:
        for debut in range(0, len(passages), _LOT):
            lot = passages[debut : debut + _LOT]
            vecteurs = self.embedder.embed_passages([p.text for p in lot])
            store.add([p.passage_id for p in lot], np.asarray(vecteurs, dtype=np.float32))

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        passages = [p for doc in corpus.documents for p in self.chunker.chunk(doc)]  # type: ignore[attr-defined]
        store = self._nouveau_store()
        self._encoder(store, passages)
        ecrire_passages(directory, passages)
        store.save(directory / _SOUS_DOSSIER)

    def update(
        self,
        change: CorpusChange,
        corpus_after: ParsedCorpus,
        old_directory: Path,
        new_directory: Path,
    ) -> None:
        """Retire les Passages des Documents supprimés ou remplacés, encode les nouveaux seuls."""
        retires = set(change.removed) | {ancien for ancien, _ in change.modified}
        nouveaux_docs = [*change.added, *(doc for _, doc in change.modified)]
        anciens = lire_passages(old_directory)
        store = self._nouveau_store()
        store.load(old_directory / _SOUS_DOSSIER)
        store.delete([p.passage_id for p in anciens if p.doc_id in retires])
        ajoutes = [p for doc in nouveaux_docs for p in self.chunker.chunk(doc)]  # type: ignore[attr-defined]
        self._encoder(store, ajoutes)
        gardes = [p for p in anciens if p.doc_id not in retires]
        ecrire_passages(new_directory, [*gardes, *ajoutes])
        store.save(new_directory / _SOUS_DOSSIER)

    def load(self, directory: Path) -> None:
        store = self._nouveau_store()
        store.load(directory / _SOUS_DOSSIER)
        passages = {p.passage_id: p for p in lire_passages(directory)}
        self._index = SearchIndex(passages=passages, embedder=self.embedder, vectors=store)

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
