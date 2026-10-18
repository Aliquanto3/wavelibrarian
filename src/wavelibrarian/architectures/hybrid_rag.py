"""Architecture `hybrid_rag` : index dense et BM25, fusion, reranker optionnel (FR-19)."""

from pathlib import Path
from typing import Any, ClassVar, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.architectures._passages import ecrire_passages, lire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.components.retrievers.hybrid import HybridRetriever
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import (
    ArchAnswer,
    ParsedCorpus,
    Passage,
    QuestionInput,
    ScoredPassage,
)
from wavelibrarian.ports.architecture import ArchCapabilities, ArchitectureBase, CorpusChange
from wavelibrarian.ports.components import (
    ComponentSpec,
    Embedder,
    LexicalIndex,
    SearchIndex,
    VectorStore,
)
from wavelibrarian.registry import register

_VECTEURS = "vectors"
_LEXICAL = "lexical"
_LOT = 64  # Passages encodés par appel à l'Embedder


def _spec(nom: str) -> Any:
    return Field(default_factory=lambda: ComponentSpec(name=nom))


def _refuser_fusion_contradictoire(spec: ComponentSpec, fusion: dict[str, Any]) -> None:
    """Une seule source de vérité : les étages de fusion se règlent sur l'Architecture.

    La résolution complète `retriever.params` avec les défauts du Retriever : seule une valeur
    différente de ce défaut et de celle de l'Architecture trahit un réglage contradictoire.
    """
    defauts = HybridRetriever.Params()
    for cle, valeur in fusion.items():
        if cle not in spec.params:
            continue
        donnee = spec.params[cle]
        if donnee != getattr(defauts, cle) and donnee != valeur:
            raise ConfigError(
                f"retriever.params.{cle}",
                f"vaut {donnee!r} mais l'Architecture fixe {cle} = {valeur!r} ; "
                f"régler `{cle}` au niveau de l'Architecture `hybrid_rag`",
            )


@register("architecture", "hybrid_rag")
class HybridRag(ArchitectureBase):
    """Deux index (dense et BM25) construits ensemble ; chaque étage de requête se configure
    à part : `retriever` (`dense`, `lexical` ou `hybrid`), fusion, reranker."""

    name = "hybrid_rag"
    # Deux index distincts : aucun besoin d'un store hybride (`requires_hybrid_store = false`).
    capabilities = ArchCapabilities(incremental_update=True, retrieval_method="ranked")
    query_params: ClassVar[frozenset[str]] = frozenset(
        {"k", "retriever", "fusion", "rrf_k", "weight_dense", "reranker", "rerank_top_n"}
    )

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        chunker: ComponentSpec = _spec("fixed_tokens")
        embedder: ComponentSpec = _spec("sentence_transformers")
        store: ComponentSpec = _spec("numpy_exact")
        lexical_index: ComponentSpec = _spec("bm25")
        retriever: ComponentSpec = _spec("hybrid")
        context_builder: ComponentSpec = _spec("labeled")
        generator: ComponentSpec = _spec("llm")
        reranker: ComponentSpec | None = None
        fusion: Literal["rrf", "weighted"] = "rrf"
        rrf_k: int = Field(default=60, gt=0)
        weight_dense: float = Field(default=0.5, ge=0.0, le=1.0)
        rerank_top_n: int = Field(default=20, gt=0)
        k: int = Field(default=5, gt=0)

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.chunker = ctx.build("chunker", params.chunker)
        self.embedder: Embedder = ctx.build("embedder", params.embedder)
        self.context_builder = ctx.build("context_builder", params.context_builder)
        self.generator = ctx.build("generator", params.generator)
        spec = params.retriever
        if spec.name == "hybrid":  # les étages de fusion sont des Params de l'Architecture
            fusion = {
                "fusion": params.fusion,
                "rrf_k": params.rrf_k,
                "weight_dense": params.weight_dense,
            }
            _refuser_fusion_contradictoire(spec, fusion)
            spec = ComponentSpec(name=spec.name, params={**spec.params, **fusion})
        self.retriever = ctx.build("retriever", spec)
        self.reranker = ctx.build("reranker", params.reranker) if params.reranker else None
        self._index: SearchIndex | None = None

    def embedder_dim(self) -> int | None:
        return int(self.embedder.dim)

    def _nouveau_store(self) -> VectorStore:
        spec = self.params.store  # type: ignore[attr-defined]
        avec_dim = ComponentSpec(name=spec.name, params={"dim": self.embedder.dim, **spec.params})
        store: VectorStore = self.ctx.build("vector_store", avec_dim)  # type: ignore[attr-defined]
        return store

    def _nouveau_lexical(self) -> LexicalIndex:
        spec = self.params.lexical_index  # type: ignore[attr-defined]
        lexical: LexicalIndex = self.ctx.build("lexical_index", spec)  # type: ignore[attr-defined]
        return lexical

    def _ajouter(self, store: VectorStore, lexical: LexicalIndex, passages: list[Passage]) -> None:
        for debut in range(0, len(passages), _LOT):
            lot = passages[debut : debut + _LOT]
            vecteurs = self.embedder.embed_passages([p.text for p in lot])
            store.add([p.passage_id for p in lot], np.asarray(vecteurs, dtype=np.float32))
        lexical.add(passages)

    def _ecrire(
        self, dossier: Path, store: VectorStore, lexical: LexicalIndex, passages: list[Passage]
    ) -> None:
        ecrire_passages(dossier, passages)
        store.save(dossier / _VECTEURS)
        lexical.save(dossier / _LEXICAL)

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        passages = [p for doc in corpus.documents for p in self.chunker.chunk(doc)]  # type: ignore[attr-defined]
        store, lexical = self._nouveau_store(), self._nouveau_lexical()
        self._ajouter(store, lexical, passages)
        self._ecrire(directory, store, lexical, passages)

    def update(
        self,
        change: CorpusChange,
        corpus_after: ParsedCorpus,
        old_directory: Path,
        new_directory: Path,
    ) -> None:
        """Retire les Passages des Documents supprimés ou remplacés des deux index, ajoute les
        nouveaux seuls."""
        retires = set(change.removed) | {ancien for ancien, _ in change.modified}
        nouveaux_docs = [*change.added, *(doc for _, doc in change.modified)]
        anciens = lire_passages(old_directory)
        store, lexical = self._nouveau_store(), self._nouveau_lexical()
        store.load(old_directory / _VECTEURS)
        lexical.load(old_directory / _LEXICAL)
        sortants = [p.passage_id for p in anciens if p.doc_id in retires]
        store.delete(sortants)
        lexical.delete(sortants)
        ajoutes = [p for doc in nouveaux_docs for p in self.chunker.chunk(doc)]  # type: ignore[attr-defined]
        self._ajouter(store, lexical, ajoutes)
        gardes = [p for p in anciens if p.doc_id not in retires]
        self._ecrire(new_directory, store, lexical, [*gardes, *ajoutes])

    def load(self, directory: Path) -> None:
        store, lexical = self._nouveau_store(), self._nouveau_lexical()
        store.load(directory / _VECTEURS)
        lexical.load(directory / _LEXICAL)
        passages = {p.passage_id: p for p in lire_passages(directory)}
        self._index = SearchIndex(
            passages=passages, embedder=self.embedder, vectors=store, lexical=lexical
        )

    def _recuperer(self, texte: str, index: SearchIndex) -> list[ScoredPassage]:
        k = self.params.k  # type: ignore[attr-defined]
        if self.reranker is None:
            return self.retriever.retrieve(texte, k, index)  # type: ignore[attr-defined]
        top_n = self.params.rerank_top_n  # type: ignore[attr-defined]
        candidats = self.retriever.retrieve(texte, max(k, top_n), index)  # type: ignore[attr-defined]
        reclasses = self.reranker.rerank(texte, candidats, top_n)  # type: ignore[attr-defined]
        # `k` > `rerank_top_n` : les candidats non reclassés suivent, dans l'ordre de la fusion,
        # score plafonné au dernier score reclassé pour que les scores décroissent avec le rang
        # (les échelles de la fusion et du reranker ne sont pas comparables).
        vus = {s.passage.passage_id for s in reclasses}
        plafond = reclasses[-1].score if reclasses else None
        suite = [
            s if plafond is None else s.model_copy(update={"score": min(s.score, plafond)})
            for s in candidats
            if s.passage.passage_id not in vus
        ]
        final = [*reclasses, *suite][:k]
        return [s.model_copy(update={"rank": r}) for r, s in enumerate(final, start=1)]

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if self._index is None:
            raise RuntimeError("`load` doit précéder `answer`")
        classes = self._recuperer(question.text, self._index)
        contexte = self.context_builder.build([s.passage for s in classes])
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(
            contexte,
            resultat,
            classes,
            "ranked",
            tokenizer=self.ctx.tokenizer_for(self.generator.model_id),
        )
