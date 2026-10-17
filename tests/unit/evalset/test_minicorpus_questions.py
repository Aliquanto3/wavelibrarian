"""Jeu d'évaluation de référence du Mini-corpus (story 3.7)."""

import shutil
from pathlib import Path

import pytest
import yaml
from conftest import CONFORMANCE_QUESTION_ID
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import ParsedCorpus, Question
from wavelibrarian.corpus.scenario import corpus_apres
from wavelibrarian.evalset import check, freeze, io
from wavelibrarian.llm.providers.fake import _grade_relevance, _mots

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
QUESTIONS = RACINE / "questions.yaml"
SCENARIO = RACINE / "scenario" / "scenario.yaml"
TYPES_ATTENDUS = {
    "factual",
    "multi_hop",
    "global",
    "comparison",
    "temporal",
    "unanswerable",
    "knowledge_trap",
}


@pytest.fixture(scope="module")
def jeu() -> io.QuestionsFile:
    return io.load(QUESTIONS)


@pytest.fixture(scope="module")
def apres(minicorpus: ParsedCorpus) -> ParsedCorpus:
    return corpus_apres(minicorpus, SCENARIO, lang="fr")


def _utilisables(jeu: io.QuestionsFile) -> list[Question]:
    return [q for q in jeu.questions if q.status == "validated"]


def test_controle_complet_avec_scenario(
    jeu: io.QuestionsFile, minicorpus: ParsedCorpus, apres: ParsedCorpus
) -> None:
    res = check.controler(jeu, minicorpus, apres)
    assert not res.echec
    assert res.signalements == ()
    assert res.utilisables >= 40
    sans = check.controler(jeu, minicorpus)
    assert not sans.echec  # sans --scenario : les Questions `after` restent « non vérifiables »
    assert any("non vérifiables" in s.message for s in sans.signalements)


def test_commande_controler_avec_scenario() -> None:
    res = CliRunner().invoke(
        app,
        [
            "questions",
            "controler",
            str(QUESTIONS),
            "--corpus",
            str(RACINE / "corpus.yaml"),
            "--scenario",
            str(SCENARIO),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "Contrôle réussi." in res.output


def test_effectif_origine_et_cible(jeu: io.QuestionsFile) -> None:
    assert jeu.corpus_id == "minicorpus"
    assert jeu.target_count == 40
    valides = _utilisables(jeu)
    assert len(valides) >= 40
    assert all(q.status == "validated" for q in jeu.questions)
    assert all(
        q.origin == {"kind": "model", "name": "claude-code-dev-agent"} for q in jeu.questions
    )
    assert len({q.id for q in jeu.questions}) == len(jeu.questions)


def test_types_suivis_interlingues_et_scenario(jeu: io.QuestionsFile) -> None:
    types = {q.type for q in jeu.questions}
    assert types == TYPES_ATTENDUS  # tous, sauf `visual` et `numeric_aggregation`
    suivis = [q for q in jeu.questions if q.follow_up]
    assert len(suivis) >= 2 and all(q.history for q in suivis)
    assert all(not q.history for q in jeu.questions if not q.follow_up)
    assert sum(q.cross_lingual for q in jeu.questions) >= 2
    operations = {
        o["id"] for o in yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))["operations"]
    }
    cibles = [q for q in jeu.questions if q.scenario_target]
    assert len(cibles) >= 3
    assert all(q.scenario_target["operation"] in operations for q in cibles if q.scenario_target)


def test_interlingue_langue_de_la_question_differente_du_document(
    jeu: io.QuestionsFile, minicorpus: ParsedCorpus
) -> None:
    langue_doc = {d.source_path: d.lang for d in minicorpus.documents}
    for q in jeu.questions:
        if q.cross_lingual:
            assert all(langue_doc[a.doc] != q.lang for a in q.reference_anchors), q.id


def test_unanswerable_sans_ancrage_et_piege_ancre(jeu: io.QuestionsFile) -> None:
    inconnues = [q for q in jeu.questions if q.type == "unanswerable"]
    assert inconnues and all(not q.reference_anchors for q in inconnues)
    pieges = [q for q in jeu.questions if q.type == "knowledge_trap"]
    assert pieges and all(q.reference_anchors for q in pieges)


def test_questions_factuelles_courtes_et_page_de_pdf(jeu: io.QuestionsFile) -> None:
    factuelles = [q for q in jeu.questions if q.type == "factual"]
    assert sum(q.answer_form == "short" for q in factuelles) >= 5
    assert any(
        a.page is not None and a.doc.endswith(".pdf")
        for q in factuelles
        for a in q.reference_anchors
    )


def test_question_de_conformite(jeu: io.QuestionsFile, minicorpus: ParsedCorpus) -> None:
    q = next(q for q in jeu.questions if q.id == CONFORMANCE_QUESTION_ID)
    assert q.type == "factual" and len(q.reference_anchors) == 1 and not q.follow_up
    ref = q.reference_anchors[0]
    anchor_id = minicorpus.resolve(ref.doc, ref.page, tuple(ref.headings))
    assert anchor_id is not None
    texte = minicorpus.anchor_text(anchor_id)
    mots_q = _mots(q.text)
    assert len(mots_q & _mots(texte)) / len(mots_q) >= 0.8
    # Règle du Faux LLM `grade_relevance` (contracts.md §3) : seuil de 0,5 du Corrective RAG.
    score = _grade_relevance({"question": q.text, "passages": [texte]}).scores[0]  # type: ignore[attr-defined]
    assert score > 0.5
    # Au moins un mot de la question hors de l'Ancrage ne retire rien : le terme rare est présent
    # (BM25, faux embedder et `select_nodes` s'appuient sur ces mots communs).
    assert {"bram", "oskelle"} <= mots_q & _mots(texte)


def test_jeu_gele_graine_42_ratio_04(jeu: io.QuestionsFile) -> None:
    freeze.verify_frozen(jeu)
    assert jeu.freeze is not None
    assert jeu.freeze.seed == 42 and jeu.freeze.dev_ratio == 0.4
    assert all(q.split in ("dev", "test") for q in jeu.questions)
    for type_ in TYPES_ATTENDUS:
        n = sum(q.type == type_ for q in jeu.questions)
        dev = sum(q.type == type_ and q.split == "dev" for q in jeu.questions)
        assert dev == freeze.nb_dev(n, 0.4), type_


def test_regel_identique_ne_change_aucune_partie(jeu: io.QuestionsFile) -> None:
    again = freeze.geler(jeu, 0.4, 42)
    assert {q.id: q.split for q in again.questions} == {q.id: q.split for q in jeu.questions}


def test_modifier_une_question_dans_une_copie_est_refuse(tmp_path: Path) -> None:
    copie = tmp_path / "questions.yaml"
    shutil.copyfile(QUESTIONS, copie)
    freeze.verify_frozen(io.load(copie))  # la copie intacte passe
    brut = yaml.safe_load(copie.read_text(encoding="utf-8"))
    brut["questions"][3]["reference_answer"] = "Deux deniers par mesure"
    copie.write_text(yaml.safe_dump(brut, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(ConfigError, match="sha256"):
        freeze.verify_frozen(io.load(copie))


def test_reponses_factuelles_courtes_presentes_dans_leurs_ancrages(
    jeu: io.QuestionsFile, minicorpus: ParsedCorpus, apres: ParsedCorpus
) -> None:
    """Chaque mot d'une Réponse `short` factuelle (hors interlingue) figure dans ses Ancrages."""
    for q in jeu.questions:
        if q.type != "factual" or q.answer_form != "short" or q.cross_lingual:
            continue
        cible = q.scenario_target or {}
        corpus = apres if cible.get("state") == "after" else minicorpus
        textes = " ".join(
            corpus.anchor_text(aid)
            for a in q.reference_anchors
            if (aid := corpus.resolve(a.doc, a.page, tuple(a.headings))) is not None
        )
        manquants = _mots(q.reference_answer) - _mots(textes)
        assert not manquants, (q.id, manquants)


def test_questions_hors_scenario_sans_document_modifie_ou_supprime(
    jeu: io.QuestionsFile,
) -> None:
    """Toutes les Questions sont reposées après mise à jour (story 4.7) : sans `scenario_target`,
    une Question ne s'appuie sur aucun Document que le Scénario modifie ou supprime."""
    operations = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))["operations"]
    touches = {o["target"] for o in operations if o["op"] in ("modify", "delete")}
    # q-022 : feu à éclats allumé dans les deux versions du bulletin ; Réponse tirée du phare.
    stables = {"q-022"}
    fautives = [
        q.id
        for q in jeu.questions
        if q.scenario_target is None
        and q.id not in stables
        and any(a.doc in touches for a in q.reference_anchors)
    ]
    assert fautives == []
