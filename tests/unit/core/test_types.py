"""Tests des types du domaine (story 1.2)."""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from wavelibrarian.core import types as t
from wavelibrarian.core.types import (
    Anchor,
    Answer,
    Block,
    CorpusProfile,
    ParsedCorpus,
    ParsedDocument,
    Passage,
    Usage,
)
from wavelibrarian.ports.gateway import LLMResult

NOMS = [
    "Anchor", "Block", "ParsedDocument", "ParsedCorpus", "Passage", "ScoredPassage",
    "QuestionInput", "Citation", "ArchAnswer", "Answer", "AnchorRef", "Question",
    "CorpusProfile", "Usage", "Verdict", "DocMeta", "ModelRefMeta", "ModelRef",
    "QuestionType", "Criterion", "CostPost", "Condition", "Phase", "JUDGED_CRITERIA",
    "ConversationTurn",
]  # fmt: skip


def _doc_md() -> ParsedDocument:
    did = "aaaa111122223333"
    a1 = f"{did}#h/histoire/fondation"
    a2 = f"{did}#h/histoire"
    return ParsedDocument(
        doc_id=did,
        source_path="docs/a.md",
        format="markdown",
        lang="fr",
        blocks=(
            Block(text="Histoire", anchor_id=a2, kind="heading"),
            Block(text="Un", anchor_id=a1, kind="text"),
            Block(text="Autre", anchor_id=a2, kind="text"),
            Block(text="Deux", anchor_id=a1, kind="text"),
        ),
        anchors={
            a2: Anchor(
                anchor_id=a2, doc_id=did, source_path="docs/a.md", heading_path=("Histoire",)
            ),
            a1: Anchor(
                anchor_id=a1, doc_id=did, source_path="docs/a.md",
                heading_path=("Histoire", "Fondation"),
            ),
        },
    )  # fmt: skip


def _doc_pdf() -> ParsedDocument:
    did = "bbbb111122223333"
    ancres = {
        f"{did}#p{n}": Anchor(anchor_id=f"{did}#p{n}", doc_id=did, source_path="docs/b.pdf", page=n)
        for n in (1, 2)
    }
    return ParsedDocument(
        doc_id=did,
        source_path="docs/b.pdf",
        format="pdf",
        lang="fr",
        blocks=(
            Block(text="p1", anchor_id=f"{did}#p1", kind="text"),
            Block(text="p2a", anchor_id=f"{did}#p2", kind="text"),
            Block(text="p2b", anchor_id=f"{did}#p2", kind="table"),
        ),
        anchors=ancres,
    )


def _corpus() -> ParsedCorpus:
    return ParsedCorpus(corpus_id="c", fingerprint="f", documents=(_doc_md(), _doc_pdf()))


def test_tous_les_types_existent() -> None:
    for nom in NOMS:
        assert hasattr(t, nom), nom


def test_defauts() -> None:
    p = Passage(passage_id="p", doc_id="d", text="x", anchor_ids=("a",))
    assert p.level == 0 and p.child_ids == ()
    assert Usage().cache_write_tokens == 0
    assert t.JUDGED_CRITERIA == ("correctness", "completeness", "faithfulness")
    a = t.ArchAnswer(text="x", abstained=False)
    assert a.retrieval_method == "ranked" and a.invalid_citations == 0
    ans = Answer(
        text="x", abstained=False, answer_id="i", question_id="q", config_id="c", status="ok"
    )
    assert ans.condition == "standard" and ans.phase == "base" and ans.tier is None


def _modeles() -> list[type[BaseModel]]:
    return [
        v for v in vars(t).values()
        if isinstance(v, type) and issubclass(v, BaseModel) and v is not BaseModel
        and v.__module__ == t.__name__
    ]  # fmt: skip


def test_modeles_geles_et_stricts() -> None:
    modeles = _modeles()
    assert len(modeles) >= 17
    for m in modeles:
        assert m.model_config.get("frozen") is True, m.__name__
        assert m.model_config.get("extra") == "forbid", m.__name__


def test_champ_inconnu_et_affectation_refuses() -> None:
    with pytest.raises(ValidationError):
        Usage(input_tokens=1, inconnu=2)  # type: ignore[call-arg]
    u = Usage()
    with pytest.raises(ValidationError):
        u.input_tokens = 3  # type: ignore[misc]


def test_resolve_markdown_et_pdf() -> None:
    c = _corpus()
    assert (
        c.resolve("docs/a.md", None, ("Histoire", "Fondation"))
        == "aaaa111122223333#h/histoire/fondation"
    )
    assert c.resolve("docs/b.pdf", 2, ()) == "bbbb111122223333#p2"


def test_resolve_absent() -> None:
    c = _corpus()
    assert c.resolve("docs/a.md", None, ("Inconnu",)) is None
    assert c.resolve("docs/b.pdf", 9, ()) is None
    assert c.resolve("docs/zz.md", None, ("Histoire",)) is None
    assert c.resolve("docs/a.md", None, ()) is None


def test_anchor_text_concatene_dans_l_ordre() -> None:
    c = _corpus()
    assert c.anchor_text("aaaa111122223333#h/histoire/fondation") == "Un\n\nDeux"
    assert c.anchor_text("bbbb111122223333#p2") == "p2a\n\np2b"
    assert c.anchor_text("bbbb111122223333#p9") == ""
    assert c.anchor_text("inconnu#p1") == ""


def test_decimal_serialise_en_chaine_et_relecture() -> None:
    r = LLMResult(
        text="x", usage=Usage(input_tokens=3), cost=Decimal("0.0012"),
        cost_uncached=Decimal("0.0012"), currency="USD", latency_s=0.5, from_cache=False,
    )  # fmt: skip
    d = r.model_dump(mode="json")
    assert d["cost"] == "0.0012" and isinstance(d["cost"], str)
    assert LLMResult.model_validate(d) == r


def test_answer_aller_retour_json() -> None:
    p = Passage(passage_id="p", doc_id="d", text="x", anchor_ids=("a",))
    ans = Answer(
        text="x", abstained=False, answer_id="i", question_id="q", config_id="c", status="ok",
        retrieved=(t.ScoredPassage(passage=p, score=1.0, rank=1),),
        citations=(t.Citation(anchor_id="a"),),
    )  # fmt: skip
    assert Answer.model_validate(ans.model_dump(mode="json")) == ans


def _profil(n: int = 1000) -> CorpusProfile:
    return CorpusProfile(
        corpus_id="c", fingerprint="f", parser="p", tokenizer="o200k_base", n_documents=2,
        n_tokens=n, mean_tokens_per_document=n / 2, heading_depth_max=2, heading_depth_mean=1.0,
        link_density=0.0, table_share=0.0, images_per_document=0.0, dominant_lang="fr",
        langs={"fr": 2}, formats={"markdown": 2}, volatility="low",
    )  # fmt: skip


def _catalogue(tokenizer: str, facteur: str) -> Any:
    entree = SimpleNamespace(tokenizer=tokenizer, token_factor=Decimal(facteur))
    return SimpleNamespace(get=lambda _id: entree)


def test_tokens_for() -> None:
    assert _profil().tokens_for("m", _catalogue("reference", "1.2")) == 1000
    assert _profil().tokens_for("m", _catalogue("approx", "1.2")) == 1200
