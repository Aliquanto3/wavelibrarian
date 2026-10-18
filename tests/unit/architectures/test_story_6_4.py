"""Story 6.4 : Architecture `corrective_rag` (Decider `llm`, QueryRewriter `llm`)."""

import json
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.corrective_rag import CorrectiveRag
from wavelibrarian.architectures.naive_rag import NaiveRag
from wavelibrarian.core.errors import ConfigError, NonConformantOutput
from wavelibrarian.core.types import ParsedCorpus, QuestionInput
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context as RunCtx
from wavelibrarian.runner.index_cache import IndexCache

PETITS = {"name": "fixed_tokens", "params": {"size": 40, "overlap": 5}}
REPONSE = '{"answer": "Réponse.", "citations": ["S1"], "abstain": false}'
REFORMULEE = "taxes douanes marché"


@pytest.fixture
def ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    provider = FakeProvider()
    c = RunCtx.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-1", seed=1, providers={"fake": provider}
    )
    c.parser = "markdown"
    c.provider = provider  # type: ignore[attr-defined]
    with c:
        yield c


def _arch(ctx: RunCtx, nom: str = "corrective_rag", **params: Any) -> Any:
    params.setdefault("embedder", {"name": "fake"})
    params.setdefault("chunker", PETITS)
    return ctx.build("architecture", ComponentSpec(name=nom, params=params))


def _question() -> QuestionInput:
    return QuestionInput(question_id="q-001", text="Que sait-on de la guilde Orvane ?", lang="fr")


def _repondre(arch: Any, ctx: RunCtx) -> Any:
    with ctx.scope(post="query", question_id="q-001"):
        return arch.answer(_question())


def _spans(ctx: RunCtx) -> list[dict[str, Any]]:
    lignes = (ctx.run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lignes]


def _etapes(ctx: RunCtx, depuis: int = 0) -> list[str]:
    return [s["wl.step"] for s in _spans(ctx)[depuis:] if s.get("wl.kind") == "llm"]


def _construire(ctx: RunCtx, corpus: ParsedCorpus, tmp_path: Path, **params: Any) -> Any:
    arch, _ = IndexCache(tmp_path / "home").build(ctx, lambda: _arch(ctx, **params), corpus)
    return arch


def _notes(*valeurs: float) -> Any:
    """Sortie `grade_relevance` : les valeurs données, complétées par 0.0 jusqu'au nombre reçu."""

    def sortie(req: LLMRequest) -> str:
        n = len(req.inputs["passages"])
        return json.dumps({"scores": [*valeurs, *([0.0] * n)][:n]})

    return sortie


def _espionner_recherches(arch: Any) -> list[str]:
    requetes: list[str] = []
    origine = arch.retriever.retrieve

    def espion(query: str, k: int, index: Any, query_vector: Any = None) -> Any:
        requetes.append(query)
        return origine(query, k, index, query_vector=query_vector)

    arch.retriever.retrieve = espion
    return requetes


def _espionner_generate(ctx: RunCtx) -> list[LLMRequest]:
    vues: list[LLMRequest] = []

    def generer(req: LLMRequest) -> str:
        vues.append(req)
        return REPONSE

    ctx.provider.script("generate", "generate*", generer)  # type: ignore[attr-defined]
    return vues


def test_enregistrement_defauts_et_meme_index_que_naive_rag(ctx: RunCtx) -> None:
    a = _arch(ctx)  # construit : déclenche la découverte des Composants
    assert registry.get("architecture", "corrective_rag") is CorrectiveRag
    assert registry.get("decider", "llm") is type(a.decider)
    assert registry.get("query_rewriter", "llm") is type(a.query_rewriter)
    assert a.params.threshold == 0.5 and a.params.max_loops == 2 and a.params.k == 5
    assert {"threshold", "max_loops"} <= CorrectiveRag.query_params
    assert CorrectiveRag.capabilities == NaiveRag.capabilities
    # threshold et max_loops hors de la clé d'index : l'index dense de naive_rag est réutilisé
    assert a.index_key() == _arch(ctx, threshold=0.9, max_loops=0).index_key()
    assert a.index_key() == _arch(ctx, "naive_rag").index_key()
    assert a.embedder_dim() == 64


def test_decider_trois_scores_dans_l_ordre_a_l_etape_de_la_boucle(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _construire(ctx, minicorpus, tmp_path)
    passages = list(arch._index.passages.values())[:3]
    ctx.provider.script("grade_relevance", "crag.grade.*", '{"scores": [0.9, 0.2, 0.5]}')  # type: ignore[attr-defined]
    with ctx.scope(post="query"):
        assert arch.decider.grade(_question(), passages, loop=0) == [0.9, 0.2, 0.5]
    assert _etapes(ctx)[-1] == "crag.grade.loop0"


@pytest.mark.parametrize("sortie", ['{"scores": [0.9, 1.5, 0.5]}', '{"scores": [0.9, -0.1, 0.5]}'])
def test_score_hors_bornes_est_une_sortie_non_conforme(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path, sortie: str
) -> None:
    arch = _construire(ctx, minicorpus, tmp_path)
    passages = list(arch._index.passages.values())[:3]
    ctx.provider.script("grade_relevance", "crag.grade.*", sortie)  # type: ignore[attr-defined]
    with pytest.raises(NonConformantOutput), ctx.scope(post="query"):
        arch.decider.grade(_question(), passages, loop=0)


def test_un_nombre_de_scores_different_du_nombre_de_passages_est_non_conforme(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _construire(ctx, minicorpus, tmp_path)
    passages = list(arch._index.passages.values())[:3]
    ctx.provider.script("grade_relevance", "crag.grade.*", '{"scores": [0.9]}')  # type: ignore[attr-defined]
    with pytest.raises(NonConformantOutput), ctx.scope(post="query"):
        arch.decider.grade(_question(), passages, loop=0)
    with ctx.scope(post="query"):
        assert arch.decider.grade(_question(), [], loop=0) == []


def test_seuls_les_passages_au_seuil_entrent_dans_le_contexte_et_la_reponse_en_cite_un(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    vues = _espionner_generate(ctx)
    ctx.provider.script("grade_relevance", "crag.grade.*", _notes(0.1, 0.5, 0.49, 0.9, 0.0))  # type: ignore[attr-defined]
    arch = _construire(ctx, minicorpus, tmp_path)
    rep = _repondre(arch, ctx)
    gardes = [s for s in rep.retrieved if s.rank in (2, 4)]  # 0,5 compte, 0,49 non
    assert len(rep.retrieved) == 5 and len(gardes) == 2
    assert len(vues) == 1
    assert list(vues[0].inputs["blocks"].values()) == [s.passage.text for s in gardes]
    assert len(rep.context_texts) == 2 and not rep.abstained
    assert {c.anchor_id for c in rep.citations} <= {a for s in gardes for a in s.passage.anchor_ids}
    assert rep.citations
    etapes = _etapes(ctx)
    assert etapes.count("crag.grade.loop0") == 1 and "crag.rewrite.loop1" not in etapes


def test_scores_par_defaut_du_faux_llm_au_dessus_du_seuil(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script("generate", "generate*", REPONSE)  # type: ignore[attr-defined]
    arch = _construire(ctx, minicorpus, tmp_path, threshold=0.3)
    rep = _repondre(arch, ctx)
    assert not rep.abstained and rep.context_texts and rep.citations


def test_tout_sous_le_seuil_deux_reformulations_puis_abstention_sans_generate(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script("grade_relevance", "crag.grade.*", _notes())  # type: ignore[attr-defined]
    ctx.provider.script("rewrite", "crag.rewrite.*", REFORMULEE)  # type: ignore[attr-defined]
    arch = _construire(ctx, minicorpus, tmp_path, max_loops=2)
    requetes = _espionner_recherches(arch)
    avant = len(_spans(ctx))
    rep = _repondre(arch, ctx)
    assert _etapes(ctx, avant) == [
        "crag.grade.loop0",
        "crag.rewrite.loop1",
        "crag.grade.loop1",
        "crag.rewrite.loop2",
        "crag.grade.loop2",
    ]
    assert "generate" not in _etapes(ctx)
    assert rep.abstained and rep.citations == () and rep.context_texts == ()
    assert requetes == [_question().text, REFORMULEE, REFORMULEE]


def test_max_loops_zero_ne_reformule_pas(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script("grade_relevance", "crag.grade.*", _notes())  # type: ignore[attr-defined]
    arch = _construire(ctx, minicorpus, tmp_path, max_loops=0)
    rep = _repondre(arch, ctx)
    assert rep.abstained
    assert [e for e in _etapes(ctx) if e.startswith("crag")] == ["crag.grade.loop0"]


def test_une_reformulation_suffit_et_le_contexte_vient_de_la_deuxieme_recherche(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    vues = _espionner_generate(ctx)
    ctx.provider.script("grade_relevance", "crag.grade.loop0", _notes())  # type: ignore[attr-defined]
    ctx.provider.script("grade_relevance", "crag.grade.loop1", _notes(0.8, 0.8))  # type: ignore[attr-defined]
    ctx.provider.script("rewrite", "crag.rewrite.*", REFORMULEE)  # type: ignore[attr-defined]
    arch = _construire(ctx, minicorpus, tmp_path)
    requetes = _espionner_recherches(arch)
    rep = _repondre(arch, ctx)
    etapes = [e for e in _etapes(ctx) if e.startswith("crag") or e == "generate"]
    assert etapes == ["crag.grade.loop0", "crag.rewrite.loop1", "crag.grade.loop1", "generate"]
    assert requetes == [_question().text, REFORMULEE]
    with ctx.scope(post="query"):
        premiere = arch.retriever.retrieve(_question().text, 5, arch._index)
        deuxieme = arch.retriever.retrieve(REFORMULEE, 5, arch._index)
    ids = [s.passage.passage_id for s in rep.retrieved]
    assert ids == [s.passage.passage_id for s in deuxieme]
    assert ids != [s.passage.passage_id for s in premiere]
    assert len(vues) == 1 and len(vues[0].inputs["blocks"]) == 2
    assert len(rep.context_texts) == 2 and not rep.abstained
    assert vues[0].inputs["question"] == _question().text  # generate reçoit la Question d'origine


def test_retriever_autre_que_dense_refuse(ctx: RunCtx) -> None:
    for nom in ("lexical", "hybrid"):
        with pytest.raises(ConfigError):
            _arch(ctx, retriever={"name": nom})
