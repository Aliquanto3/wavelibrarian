"""Ports des Composants (contracts.md §2). Aucune entrée-sortie."""

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.types import (
    Citation,
    Criterion,
    DocMeta,
    ParsedDocument,
    Passage,
    QuestionInput,
    ScoredPassage,
)

if TYPE_CHECKING:
    import networkx

KINDS: tuple[str, ...] = (
    "parser",
    "chunker",
    "embedder",
    "vector_store",
    "lexical_index",
    "graph_store",
    "retriever",
    "reranker",
    "context_builder",
    "decider",
    "generator",
    "judge",
    "query_rewriter",
    "architecture",
)  # liste fermée des `kind`


class ComponentSpec(BaseModel):
    """Forme YAML de toute référence à un Composant."""

    model_config = ConfigDict(extra="forbid")  # une clé mal orthographiée est refusée (FR-9)

    name: str
    params: dict[str, Any] = {}


class Parser(Protocol):
    formats: ClassVar[frozenset[str]]  # sous-ensemble de {"markdown","text","html","pdf"}

    def parse(self, source_path: str, raw: bytes, lang: str, meta: DocMeta) -> ParsedDocument: ...


class Chunker(Protocol):
    def key(self) -> str: ...  # nom + paramètres canoniques, entre dans passage_id
    def chunk(self, doc: ParsedDocument) -> list[Passage]: ...


@runtime_checkable
class Embedder(Protocol):
    model_id: str  # identifiant du Catalogue
    dim: int

    def embed_passages(self, texts: Sequence[str]) -> NDArray[np.float32]: ...  # (n, dim), norme 1
    def embed_queries(self, texts: Sequence[str]) -> NDArray[np.float32]: ...


class StoreCapabilities(BaseModel):
    hybrid: bool = False
    deletions: bool = True


@runtime_checkable
class VectorStore(Protocol):
    capabilities: ClassVar[StoreCapabilities]
    dim: int

    def add(self, ids: Sequence[str], vectors: NDArray[np.float32]) -> None: ...
    def delete(self, ids: Sequence[str]) -> None: ...
    def search(
        self, query: NDArray[np.float32], k: int
    ) -> list[tuple[str, float]]: ...  # score décroissant, ex æquo départagés par id
    def save(self, directory: Path) -> None: ...
    def load(self, directory: Path) -> None: ...


@runtime_checkable
class LexicalIndex(Protocol):
    """Index BM25."""

    def add(self, passages: Sequence[Passage]) -> None: ...
    def delete(self, ids: Sequence[str]) -> None: ...
    def search(self, text: str, k: int) -> list[tuple[str, float]]: ...
    def save(self, directory: Path) -> None: ...
    def load(self, directory: Path) -> None: ...


class GraphStore(Protocol):
    def upsert_entity(
        self, entity_id: str, name: str, kind: str, description: str, passage_ids: Sequence[str]
    ) -> None: ...
    def upsert_relation(
        self,
        source: str,
        target: str,
        description: str,
        weight: float,
        passage_ids: Sequence[str],
    ) -> None: ...
    def remove_passages(self, passage_ids: Sequence[str]) -> None: ...  # retire les orphelins
    def graph(self) -> "networkx.Graph[Any]": ...
    def save(self, directory: Path) -> None: ...
    def load(self, directory: Path) -> None: ...


class SearchIndex(BaseModel):
    """Assemblé par l'Architecture, passé au Retriever."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    passages: dict[str, Passage]
    embedder: Embedder | None = None
    vectors: VectorStore | None = None
    lexical: LexicalIndex | None = None


class Retriever(Protocol):
    def retrieve(
        self,
        query: str,
        k: int,
        index: SearchIndex,
        query_vector: NDArray[np.float32] | None = None,
    ) -> list[ScoredPassage]: ...


class Reranker(Protocol):
    def rerank(
        self, query: str, passages: Sequence[ScoredPassage], top_n: int
    ) -> list[ScoredPassage]: ...


class Context(BaseModel):
    text: str  # blocs "[S1] (ancrage) texte" concaténés
    blocks: tuple[str, ...]  # un bloc par étiquette, dans l'ordre
    labels: dict[str, tuple[str, ...]]  # "S1" -> anchor_ids (AD-7)
    passage_ids: dict[str, str]  # "S1" -> passage_id


class ContextBuilder(Protocol):
    def build(self, passages: Sequence[Passage]) -> Context: ...


class GenerationResult(BaseModel):
    text: str
    abstained: bool
    citations: tuple[Citation, ...]  # labels déjà convertis en ancrages, invalides retirés
    invalid_citations: int


class Generator(Protocol):
    model_id: str

    def generate(self, question: QuestionInput, context: Context) -> GenerationResult: ...


class Decider(Protocol):
    model_id: str | None

    # `loop` : rang de la boucle de l'Architecture, qui nomme l'étape de la Trace (`….loopN`).
    def grade(
        self, question: QuestionInput, passages: Sequence[Passage], loop: int = 0
    ) -> list[float]: ...  # dans [0, 1]


class QueryRewriter(Protocol):
    def rewrite(self, question: QuestionInput, loop: int = 1) -> str: ...


class JudgeInput(BaseModel):
    question: str
    reference_answer: str
    reference_texts: tuple[str, ...]  # texte des Ancrages de référence
    answer_text: str
    context_texts: tuple[str, ...]  # ce que le Generator a reçu (pour la fidélité)


class Judge(Protocol):
    model_id: str

    def judge(
        self, item: JudgeInput, criteria: Sequence[Criterion], pass_id: int
    ) -> dict[Criterion, tuple[bool, str]]: ...
