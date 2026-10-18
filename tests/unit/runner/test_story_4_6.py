"""Story 4.6 : Condition contexte parfait et Paliers de volume (profil `test`, Faux LLM)."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.components.generators.llm import LLMGenerator
from wavelibrarian.core.types import Passage, Question, QuestionInput
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions
from wavelibrarian.ports.architecture import ArchitectureBase
from wavelibrarian.runner.execute import chemins_requis

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
BASELINES = [
    {"id": "sans-contexte", "architecture": "no_context"},
    {"id": "contexte-long", "architecture": "long_context"},
    {"id": "bm25", "architecture": "bm25_only"},
]
# Les 13 Documents des Ancrages de référence du split `dev` ne tiennent pas dans le Palier de 5 :
# les tests de Paliers limitent donc le nombre de Questions.
TROIS = 3


def _experience(tmp_path: Path, **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-4-6",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": BASELINES,
        **champs,
    }
    chemin = tmp_path / "exp.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl_run(chemin: Path, wl_home: Path, code: int = 0) -> Path | None:
    avant = set((wl_home / "runs").glob("*")) if (wl_home / "runs").exists() else set()
    res = CliRunner().invoke(app, ["run", str(chemin)])
    assert res.exit_code == code, res.output
    nouveau = set((wl_home / "runs").glob("*")) - avant if (wl_home / "runs").exists() else set()
    if code != 0:
        assert not nouveau
        return None
    (dossier,) = nouveau
    return dossier


def _jsonl(chemin: Path) -> list[dict[str, Any]]:
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


def _documents() -> list[str]:
    return [d.source_path for d in declare(RACINE / "corpus.yaml").documents]


def _apres_scenario() -> set[str]:
    """Questions dont l'Ancrage n'existe qu'après le Scénario (story 4.7)."""
    return {q.id for q in _dev() if q.scenario_target is not None}


def _dev() -> list[Question]:
    return sorted(select_questions(io.load(RACINE / "questions.yaml"), "dev"), key=lambda q: q.id)


@pytest.fixture
def espion(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Espionne `answer_with_context` (ce que l'Architecture reçoit) et le Generator `llm`."""
    vu: dict[str, list[Any]] = {"contexte": [], "generation": []}
    original_ctx = ArchitectureBase.answer_with_context
    original_gen = LLMGenerator.generate

    def avec_contexte(self: Any, question: Any, passages: Any) -> Any:
        vu["contexte"].append((self.name, self.ctx.parser, question, list(passages)))
        return original_ctx(self, question, passages)

    def generer(self: Any, question: Any, context: Any) -> Any:
        vu["generation"].append((self._cache_system, question, context))
        return original_gen(self, question, context)

    monkeypatch.setattr(ArchitectureBase, "answer_with_context", avec_contexte)
    # `long_context` redéfinit `answer_with_context` : on espionne aussi sa version
    from wavelibrarian.architectures.long_context import LongContext

    original_lc = LongContext.answer_with_context

    def lc_contexte(self: Any, question: Any, passages: Any) -> Any:
        vu["contexte"].append((self.name, self.ctx.parser, question, list(passages)))
        return original_lc(self, question, passages)

    monkeypatch.setattr(LongContext, "answer_with_context", lc_contexte)
    monkeypatch.setattr(LLMGenerator, "generate", generer)
    return vu


# --- AC 1 : contexte parfait --------------------------------------------------------------------


def test_contexte_parfait_passages_de_reference_et_aucune_reference_a_l_architecture(
    tmp_path: Path, wl_home: Path, espion: dict[str, list[Any]]
) -> None:
    dossier = _wl_run(_experience(tmp_path, conditions=["standard", "perfect_context"]), wl_home)
    assert dossier is not None
    reponses = _jsonl(dossier / "answers.jsonl")
    dev = _dev()
    ids = [q.id for q in dev]
    parfait = [a for a in reponses if a["condition"] == "perfect_context"]
    standard = [a for a in reponses if a["condition"] == "standard"]
    assert len(parfait) == len(standard) == 3 * len(dev)
    apres = _apres_scenario()
    assert apres  # le Jeu de dev contient au moins une Question de Scénario
    # Ancrage créé par le Scénario : introuvable dans le Corpus de base, Question en `error`.
    for a in parfait:
        assert a["retrieval_method"] == "provided"
        attendu = "error" if a["question_id"] in apres else "ok"
        assert a["status"] == attendu, a
    assert all("Ancrage introuvable" in a["error"] for a in parfait if a["status"] == "error")
    assert {a["question_id"] for a in parfait} == set(ids)
    # Chaque ligne a son answer_id (condition comprise) : aucune collision entre Conditions.
    assert len({a["answer_id"] for a in reponses}) == len(reponses)
    assert all("/perfect_context/all/base/" in a["answer_id"] for a in parfait)

    # Ce que l'Architecture a reçu : QuestionInput et Passages, jamais la référence.
    appels = espion["contexte"]
    assert len(appels) == 3 * (len(dev) - len(apres))
    par_id = {q.id: q for q in dev}
    parse_par_parser: dict[str, Any] = {}
    for _nom, parser, question, passages in appels:
        assert type(question) is QuestionInput
        assert all(type(p) is Passage and p.level == 0 for p in passages)
        q = par_id[question.question_id]
        champs = set(QuestionInput.model_fields)
        assert not {"reference_answer", "reference_anchors"} & champs
        if q.type == "unanswerable":
            assert passages == []  # Contexte vide
            continue
        if parser not in parse_par_parser:
            parse_par_parser[parser] = ingest(
                declare(RACINE / "corpus.yaml"), parser, wl_home=wl_home
            )
        parse = parse_par_parser[parser]
        attendus = [parse.resolve(r.doc, r.page, r.headings) for r in q.reference_anchors]
        assert [p.anchor_ids[0] for p in passages] == list(dict.fromkeys(attendus))
        assert [p.text for p in passages] == [parse.anchor_text(a) for a in dict.fromkeys(attendus)]
    # Le Generator ne reçoit que QuestionInput et le Contexte construit des Passages ci-dessus.
    assert espion["generation"]
    for _cache, question, _context in espion["generation"]:
        assert type(question) is QuestionInput
        assert set(vars(question)) <= set(QuestionInput.model_fields)


def test_question_unanswerable_recoit_un_contexte_vide(
    tmp_path: Path, wl_home: Path, espion: dict[str, list[Any]]
) -> None:
    unanswerable = next(q for q in _dev() if q.type == "unanswerable")
    _wl_run(_experience(tmp_path, conditions=["perfect_context"]), wl_home)
    vides = [
        (nom, p)
        for nom, _parser, question, p in espion["contexte"]
        if question.question_id == unanswerable.id
    ]
    assert len(vides) == 3 and all(p == [] for _, p in vides)


def test_long_context_en_contexte_parfait_sans_cache_du_system(
    tmp_path: Path, wl_home: Path, espion: dict[str, list[Any]]
) -> None:
    """Report 4.2 : le contexte parfait de `long_context` passe sans cache du system."""
    _wl_run(
        _experience(
            tmp_path,
            conditions=["standard", "perfect_context"],
            configurations=[{"id": "contexte-long", "architecture": "long_context"}],
        ),
        wl_home,
    )
    n_dev = len(_dev())
    gens = espion["generation"]
    n_parfait = n_dev - len(_apres_scenario())
    assert len(gens) == n_dev + n_parfait
    assert [c for c, *_ in gens[:n_dev]] == [True] * n_dev  # standard : system en cache
    assert [c for c, *_ in gens[n_dev:]] == [False] * n_parfait  # contexte parfait : sans cache
    assert all(len(ctx.blocks) <= 3 for _, _, ctx in gens[n_dev:])  # pas le Corpus entier


def test_contexte_parfait_sans_index_ni_check(tmp_path: Path, wl_home: Path) -> None:
    dossier = _wl_run(_experience(tmp_path, conditions=["perfect_context"]), wl_home)
    assert dossier is not None
    spans = _jsonl(dossier / "traces.jsonl")
    assert not [s for s in spans if s["name"] == "index"]
    assert {s["wl.condition"] for s in spans} == {"perfect_context"}
    assert not list((wl_home / "index").glob("*"))  # aucun index construit


# --- AC 2 : Paliers `all` ------------------------------------------------------------------------


def test_paliers_all_sous_corpus_index_et_lignes_distincts(tmp_path: Path, wl_home: Path) -> None:
    dossier = _wl_run(
        _experience(
            tmp_path,
            tier="all",
            max_questions=TROIS,
            configurations=[{"id": "bm25", "architecture": "bm25_only"}],
        ),
        wl_home,
    )
    assert dossier is not None
    reponses = _jsonl(dossier / "answers.jsonl")
    assert len(reponses) == 3 * TROIS
    assert sorted({a["tier"] for a in reponses}) == [5, 10, 20]
    assert len({a["answer_id"] for a in reponses}) == len(reponses)
    assert all(f"/standard/{a['tier']}/base/" in a["answer_id"] for a in reponses)
    # Spans : `wl.tier` partout, un index distinct par Palier.
    spans = _jsonl(dossier / "traces.jsonl")
    assert {s["wl.tier"] for s in spans if s["name"] == "answer"} == {5, 10, 20}
    index = [s for s in spans if s["name"] == "index"]
    assert sorted(s["wl.tier"] for s in index) == [5, 10, 20]
    assert len({s["wl.index_key"] for s in index}) == 3
    # Chaque Palier est indexé sur son sous-corpus : ses Documents, requis compris.
    parse = ingest(declare(RACINE / "corpus.yaml"), "markdown+pdf_text", wl_home=wl_home)
    par_doc = {d.doc_id: d.source_path for d in parse.documents}
    requis = set(chemins_requis(_dev()[:TROIS], _documents()))
    docs_par_palier: dict[int, set[str]] = {}
    for s in index:
        lignes = _jsonl(wl_home / "index" / s["wl.index_key"] / "passages.jsonl")
        docs_par_palier[s["wl.tier"]] = {par_doc[ligne["doc_id"]] for ligne in lignes}
    for taille, docs in docs_par_palier.items():
        assert len(docs) <= taille and requis <= docs
    assert docs_par_palier[5] <= docs_par_palier[10] <= docs_par_palier[20]  # emboîtés


def test_required_paths_sont_les_documents_des_ancrages_de_reference() -> None:
    dev = _dev()
    attendus = {a.doc for q in dev for a in q.reference_anchors}
    assert "chronique-1415.md" in attendus  # créé par le Scénario, absent du Corpus de base
    requis = chemins_requis(dev, _documents())
    assert set(requis) == attendus & set(_documents())
    assert list(requis) == sorted(requis) and len(requis) == 12
    assert chemins_requis([]) == ()


def test_paliers_trop_petits_pour_les_documents_requis_refuses_en_2(
    tmp_path: Path, wl_home: Path
) -> None:
    res = CliRunner().invoke(app, ["run", str(_experience(tmp_path, tier="all"))])
    assert res.exit_code == 2, res.output
    assert "Documents requis" in res.output
    assert not (wl_home / "runs").exists()


def test_paliers_et_contexte_parfait_combines(tmp_path: Path, wl_home: Path) -> None:
    dossier = _wl_run(
        _experience(
            tmp_path,
            tier=10,
            max_questions=TROIS,
            conditions=["standard", "perfect_context"],
            configurations=[{"id": "bm25", "architecture": "bm25_only"}],
        ),
        wl_home,
    )
    assert dossier is not None
    reponses = _jsonl(dossier / "answers.jsonl")
    assert {(a["condition"], a["tier"]) for a in reponses} == {
        ("standard", 10),
        ("perfect_context", 10),
    }


def test_palier_inapplicable_long_context_est_juge_sur_son_sous_corpus(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`check()` reçoit le Profil du Palier : la clé d'applicabilité porte le Palier."""
    from wavelibrarian.architectures.long_context import LongContext
    from wavelibrarian.ports.architecture import Applicability

    def check(self: Any, profile: Any) -> Applicability:
        return Applicability(applicable=profile.n_documents >= 10, reason="trop petit")

    monkeypatch.setattr(LongContext, "check", check)
    dossier = _wl_run(
        _experience(
            tmp_path,
            tier="all",
            max_questions=TROIS,
            configurations=[{"id": "contexte-long", "architecture": "long_context"}],
        ),
        wl_home,
    )
    assert dossier is not None
    applicabilite = json.loads((dossier / "applicability.json").read_text(encoding="utf-8"))
    assert list(applicabilite) == ["contexte-long@5"]
    assert applicabilite["contexte-long@5"]["tier"] == 5
    statuts = {(a["tier"], a["status"]) for a in _jsonl(dossier / "answers.jsonl")}
    assert statuts == {(5, "inapplicable"), (10, "ok"), (20, "ok")}


# --- AC 3 : un seul Palier ; taille non déclarée --------------------------------------------------


def test_palier_unique_seul_ce_palier_s_execute(tmp_path: Path, wl_home: Path) -> None:
    dossier = _wl_run(
        _experience(
            tmp_path,
            tier=10,
            max_questions=TROIS,
            configurations=[{"id": "bm25", "architecture": "bm25_only"}],
        ),
        wl_home,
    )
    assert dossier is not None
    reponses = _jsonl(dossier / "answers.jsonl")
    assert len(reponses) == TROIS and {a["tier"] for a in reponses} == {10}
    spans = _jsonl(dossier / "traces.jsonl")
    assert {s["wl.tier"] for s in spans} == {10}


def test_taille_non_declaree_refusee_en_2_avant_tout_appel(tmp_path: Path, wl_home: Path) -> None:
    res = CliRunner().invoke(app, ["run", str(_experience(tmp_path, tier=7))])
    assert res.exit_code == 2, res.output
    assert "tiers.sizes" in res.output and "7" in res.output
    assert not (wl_home / "runs").exists()


def test_corpus_sans_tiers_refuse_en_2(tmp_path: Path, wl_home: Path) -> None:
    donnees = yaml.safe_load((RACINE / "corpus.yaml").read_text(encoding="utf-8"))
    del donnees["tiers"]
    donnees["path"] = str(RACINE / donnees["path"])
    corpus = tmp_path / "corpus.yaml"
    corpus.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    res = CliRunner().invoke(
        app, ["run", str(_experience(tmp_path, tier="all", corpus=str(corpus)))]
    )
    assert res.exit_code == 2, res.output
    assert "tiers" in res.output
    assert not (wl_home / "runs").exists()
    shutil.rmtree(tmp_path / "x", ignore_errors=True)


def test_sans_palier_ni_condition_le_comportement_est_inchange(
    tmp_path: Path, wl_home: Path
) -> None:
    dossier = _wl_run(_experience(tmp_path), wl_home)
    assert dossier is not None
    reponses = _jsonl(dossier / "answers.jsonl")
    assert {(a["condition"], a["tier"]) for a in reponses} == {("standard", None)}
    assert len(reponses) == 3 * len(_dev())
