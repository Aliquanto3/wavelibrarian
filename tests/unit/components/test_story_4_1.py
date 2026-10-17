"""Story 4.1 : chunker `fixed_tokens`, ContextBuilder `labeled`, Generator `llm`, ArchAnswer."""

from pathlib import Path

import pytest

from wavelibrarian import registry
from wavelibrarian.components.chunkers.fixed_tokens import FixedTokenChunker
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.components.context.labeled import LabeledContextBuilder
from wavelibrarian.components.generators.llm import LLMGenerator
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import (
    Block,
    ConversationTurn,
    ParsedCorpus,
    ParsedDocument,
    Passage,
    QuestionInput,
    ScoredPassage,
)
from wavelibrarian.llm.providers.fake import FakeProvider, default_output
from wavelibrarian.ports.components import ComponentSpec, Context, GenerationResult
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context as RunCtx


@pytest.fixture
def ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    provider = FakeProvider()
    c = RunCtx.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-1", seed=1, providers={"fake": provider}
    )
    c.provider = provider  # type: ignore[attr-defined]
    with c:
        yield c


def _chunker(ctx: RunCtx, **params: int) -> FixedTokenChunker:
    return ctx.build("chunker", ComponentSpec(name="fixed_tokens", params=params))  # type: ignore[no-any-return]


def _passage(i: int, ancres: tuple[str, ...], texte: str) -> Passage:
    return Passage(passage_id=f"p{i}", doc_id="d", text=texte, anchor_ids=ancres)


# --- Chunker ---------------------------------------------------------------------------------


def test_chunker_enregistre_et_passages_du_minicorpus(
    ctx: RunCtx, minicorpus: ParsedCorpus
) -> None:
    assert registry.get("chunker", "fixed_tokens") is FixedTokenChunker
    chunker = _chunker(ctx, size=60, overlap=10)
    plus_de_un = False
    for doc in minicorpus.documents:
        passages = chunker.chunk(doc)
        assert passages
        plus_de_un = plus_de_un or len(passages) > 1
        for ordinal, p in enumerate(passages):
            assert p.level == 0
            assert p.doc_id == doc.doc_id
            assert p.anchor_ids
            assert all(a in doc.anchors for a in p.anchor_ids)
            assert p.passage_id == sha16(doc.doc_id, chunker.key(), str(ordinal))
    assert plus_de_un


def test_chunker_taille_et_recouvrement(ctx: RunCtx) -> None:
    mots = [f"m{i}" for i in range(25)]
    doc = ParsedDocument(
        doc_id="d1",
        source_path="a.md",
        format="text",
        lang="fr",
        blocks=(Block(text=" ".join(mots), anchor_id="d1#h/a", kind="text"),),
        anchors={},
    )
    passages = _chunker(ctx, size=10, overlap=3).chunk(doc)
    textes = [p.text.split() for p in passages]
    assert all(len(t) <= 10 for t in textes)
    assert textes[0] == mots[:10]
    assert textes[1][:3] == mots[7:10]  # recouvrement de 3 mots
    assert textes[-1][-1] == "m24"
    assert [p.anchor_ids for p in passages] == [("d1#h/a",)] * len(passages)


def test_passage_a_cheval_sur_deux_sections_porte_les_deux_ancrages(ctx: RunCtx) -> None:
    doc = ParsedDocument(
        doc_id="d2",
        source_path="a.md",
        format="markdown",
        lang="fr",
        blocks=(
            Block(text="un deux trois quatre", anchor_id="d2#h/a", kind="text"),
            Block(text="cinq six sept huit", anchor_id="d2#h/b", kind="text"),
        ),
        anchors={},
    )
    passages = _chunker(ctx, size=6, overlap=2).chunk(doc)
    assert passages[0].anchor_ids == ("d2#h/a", "d2#h/b")


def test_key_change_avec_size_et_overlap(ctx: RunCtx) -> None:
    base = _chunker(ctx).key()
    assert _chunker(ctx, size=200).key() != base
    assert _chunker(ctx, overlap=10).key() != base
    assert _chunker(ctx).key() == base


def test_chunker_refuse_un_recouvrement_trop_grand(ctx: RunCtx) -> None:
    with pytest.raises(ConfigError):
        _chunker(ctx, size=10, overlap=10)


# --- ContextBuilder --------------------------------------------------------------------------


def test_labeled_construit_les_blocs_et_les_tables(ctx: RunCtx) -> None:
    builder = ctx.build("context_builder", ComponentSpec(name="labeled"))
    assert isinstance(builder, LabeledContextBuilder)
    passages = [
        _passage(1, ("d#h/a",), "Alpha."),
        _passage(2, ("d#h/b", "d#h/c"), "Beta."),
        _passage(3, ("e#p1",), "Gamma."),
    ]
    contexte = builder.build(passages)
    assert contexte.blocks == (
        "[S1] (d#h/a) Alpha.",
        "[S2] (d#h/b, d#h/c) Beta.",
        "[S3] (e#p1) Gamma.",
    )
    assert contexte.text == "\n\n".join(contexte.blocks)
    assert contexte.labels == {"S1": ("d#h/a",), "S2": ("d#h/b", "d#h/c"), "S3": ("e#p1",)}
    assert contexte.passage_ids == {"S1": "p1", "S2": "p2", "S3": "p3"}
    assert builder.build([]).blocks == ()


# --- Generator -------------------------------------------------------------------------------


def _contexte() -> Context:
    return LabeledContextBuilder(LabeledContextBuilder.Params(), None).build(
        [_passage(1, ("d#h/a",), "Alpha vaut un. Suite."), _passage(2, ("d#h/b",), "Beta.")]
    )


def _generateur(ctx: RunCtx) -> LLMGenerator:
    return ctx.build("generator", ComponentSpec(name="llm"))  # type: ignore[no-any-return]


def _question(**kw: object) -> QuestionInput:
    return QuestionInput(question_id="q-001", text="Que vaut Alpha ?", lang="fr", **kw)  # type: ignore[arg-type]


def test_generator_enregistre_et_modele_par_defaut(ctx: RunCtx) -> None:
    assert registry.get("generator", "llm") is LLMGenerator
    assert _generateur(ctx).model_id == ctx.profile.defaults.generator_models[0]
    assert (
        ctx.build("generator", ComponentSpec(name="llm", params={"model": "fake-llm-b"})).model_id
        == "fake-llm-b"
    )


def test_citation_invalide_retiree_et_comptee(ctx: RunCtx) -> None:
    requetes: list[LLMRequest] = []

    def sortie(req: LLMRequest) -> str:
        requetes.append(req)
        return '{"answer": "Un.", "citations": ["S1", "S9"], "abstain": false}'

    ctx.provider.script("generate", "generate*", sortie)  # type: ignore[attr-defined]
    with ctx.scope(post="query", question_id="q-001"):
        res = _generateur(ctx).generate(_question(), _contexte())
    assert [c.anchor_id for c in res.citations] == ["d#h/a"]
    assert res.invalid_citations == 1
    assert res.abstained is False
    assert set(requetes[0].inputs) >= {"question", "blocks"}
    assert requetes[0].inputs["blocks"] == {"S1": "Alpha vaut un. Suite.", "S2": "Beta."}


def test_contexte_vide_le_faux_llm_s_abstient(ctx: RunCtx) -> None:
    requetes: list[LLMRequest] = []

    def sortie(req: LLMRequest) -> str:
        requetes.append(req)
        return default_output("generate", req.inputs)

    ctx.provider.script("generate", "generate*", sortie)  # type: ignore[attr-defined]
    vide = LabeledContextBuilder(LabeledContextBuilder.Params(), None).build([])
    with ctx.scope(post="query", question_id="q-001"):
        res = _generateur(ctx).generate(_question(), vide)
    assert requetes[0].inputs["blocks"] == {}  # le Faux LLM reçoit un contexte vide
    assert "(aucun passage)" in requetes[0].messages[-1].content
    assert res.abstained is True
    assert res.citations == () and res.invalid_citations == 0
    assert res.text != ""  # texte d'abstention, distinct de l'indicateur


@pytest.mark.parametrize(
    ("sortie", "abstention"),
    [
        ('{"answer": "Alpha vaut un.", "citations": [], "abstain": true}', True),
        ('{"answer": "Je ne sais pas.", "citations": [], "abstain": false}', False),
    ],
)
def test_abstention_lue_sur_l_indicateur_pas_sur_le_texte(
    ctx: RunCtx, sortie: str, abstention: bool
) -> None:
    ctx.provider.script("generate", "generate*", lambda _req: sortie)  # type: ignore[attr-defined]
    with ctx.scope(post="query", question_id="q-001"):
        res = _generateur(ctx).generate(_question(), _contexte())
    assert res.abstained is abstention
    assert res.text == sortie.split('"')[3]


def test_formes_d_etiquette(ctx: RunCtx) -> None:
    formes = '["[S1]", " S2 ", "[S1", "S2]", "s1", "S01"]'
    sortie = f'{{"answer": "Un.", "citations": {formes}, "abstain": false}}'
    ctx.provider.script("generate", "generate*", lambda _req: sortie)  # type: ignore[attr-defined]
    with ctx.scope(post="query", question_id="q-001"):
        res = _generateur(ctx).generate(_question(), _contexte())
    assert [c.anchor_id for c in res.citations] == ["d#h/a", "d#h/b"]
    assert res.invalid_citations == 4  # `[S1`, `S2]`, `s1`, `S01` refusées


def test_generation_nominale_cite_s1(ctx: RunCtx) -> None:
    with ctx.scope(post="query", question_id="q-001"):
        res = _generateur(ctx).generate(_question(), _contexte())
    assert res.abstained is False
    assert res.text == "Alpha vaut un."
    assert [c.anchor_id for c in res.citations] == ["d#h/a"]


def test_historique_transmis_en_messages(ctx: RunCtx) -> None:
    requetes: list[LLMRequest] = []

    def sortie(req: LLMRequest) -> str:
        requetes.append(req)
        return default_output("generate", req.inputs)

    ctx.provider.script("generate", "generate*", sortie)  # type: ignore[attr-defined]
    historique = (
        ConversationTurn(role="user", text="Parle-moi de la guilde."),
        ConversationTurn(role="assistant", text="Elle date de 1412."),
    )
    with ctx.scope(post="query", question_id="q-001"):
        _generateur(ctx).generate(_question(history=historique), _contexte())
    msgs = requetes[0].messages
    assert [(m.role, m.content) for m in msgs[:2]] == [
        ("user", "Parle-moi de la guilde."),
        ("assistant", "Elle date de 1412."),
    ]
    assert msgs[-1].role == "user"
    assert "Que vaut Alpha ?" in msgs[-1].content and "[S1]" in msgs[-1].content


# --- build_arch_answer -----------------------------------------------------------------------


class _Mots:
    name = "mots"

    def count(self, text: str) -> int:
        return len(text.split())


def _resultat(*ancres: str) -> GenerationResult:
    from wavelibrarian.core.types import Citation

    return GenerationResult(
        text="R.",
        abstained=False,
        citations=tuple(Citation(anchor_id=a) for a in ancres),
        invalid_citations=2,
    )


def test_arch_answer_reprend_les_blocs_sous_le_seuil() -> None:
    contexte = _contexte()
    scored = (ScoredPassage(passage=_passage(1, ("d#h/a",), "Alpha."), score=1.0, rank=1),)
    rep = build_arch_answer(contexte, _resultat("d#h/a"), scored, "ranked", tokenizer=_Mots())
    assert rep.context_texts == contexte.blocks
    assert rep.context_truncated is False
    assert rep.context_anchor_ids == ("d#h/a", "d#h/b")
    assert rep.retrieved == scored
    assert rep.retrieval_method == "ranked"
    assert rep.invalid_citations == 2
    assert rep.text == "R." and rep.abstained is False


def test_arch_answer_tronque_aux_blocs_cites_au_dela_du_seuil() -> None:
    contexte = _contexte()
    rep = build_arch_answer(
        contexte,
        _resultat("d#h/b"),
        (),
        "provided",
        tokenizer=_Mots(),
        max_context_tokens=3,
    )
    assert rep.context_truncated is True
    assert rep.context_texts == (contexte.blocks[1],)
    assert rep.context_anchor_ids == ("d#h/a", "d#h/b")  # tout ce qui a été fourni
