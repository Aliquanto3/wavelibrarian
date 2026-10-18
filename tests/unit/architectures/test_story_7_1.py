"""Story 7.1 : Architecture `raptor` (arbre de résumés, recherche à plat)."""

import json
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures._passages import lire_passages
from wavelibrarian.architectures.raptor import Raptor
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import ParsedCorpus, Passage, QuestionInput
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.architecture import CorpusChange
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.runner.context import Context as RunCtx

PETITS = {"name": "fixed_tokens", "params": {"size": 40, "overlap": 5}}


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


def _arch(ctx: RunCtx, **params: Any) -> Any:
    params.setdefault("embedder", {"name": "fake"})
    params.setdefault("chunker", PETITS)
    return ctx.build("architecture", ComponentSpec(name="raptor", params=params))


def _indexer(ctx: RunCtx, corpus: ParsedCorpus, dossier: Path, **params: Any) -> Any:
    arch = _arch(ctx, **params)
    with ctx.scope(post="indexing"):
        arch.index(corpus, dossier)
    return arch


def _spans_llm(ctx: RunCtx) -> list[dict[str, Any]]:
    chemin = ctx.run_dir / "traces.jsonl"
    lignes = chemin.read_text(encoding="utf-8").splitlines() if chemin.exists() else []
    return [s for s in map(json.loads, lignes) if s.get("wl.kind") == "llm"]


def _question() -> QuestionInput:
    return QuestionInput(question_id="q-001", text="Que sait-on de la guilde Orvane ?", lang="fr")


def test_arbre_noeuds_groupes_profondeur_et_identifiants(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert registry.get("architecture", "raptor") is Raptor
    assert Raptor.capabilities.incremental_update is False
    _indexer(ctx, minicorpus, tmp_path / "i")
    passages = lire_passages(tmp_path / "i")
    par_id = {p.passage_id: p for p in passages}
    feuilles = [p for p in passages if p.level == 0]
    noeuds = [p for p in passages if p.level >= 1]
    assert len(feuilles) > 10 and noeuds
    assert max(p.level for p in noeuds) <= 3
    assert {p.level for p in noeuds} >= {1, 2}
    for n in noeuds:
        assert n.child_ids
        assert all(c in par_id and par_id[c].level == n.level - 1 for c in n.child_ids)
        assert n.passage_id == sha16("node", "raptor", str(n.level), *sorted(n.child_ids))
        enfants = [par_id[c] for c in n.child_ids]
        assert set(n.anchor_ids) == {a for e in enfants for a in e.anchor_ids}
        docs = {e.doc_id for e in enfants}
        assert n.doc_id == (next(iter(docs)) if len(docs) == 1 else None)
    assert any(n.doc_id is None for n in noeuds)
    # tailles de groupe : entre group_min et group_max, sauf un niveau trop petit (un seul groupe)
    for niveau in {n.level for n in noeuds}:
        du_niveau = [n for n in noeuds if n.level == niveau]
        total = sum(len(n.child_ids) for n in du_niveau)
        for n in du_niveau:
            assert len(n.child_ids) <= 10
            assert len(n.child_ids) >= 5 or (len(du_niveau) == 1 and total < 5)
        # chaque nœud du niveau inférieur est dans exactement un groupe
        assert total == len([p for p in passages if p.level == niveau - 1])


def test_groupes_toleres_sous_group_min_et_profondeur_bornee(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "a", max_depth=1)
    assert max(p.level for p in lire_passages(tmp_path / "a")) == 1
    _indexer(ctx, minicorpus, tmp_path / "b", group_min=40, group_max=79, max_depth=2)
    passages_b = lire_passages(tmp_path / "b")
    noeuds = [p for p in passages_b if p.level >= 1]
    assert noeuds and max(n.level for n in noeuds) <= 2
    for niveau in {n.level for n in noeuds}:
        du_niveau = [n for n in noeuds if n.level == niveau]
        total = sum(len(n.child_ids) for n in du_niveau)
        assert total == sum(1 for p in passages_b if p.level == niveau - 1)
        for n in du_niveau:  # aucun niveau exempté, le niveau 1 compris
            assert len(n.child_ids) <= 79
            assert len(n.child_ids) >= 40 or (len(du_niveau) == 1 and total < 40)
    with pytest.raises(Exception, match="group_max"):
        _arch(ctx, group_min=5, group_max=8)


def test_indexation_deterministe(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> None:
    _indexer(ctx, minicorpus, tmp_path / "a")
    _indexer(ctx, minicorpus, tmp_path / "b")
    assert (tmp_path / "a" / "passages.jsonl").read_bytes() == (
        tmp_path / "b" / "passages.jsonl"
    ).read_bytes()


def test_appels_summarize_step_et_poste(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    spans = [s for s in _spans_llm(ctx) if s["wl.step"].startswith("raptor.")]
    niveaux = {p.level for p in lire_passages(tmp_path / "i")} - {0}
    assert {s["wl.step"] for s in spans} == {f"raptor.summarize.level{n}" for n in niveaux}
    assert {s["wl.post"] for s in spans} == {"indexing"}
    n_noeuds = sum(1 for p in lire_passages(tmp_path / "i") if p.level >= 1)
    assert len(spans) == n_noeuds


def test_recherche_a_plat_niveaux_et_citation_vers_les_feuilles(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _indexer(ctx, minicorpus, tmp_path / "i", k=40)
    arch = _arch(ctx, k=40)
    arch.load(tmp_path / "i")
    ctx.provider.script(  # type: ignore[attr-defined]
        "generate", "generate*", '{"answer": "R", "citations": ["S1", "S2"], "abstain": false}'
    )
    with ctx.scope(post="query", question_id="q-001"):
        rep = arch.answer(_question())
    niveaux = {s.passage.level for s in rep.retrieved}
    assert len(rep.retrieved) == 40 and niveaux >= {
        0,
        1,
    }  # nœuds et feuilles dans le même classement
    existants = {a for d in minicorpus.documents for a in d.anchors}
    assert rep.citations
    assert {c.anchor_id for c in rep.citations} <= existants
    attendues = {a for s in rep.retrieved[:2] for a in s.passage.anchor_ids}
    assert {c.anchor_id for c in rep.citations} == attendues
    # pertinence par recouvrement d'Ancrages : un nœud couvre les Ancrages de ses feuilles
    par_id = arch._index.passages

    def ancrages_des_feuilles(p: Passage) -> set[str]:
        if p.level == 0:
            return set(p.anchor_ids)
        return {a for c in p.child_ids for a in ancrages_des_feuilles(par_id[c])}

    assert max(p.level for p in par_id.values()) >= 2
    for p in par_id.values():  # tous les niveaux, pas seulement le niveau 1
        if p.level >= 1:
            assert set(p.anchor_ids) == ancrages_des_feuilles(p)
            assert set(p.anchor_ids) <= existants


def test_update_reconstruit_et_retire_le_document_supprime(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    docs = list(minicorpus.documents)
    supprime = docs[0]
    apres = minicorpus.model_copy(update={"documents": tuple(docs[1:])})
    _indexer(ctx, minicorpus, tmp_path / "v1")
    maj = _arch(ctx)
    with ctx.scope(post="update"):
        maj.update(
            CorpusChange(removed=(supprime.doc_id,)), apres, tmp_path / "v1", tmp_path / "v2"
        )
    passages = lire_passages(tmp_path / "v2")
    assert any(p.level >= 1 for p in passages)
    interdits = set(supprime.anchors)
    assert not interdits & {a for p in passages for a in p.anchor_ids}
    assert supprime.doc_id not in {p.doc_id for p in passages}
    maj_spans = [s for s in _spans_llm(ctx) if s["wl.post"] == "update"]
    assert maj_spans and all(s["wl.step"].startswith("raptor.summarize.level") for s in maj_spans)
    neuve = _arch(ctx)
    neuve.load(tmp_path / "v2")
    assert {p.passage_id for p in passages} == set(neuve._index.passages)


def test_retriever_non_dense_refuse_avant_tout_appel(ctx: RunCtx) -> None:
    with pytest.raises(ConfigError, match="dense"):
        _arch(ctx, retriever={"name": "lexical"})
    assert _spans_llm(ctx) == []


def test_group_max_un_refuse_et_chaque_niveau_reduit(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    with pytest.raises(Exception, match="group_max"):
        _arch(ctx, group_min=1, group_max=1)
    _indexer(ctx, minicorpus, tmp_path / "i", group_min=1, group_max=2, max_depth=10)
    passages = lire_passages(tmp_path / "i")
    comptes = [
        sum(1 for p in passages if p.level == n) for n in range(max(p.level for p in passages) + 1)
    ]
    assert all(b < a for a, b in zip(comptes, comptes[1:], strict=False))
    assert comptes[-1] == 1  # arrêt dès qu'il reste un seul nœud, avant max_depth


def test_feuille_unique_sans_resume(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> None:
    doc = minicorpus.documents[0]
    un = minicorpus.model_copy(update={"documents": (doc,)})
    _indexer(
        ctx,
        un,
        tmp_path / "i",
        chunker={"name": "fixed_tokens", "params": {"size": 40000, "overlap": 5}},
        group_max=2,
        group_min=1,
    )
    passages = lire_passages(tmp_path / "i")
    assert len(passages) == 1 and passages[0].level == 0
    assert [s for s in _spans_llm(ctx) if s["wl.step"].startswith("raptor.")] == []


def test_fenetre_du_modele_de_resume(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> None:
    # fake-llm-a : fenêtre de 100 000 tokens ; 400 enfants de 300 tokens n'y tiennent pas
    grand = {"name": "fixed_tokens", "params": {"size": 300, "overlap": 5}}
    with pytest.raises(ConfigError, match="fenêtre"):
        _arch(ctx, chunker=grand, group_max=400)
    assert _spans_llm(ctx) == []
    # contrôle avant chaque appel : aucun prompt tronqué en silence
    arch = _arch(ctx)
    arch._fenetre = lambda: 300
    with ctx.scope(post="indexing"), pytest.raises(ConfigError, match="fenêtre"):
        arch.index(minicorpus, tmp_path / "i")
    assert [s for s in _spans_llm(ctx) if s["wl.step"].startswith("raptor.")] == []
