"""Tests des ports publiés (story 1.2)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import pytest
from pydantic import BaseModel

from wavelibrarian.core.types import ArchAnswer, Citation, ParsedCorpus, Passage, QuestionInput
from wavelibrarian.ports import architecture, components, context, gateway, measure
from wavelibrarian.ports.architecture import (
    Applicability,
    ArchCapabilities,
    ArchitectureBase,
    CorpusChange,
)
from wavelibrarian.ports.components import Context, GenerationResult, SearchIndex

ATTENDUS = {
    components: [
        "ComponentSpec", "SearchIndex", "Context", "GenerationResult", "JudgeInput", "Parser",
        "Chunker", "Embedder", "VectorStore", "LexicalIndex", "GraphStore", "Retriever",
        "Reranker", "ContextBuilder", "Generator", "Decider", "QueryRewriter", "Judge",
    ],
    architecture: ["ArchitectureBase", "ArchCapabilities", "Applicability", "CorpusChange"],
    gateway: ["LLMRole", "Message", "LLMRequest", "LLMResult", "ModelGateway"],
    measure: ["Tokenizer", "Tracer", "EnergyMeter", "EnergyEstimator"],
    context: ["RunContext"],
}  # fmt: skip


def test_ports_exposes_les_noms() -> None:
    for module, noms in ATTENDUS.items():
        for nom in noms:
            assert hasattr(module, nom), f"{module.__name__}.{nom}"


def test_quinze_roles_llm() -> None:
    assert len(get_args(gateway.LLMRole)) == 15


def test_kinds_ferme() -> None:
    assert len(components.KINDS) == 14 and "architecture" in components.KINDS


class _Gen:
    model_id = "fake"

    def generate(self, question: QuestionInput, context: Context) -> GenerationResult:
        return GenerationResult(
            text="rep " + context.text,
            abstained=False,
            citations=(Citation(anchor_id="d#p1"),),
            invalid_citations=1,
        )


class _CB:
    def build(self, passages: Any) -> Context:
        return Context(
            text="[S1] t",
            blocks=("[S1] t",),
            labels={"S1": tuple(a for p in passages for a in p.anchor_ids)},
            passage_ids={"S1": passages[0].passage_id},
        )


class _Arch(ArchitectureBase):
    name = "dummy"
    Params = BaseModel
    capabilities = ArchCapabilities()
    query_params = frozenset({"k"})
    indexed: list[Path] = []

    def __init__(self, params: BaseModel, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.generator = _Gen()
        self.context_builder = _CB()

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        self.indexed.append(directory)

    def load(self, directory: Path) -> None:
        pass

    def answer(self, question: QuestionInput) -> ArchAnswer:
        return ArchAnswer(text="", abstained=True)


class _P(BaseModel):
    k: int = 5
    size: int = 300


def _arch(parser: str = "markdown=markdown,pdf=pdf_text") -> _Arch:
    ctx = SimpleNamespace(tokenizer=SimpleNamespace(name="approx"), parser=parser)
    return _Arch(_P(), ctx)


def test_architecture_base_est_abstraite() -> None:
    with pytest.raises(TypeError):
        ArchitectureBase(_P(), None)  # type: ignore[abstract, arg-type]


def test_answer_with_context_par_defaut() -> None:
    p = Passage(passage_id="p1", doc_id="d", text="x", anchor_ids=("d#p1",))
    q = QuestionInput(question_id="q", text="?", lang="fr")
    rep = _arch().answer_with_context(q, [p])
    assert rep.text == "rep [S1] t"
    assert rep.retrieval_method == "provided"
    assert rep.context_anchor_ids == ("d#p1",)
    assert rep.context_texts == ("[S1] t",)
    assert rep.invalid_citations == 1


def test_update_reindexe_dans_new_directory(tmp_path: Path) -> None:
    a = _arch()
    _Arch.indexed.clear()
    corpus = ParsedCorpus(corpus_id="c", fingerprint="f", documents=())
    a.update(CorpusChange(), corpus, tmp_path / "old", tmp_path / "new")
    assert _Arch.indexed == [tmp_path / "new"]


def test_check_et_index_key_par_defaut() -> None:
    a = _arch()
    assert a.check(None) == Applicability(applicable=True)  # type: ignore[arg-type]
    cle = a.index_key()
    assert cle["params"] == {"size": 300} and cle["tokenizer"] == "approx"
    assert cle["parser"] == "markdown=markdown,pdf=pdf_text"
    assert _arch(parser="pdf=pdf_ocr").index_key() != cle


def test_arch_capabilities_strictes_et_gelees() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ArchCapabilities(requires_prompt_cahce=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ArchCapabilities().requires_prompt_cache = True  # type: ignore[misc]


def test_search_index_accepte_des_objets_conformes() -> None:
    class Lex:
        def add(self, passages: Any) -> None: ...
        def delete(self, ids: Any) -> None: ...
        def search(self, text: str, k: int) -> list[tuple[str, float]]:
            return []

        def save(self, directory: Path) -> None: ...
        def load(self, directory: Path) -> None: ...

    idx = SearchIndex(passages={}, lexical=Lex())
    assert idx.lexical is not None
