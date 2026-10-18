"""Story 4.9 : Critères automatiques et Panel de Juges dans l'Exécution (profil `test`)."""

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.components.judges.llm import LLMJudge
from wavelibrarian.core.errors import BudgetExceeded
from wavelibrarian.core.types import Criterion, Question
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions
from wavelibrarian.ports.components import JudgeInput
from wavelibrarian.runner.rundir import read_answers, read_panel, read_verdicts
from wavelibrarian.scoring.answer import exact_match

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
MODELES = Path(__file__).resolve().parents[3] / "src" / "wavelibrarian" / "defaults" / "models.yaml"
BM25 = {"id": "bm25", "architecture": "bm25_only"}
SANS_CONTEXTE = {"id": "sans-contexte", "architecture": "no_context"}
PANEL = {"fake-llm-c", "fake-llm-b"}  # réservoir [c, b, a] du profil test, Generator fake-llm-a
JUGES: tuple[Criterion, ...] = ("correctness", "completeness", "faithfulness")
Appel = tuple[str, str, tuple[str, ...], int, JudgeInput]


def _experience(tmp_path: Path, **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-4-9",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": [BM25],
        **champs,
    }
    chemin = tmp_path / "exp.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl(*args: str, code: int = 0) -> Any:
    # `--tolerer-erreurs` : Questions et Juges en échec scénarisés -> `completed_with_errors` (8.3)
    res = CliRunner().invoke(app, ["run", *args, "--tolerer-erreurs"])
    assert res.exit_code == code, res.output
    return res


def _un_run(wl_home: Path) -> Path:
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return dossier


def _questions() -> dict[str, Question]:
    return {q.id: q for q in select_questions(io.load(RACINE / "questions.yaml"), "dev")}


def _espion(
    monkeypatch: pytest.MonkeyPatch, avant: Callable[[int], None] | None = None
) -> list[Appel]:
    """Enregistre chaque appel d'un Juge : (modèle, Question, Critères, passe, item)."""
    appels: list[Appel] = []
    reel = LLMJudge.judge
    par_texte = {q.text: q.id for q in _questions().values()}

    def juge(self: LLMJudge, item: JudgeInput, criteria: Sequence[Criterion], pass_id: int) -> Any:
        if avant is not None:
            avant(len(appels))
        qid = par_texte[item.question]
        appels.append((self.model_id, qid, tuple(criteria), pass_id, item))
        return reel(self, item, criteria, pass_id)

    monkeypatch.setattr(LLMJudge, "judge", juge)
    return appels


def _spans(dossier: Path) -> list[dict[str, Any]]:
    lignes = (dossier / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(ligne) for ligne in lignes]


def _lignes(dossier: Path, nom: str) -> list[str]:
    return (dossier / nom).read_text(encoding="utf-8").splitlines()


# --- AC 3 : Panel, un appel par Réponse et par Juge, au poste judging ----------------------------


def test_panel_un_appel_par_reponse_et_par_juge_verdicts_et_panel(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appels = _espion(monkeypatch)
    _wl(str(_experience(tmp_path, configurations=[BM25, SANS_CONTEXTE])))
    dossier = _un_run(wl_home)
    questions = _questions()
    reponses = read_answers(dossier)
    assert len(reponses) == 2 * len(questions)
    assert {a.status for a in reponses.values()} == {"ok"}

    # Un appel par (Réponse, Juge), tous les Critères en une fois, au poste `judging`.
    assert len(appels) == 2 * len(reponses)
    assert {m for m, *_ in appels} == PANEL
    for _, qid, criteres, passe, _ in appels:
        attendus = JUGES if questions[qid].answer_form == "free" else JUGES[1:]
        assert criteres == attendus and passe == 0
    spans = [s for s in _spans(dossier) if s["wl.post"] == "judging"]
    assert len(spans) == len(appels) and {s["wl.kind"] for s in spans} == {"llm"}
    assert {s["wl.config_id"] for s in spans} == {"bm25", "sans-contexte"}
    assert {s["wl.question_id"] for s in spans} == set(questions)

    # Un Verdict par (answer_id, judge_model, criterion, pass_id), sans doublon.
    verdicts = read_verdicts(dossier)
    assert len(_lignes(dossier, "verdicts.jsonl")) == len(verdicts)
    for a in reponses.values():
        q = questions[a.question_id]
        attendus = JUGES if q.answer_form == "free" else JUGES[1:]
        juges = sorted(c for (i, m, c, _) in verdicts if i == a.answer_id and m in PANEL)
        assert juges == sorted(attendus * len(PANEL))
        auto = {c: v for (i, m, c, _), v in verdicts.items() if i == a.answer_id and m == "auto"}
        assert set(auto) == {"citation_correctness", "abstention_correctness"} | (
            {"correctness"} if q.answer_form == "short" else set()
        )
        assert auto["abstention_correctness"].verdict == (a.abstained == (q.type == "unanswerable"))
        if q.answer_form == "short":
            assert auto["correctness"].verdict == exact_match(q.reference_answer, a.text)

    # panel.jsonl : un verdict majoritaire par (answer_id, criterion), Juges admissibles reportés.
    panel = read_panel(dossier)
    assert len(panel) == 5 * len(reponses)
    assert len(_lignes(dossier, "panel.jsonl")) == len(panel)
    for (aid, critere), ligne in panel.items():
        votes = [v.verdict for (i, _, c, _), v in verdicts.items() if i == aid and c == critere]
        assert ligne.verdict == (sum(votes) * 2 > len(votes)) and not ligne.tie
        auto_seul = all(m == "auto" for (i, m, c, _) in verdicts if i == aid and c == critere)
        assert set(ligne.judges) == (set() if auto_seul else PANEL)


def test_juge_recoit_les_textes_des_ancrages_et_le_contexte_du_generator(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appels = _espion(monkeypatch)
    _wl(str(_experience(tmp_path)))
    reponses = {a.question_id: a for a in read_answers(_un_run(wl_home)).values()}
    questions = _questions()
    assert appels
    for _, qid, _, _, item in appels:
        assert item.context_texts == reponses[qid].context_texts
        assert item.answer_text == reponses[qid].text
        assert item.reference_answer == questions[qid].reference_answer
        # Un Ancrage créé par le Scénario n'existe pas dans le Corpus de base : pas de texte.
        cible = questions[qid].scenario_target or {}
        attendus = 0 if cible.get("state") == "after" else len(questions[qid].reference_anchors)
        assert len(item.reference_texts) == attendus and all(item.reference_texts)
    assert any(item.context_texts for *_, item in appels)  # bm25 : contexte non vide


def test_juges_exclus_par_la_calibration_ne_sont_pas_appeles(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalogue = tmp_path / "models.yaml"
    d = (
        "  - {id: fake-llm-d, provider: fake, family: fake-d, kind: api, modality: llm,\n"
        "     context_window: 100000, max_output_tokens: 2048, tokenizer: approx,\n"
        "     prompt_cache: true, pricing: {date: 2026-10-17, currency: USD, per_mtok:\n"
        '     {input: "1.00", output: "2.00", cache_read: "0.10", cache_write: "1.25"}}}\n'
    )
    catalogue.write_text(MODELES.read_text(encoding="utf-8").rstrip("\n") + "\n" + d, "utf-8")
    calibration = tmp_path / "calibration.json"
    calibration.write_text(json.dumps({"judges": {"fake-llm-c": {"excluded": True}}}), "utf-8")
    appels = _espion(monkeypatch)
    chemin = _experience(
        tmp_path,
        catalog=str(catalogue),
        judges={
            "pool": ["fake-llm-c", "fake-llm-b", "fake-llm-d", "fake-llm-a"],
            "excluded_from": str(calibration),
        },
    )
    _wl(str(chemin))
    assert {m for m, *_ in appels} == {"fake-llm-b", "fake-llm-d"}
    panel = read_panel(_un_run(wl_home))
    assert {m for p in panel.values() for m in p.judges} == {"fake-llm-b", "fake-llm-d"}


# --- AC 4 : aucune Réponse non `ok` n'est jugée --------------------------------------------------


def test_inapplicable_non_jugee(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appels = _espion(monkeypatch)
    longue = {
        "id": "contexte-long",
        "architecture": "long_context",
        "params": {"generator": {"name": "llm", "params": {"max_tokens": 99000}}},
    }
    _wl(str(_experience(tmp_path, configurations=[BM25, longue], max_questions=4)))
    dossier = _un_run(wl_home)
    inapplicables = {i for i, a in read_answers(dossier).items() if a.status == "inapplicable"}
    assert len(inapplicables) == 4
    assert len(appels) == 2 * 4  # les 4 Réponses ok de bm25 seulement, deux Juges chacune
    assert not inapplicables & {k[0] for k in read_verdicts(dossier)}
    assert not inapplicables & {k[0] for k in read_panel(dossier)}


def test_budget_exceeded_non_juge(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appels = _espion(monkeypatch)
    plafond = {"per_run": {"fake": {"amount": "0.000000001", "currency": "USD"}}}
    _wl(str(_experience(tmp_path, budget=plafond, max_questions=3)), code=3)
    dossier = _un_run(wl_home)
    assert {a.status for a in read_answers(dossier).values()} == {"budget_exceeded"}
    assert not appels and not read_verdicts(dossier) and not read_panel(dossier)


def test_erreur_non_jugee(tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from wavelibrarian.architectures.bm25_only import Bm25Only

    reel = Bm25Only.answer

    def peut_echouer(self: Any, question: Any) -> Any:
        if question.question_id == "q-002":
            raise RuntimeError("panne simulée")
        return reel(self, question)

    monkeypatch.setattr(Bm25Only, "answer", peut_echouer)
    appels = _espion(monkeypatch)
    _wl(str(_experience(tmp_path, max_questions=3)))
    dossier = _un_run(wl_home)
    erreurs = [a for a in read_answers(dossier).values() if a.status == "error"]
    assert [a.question_id for a in erreurs] == ["q-002"]
    assert "q-002" not in {qid for _, qid, *_ in appels} and len(appels) == 2 * 2
    assert erreurs[0].answer_id not in {k[0] for k in read_verdicts(dossier)}


# --- AC 5 : reprise du jugement ------------------------------------------------------------------


def test_reprise_apres_arret_pendant_le_jugement_ne_demande_que_les_cles_absentes(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    n = 4
    etat = {"coupe": True}

    def coupe(deja: int) -> None:
        if etat["coupe"] and deja == 3:  # 2 Juges : la 2e Réponse n'est jugée que par le premier
            raise BudgetExceeded("plafond simulé pendant le jugement")

    chemin = _experience(tmp_path, max_questions=n)
    appels = _espion(monkeypatch, coupe)
    _wl(str(chemin), code=3)
    dossier = _un_run(wl_home)
    assert json.loads((dossier / "manifest.json").read_text("utf-8"))["status"] == "budget_exceeded"
    assert len(read_answers(dossier)) == n and len(appels) == 3
    agreges = {k[0] for k in read_panel(dossier)}
    assert len(agreges) == 1  # seule la 1re Réponse est agrégée
    faits = {(m, q) for m, q, *_ in appels}

    etat["coupe"] = False
    appels.clear()
    _wl(str(chemin), "--reprendre", dossier.name, code=0)
    # 2 Juges x 4 Réponses = 8 appels en tout : 3 faits, 5 à la reprise, jamais deux fois.
    assert len(appels) == 2 * n - 3
    vus = {(m, q) for m, q, *_ in appels}
    assert len(vus) == len(appels) and not vus & faits
    assert json.loads((dossier / "manifest.json").read_text("utf-8"))["status"] == "completed"
    verdicts = read_verdicts(dossier)
    assert len(_lignes(dossier, "verdicts.jsonl")) == len(verdicts)
    assert len(read_panel(dossier)) == 5 * n
    assert len(_lignes(dossier, "panel.jsonl")) == 5 * n
    # Relancer une Exécution terminée ne juge plus rien.
    _wl(str(chemin), "--reprendre", dossier.name, code=0)
    assert len(appels) == 2 * n - 3


def _juges_scenarises(monkeypatch: pytest.MonkeyPatch, sortie: Callable[[str], Any]) -> None:
    """`LLMJudge.judge` remplacé : `sortie(modele)` rend le verdict (bool) ou lève."""

    def juge(self: LLMJudge, item: JudgeInput, criteria: Sequence[Criterion], pass_id: int) -> Any:
        oui = sortie(self.model_id)
        return {c: (oui, f"{self.model_id} {c}") for c in criteria}

    monkeypatch.setattr(LLMJudge, "judge", juge)


def test_juges_contradictoires_egalite_no_et_tie_dans_panel(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _juges_scenarises(monkeypatch, lambda m: m == "fake-llm-b")  # b : oui, c : non
    _wl(str(_experience(tmp_path, max_questions=3)))
    dossier = _un_run(wl_home)
    jugees = [p for p in read_panel(dossier).values() if p.judges]
    assert jugees and all(p.tie and not p.verdict for p in jugees)
    assert all(set(p.judges) == PANEL for p in jugees)
    automatiques = [p for p in read_panel(dossier).values() if not p.judges]
    assert automatiques and not any(p.tie for p in automatiques)


def test_juge_en_echec_compte_au_manifeste_puis_repris(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sortie(modele: str) -> bool:
        if modele == "fake-llm-c":
            raise RuntimeError("Juge en panne simulée")
        return True

    _juges_scenarises(monkeypatch, sortie)
    chemin = _experience(tmp_path, max_questions=2)
    res = _wl(str(chemin))
    dossier = _un_run(wl_home)
    manifeste = json.loads((dossier / "manifest.json").read_text("utf-8"))
    questions = _questions()
    attendu = sum(
        len(JUGES) - (questions[a.question_id].answer_form == "short")
        for a in read_answers(dossier).values()
    )
    assert manifeste["status"] == "completed_with_errors" and manifeste["unjudged"] == attendu
    assert "sans verdict de panel" in res.output
    assert not [p for p in read_panel(dossier).values() if p.judges]

    _juges_scenarises(monkeypatch, lambda m: True)
    _wl(str(chemin), "--reprendre", dossier.name)  # completed mais non jugé : rejugé
    manifeste = json.loads((dossier / "manifest.json").read_text("utf-8"))
    assert manifeste["status"] == "completed" and manifeste["unjudged"] == 0
    assert len([p for p in read_panel(dossier).values() if p.judges]) == attendu
    res = _wl(str(chemin), "--reprendre", dossier.name)  # désormais rien à reprendre
    assert "rien à reprendre" in res.output
