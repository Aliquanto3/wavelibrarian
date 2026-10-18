"""Suite de conformité (story 4.14) : chaque Architecture du registre, profil `test`, Mini-corpus.

Paramétrée sur `registry.names("architecture")` après `discover()` : une Architecture ajoutée au
registre est vérifiée sans rien écrire ici. Ses Params viennent de ses Configurations dans
`experiments/mini-test.yaml` (par exemple `embedder: fake`, `search: global`) ; une Architecture
sans Configuration dans ce fichier échoue ici.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import CONFORMANCE_QUESTION_ID  # type: ignore[import-not-found]

from wavelibrarian import registry
from wavelibrarian.core.types import ArchAnswer, ParsedCorpus, Question, QuestionInput
from wavelibrarian.corpus.ingest import nom_parser_resolu, parsers_par_format
from wavelibrarian.corpus.scenario import appliquer_fichier
from wavelibrarian.evalset.io import load as charger_questions
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.architecture import ArchitectureBase
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.execute import passages_de_reference
from wavelibrarian.runner.index_cache import IndexCache, index_key

RACINE = Path(__file__).resolve().parents[2]
MINI_TEST = RACINE / "experiments" / "mini-test.yaml"
MINICORPUS = RACINE / "corpora" / "minicorpus"
DOCUMENT_SUPPRIME = "note-obsolete.md"  # op-3 du Scénario du Mini-corpus


def _cas() -> list[Any]:
    """Une entrée par (Architecture du registre, Configuration de `mini-test.yaml`) ; une
    Architecture sans Configuration y figure avec `None` et échoue."""
    registry.discover()
    confs = yaml.safe_load(MINI_TEST.read_text(encoding="utf-8"))["configurations"]
    cas: list[Any] = []
    for nom in registry.names("architecture"):
        siennes = [c for c in confs if c["architecture"] == nom]
        if not siennes:
            cas.append(pytest.param(nom, None, id=f"{nom}-sans-configuration"))
        for c in siennes:
            cas.append(pytest.param(nom, c.get("params", {}), id=f"{nom}-{c['id']}"))
    return cas


CAS = _cas()


@pytest.fixture(scope="module")
def questions() -> dict[str, Question]:
    return {q.id: q for q in charger_questions(MINICORPUS / "questions.yaml").questions}


@pytest.fixture
def ctx(tmp_path: Path, minicorpus: ParsedCorpus) -> Iterator[Context]:
    c = Context.from_profile(
        "test",
        wl_home=tmp_path / "wl",
        run_id="conformite",
        seed=42,
        providers={"fake": FakeProvider()},
    )
    c.parser = _parser(minicorpus)  # `auto` résolu comme le fait le runner
    with c:
        yield c


def _parser(corpus: ParsedCorpus) -> str:
    return nom_parser_resolu(parsers_par_format({d.format for d in corpus.documents}))


def _ancrages(corpus: ParsedCorpus) -> set[str]:
    return {a for d in corpus.documents for a in d.anchors}


def _entree(q: Question) -> QuestionInput:
    return QuestionInput(question_id=q.id, text=q.text, lang=q.lang, history=q.history)


def _repondre(ctx: Context, arch: ArchitectureBase, q: Question) -> ArchAnswer:
    with ctx.scope(post="query", question_id=q.id):
        return arch.answer(_entree(q))


def _citations_valides(reponse: ArchAnswer, ancrages: set[str]) -> None:
    hors = [c.anchor_id for c in reponse.citations if c.anchor_id not in ancrages]
    assert not hors, f"Citations hors du Corpus : {hors}"


class _Banc:
    def __init__(self, ctx: Context, nom: str, params: dict[str, Any] | None) -> None:
        assert params is not None, f"{nom} : aucune Configuration dans experiments/mini-test.yaml"
        self.ctx, self.nom, self.params = ctx, nom, params
        self.cache = IndexCache(ctx.wl_home)

    def fabrique(self, params: dict[str, Any] | None = None) -> ArchitectureBase:
        spec = ComponentSpec(name=self.nom, params=self.params if params is None else params)
        return self.ctx.build("architecture", spec)

    def indexer(self, corpus: ParsedCorpus) -> tuple[ArchitectureBase, str]:
        return self.cache.build(self.ctx, self.fabrique, corpus)


@pytest.mark.parametrize(("nom", "params"), CAS)
def test_conformite(
    nom: str,
    params: dict[str, Any] | None,
    ctx: Context,
    minicorpus: ParsedCorpus,
    questions: dict[str, Question],
) -> None:
    banc = _Banc(ctx, nom, params)
    ancrages = _ancrages(minicorpus)
    q = questions[CONFORMANCE_QUESTION_ID]

    # Indexation : dossier final avec manifeste, instance neuve chargée par le cache d'index.
    arch, cle = banc.indexer(minicorpus)
    assert banc.cache.has(cle)
    sans_cache = _repondre(ctx, arch, q)

    # Réponse citée sur la Question de conformité (sauf `retrieval_method: none`).
    _citations_valides(sans_cache, ancrages)
    if arch.capabilities.retrieval_method != "none":
        assert not sans_cache.abstained, f"{nom} s'abstient sur {q.id}"
        assert sans_cache.citations, f"{nom} : aucune Citation sur {q.id}"

    # Réponses identiques avec le cache d'index (index servi sans reconstruction).
    avec_cache, cle_bis = banc.indexer(minicorpus)
    assert cle_bis == cle
    assert _repondre(ctx, avec_cache, q).model_dump() == sans_cache.model_dump()

    # Abstention sur un contexte vide.
    with ctx.scope(post="query", question_id=q.id):
        vide = arch.answer_with_context(_entree(q), [])
    assert vide.abstained and not vide.citations

    # Condition contexte parfait : Passages de référence seuls, Citation parmi eux.
    reference = passages_de_reference(minicorpus, q)
    with ctx.scope(post="query", question_id=q.id):
        parfait = arch.answer_with_context(_entree(q), reference)
    attendus = {a for p in reference for a in p.anchor_ids}
    assert not parfait.abstained
    assert parfait.citations
    assert {c.anchor_id for c in parfait.citations} <= attendus

    # `index_key` : change avec un Param hors `query_params`, pas avec un `query_params` entier.
    gen = arch.params.generator  # type: ignore[attr-defined]
    autre_generateur = {"name": gen.name, "params": {**gen.params, "max_tokens": 777}}
    assert "generator" not in arch.query_params
    modifie = banc.fabrique({**banc.params, "generator": autre_generateur})
    assert index_key(minicorpus.fingerprint, modifie) != cle
    for champ in sorted(arch.query_params):
        valeur = getattr(arch.params, champ)
        if isinstance(valeur, int) and not isinstance(valeur, bool):
            requete = banc.fabrique({**banc.params, champ: valeur + 1})
            assert index_key(minicorpus.fingerprint, requete) == cle, champ


@pytest.mark.parametrize(("nom", "params"), CAS)
def test_mise_a_jour_ecarte_le_document_supprime(
    nom: str,
    params: dict[str, Any] | None,
    ctx: Context,
    minicorpus: ParsedCorpus,
    questions: dict[str, Question],
) -> None:
    """Scénario du Mini-corpus : après `update`, le Document supprimé n'apparaît ni dans les
    Passages retrouvés ni dans les Citations, sur la Question de conformité et sur celles dont
    l'Ancrage était dans ce Document."""
    banc = _Banc(ctx, nom, params)
    base_arch, cle = banc.indexer(minicorpus)
    del base_arch
    change, apres = appliquer_fichier(
        minicorpus, MINICORPUS / "scenario" / "scenario.yaml", lang="fr", parser=ctx.parser
    )
    (supprime,) = [d.doc_id for d in minicorpus.documents if d.source_path == DOCUMENT_SUPPRIME]
    assert change.removed == (supprime,)
    arch, cle_apres = banc.cache.build(
        ctx, banc.fabrique, apres, post="update", change=change, old_dir=banc.cache.path(cle)
    )
    assert cle_apres != cle
    ancrages = _ancrages(apres)
    visees = [questions[CONFORMANCE_QUESTION_ID]] + [
        q
        for q in questions.values()
        if any(r.doc == DOCUMENT_SUPPRIME for r in q.reference_anchors)
    ]
    assert len(visees) > 1
    for q in visees:
        reponse = _repondre(ctx, arch, q)
        _citations_valides(reponse, ancrages)
        for sp in reponse.retrieved:
            p = sp.passage
            assert p.doc_id != supprime, f"{q.id} : Passage du Document supprimé retrouvé"
            assert not any(a.startswith(f"{supprime}#") for a in p.anchor_ids), q.id
        assert not any(a.startswith(f"{supprime}#") for a in reponse.context_anchor_ids), q.id
