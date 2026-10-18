"""Story 8.3 : statut `completed_with_errors` de `wl run` (P9), en Faux LLM (profil `test`)."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.core.bilan import causes_execution, decrire_cause
from wavelibrarian.core.errors import BudgetExceeded
from wavelibrarian.llm.providers.fake import FakeProvider, default_output
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.execute import run_experiment
from wavelibrarian.runner.resume import deja_terminee
from wavelibrarian.runner.rundir import read_answers, read_panel

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
BM25 = {"id": "bm25", "architecture": "bm25_only"}
# Les 4 Configurations du run mini-cpu d'avant correctif, en Faux LLM (verifications-reelles
# 2026-10-18, 2e série).
MINI_CPU = [
    BM25,
    {"id": "rag-naif", "architecture": "naive_rag", "params": {"embedder": {"name": "fake"}}},
    {"id": "raptor", "architecture": "raptor", "params": {"embedder": {"name": "fake"}}},
    {"id": "pageindex", "architecture": "pageindex"},
]


def _experience(tmp_path: Path, **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-8-3",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "max_questions": 2,
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": [BM25],
        **champs,
    }
    chemin = tmp_path / "exp.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl(*args: str) -> Any:
    return CliRunner().invoke(app, ["run", *args])


def _un_run(wl_home: Path) -> Path:
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return dossier


def _manifeste(dossier: Path) -> dict[str, Any]:
    return json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))


def _avec_faux(monkeypatch: pytest.MonkeyPatch, faux: FakeProvider) -> None:
    from wavelibrarian import cli

    def lancer(*a: Any, **k: Any) -> Any:
        return run_experiment(*a, providers={"fake": faux}, **k)

    monkeypatch.setattr(cli, "run_experiment", lancer)


def _faux_mini_cpu_avant_correctif() -> FakeProvider:
    """PageIndex : sélection non conforme (0 `ok` sur 2) ; Generator non conforme sur la 2e
    Question sauf pour la 1re Configuration (bm25 2/2, rag-naif et raptor 1/2) ; Juges non
    conformes partout (panel vide)."""
    vues: list[str] = []
    vus_deux: set[str] = set()

    def generer(request: LLMRequest) -> str:
        question = request.inputs["question"]
        if question not in vues:
            vues.append(question)
        elif question == vues[1] or question in vus_deux:
            vus_deux.add(question)
            return "pas du JSON"
        return default_output("generate", request.inputs)

    faux = FakeProvider()
    faux.script("select_nodes", "pageindex.select.*", "pas du JSON")
    faux.script("judge", "*", "pas du JSON")
    faux.script("generate", "generate", generer)
    return faux


# --- règle des causes (core/bilan.py) ----------


def test_taux_d_erreur_strictement_au_dessus_du_seuil() -> None:
    confs = ["a", "b", "c", "d"]
    reponses = {
        "a": {"ok": 4, "error": 1},  # 1/5 = 0,2 : pas au-dessus de 0,2
        "b": {"ok": 3, "error": 2},  # 2/5 = 0,4 > 0,2
        "c": {"inapplicable": 3},  # seulement inapplicable : pas en erreur
        "d": {"error": 2, "inapplicable": 1},  # 2/2 : aucune `ok`, taux 1,0
    }
    assert causes_execution(reponses, {"a": 3}, 0.2, confs) == [
        {"config_id": "a", "cause": "unjudged", "count": 3},
        {"config_id": "b", "cause": "error_rate", "count": 2},
        {"config_id": "d", "cause": "no_ok_answer", "count": 2},
        {"config_id": "d", "cause": "error_rate", "count": 2},
    ]
    assert causes_execution(reponses, {}, 1.0, ["b"]) == []  # 0,4 n'est pas au-dessus de 1
    assert causes_execution({"b": {"ok": 1, "error": 1}}, {}, 0.0, ["b"]) == [
        {"config_id": "b", "cause": "error_rate", "count": 1}
    ]
    texte = decrire_cause({"config_id": "b", "cause": "error_rate", "count": 2}, 0.2)
    assert texte == "`b` : 2 Réponse(s) en `error`, taux au-dessus de `max_error_rate` (20 %)"


# --- validation de max_error_rate ----------


@pytest.mark.parametrize("valeur", [1.5, -0.1, "0.2", True])
def test_max_error_rate_hors_bornes_refuse_code_2(
    tmp_path: Path, wl_home: Path, valeur: Any
) -> None:
    res = _wl(str(_experience(tmp_path, max_error_rate=valeur)))
    assert res.exit_code == 2, res.output
    assert "max_error_rate" in res.output
    assert not (wl_home / "runs").exists()


def test_max_error_rate_defaut_0_2_dans_l_experience_resolue(tmp_path: Path) -> None:
    from wavelibrarian.config.validate import validate_file

    assert validate_file(_experience(tmp_path)).resolved.max_error_rate == 0.2
    assert validate_file(_experience(tmp_path, max_error_rate=1)).resolved.max_error_rate == 1.0


# --- scénarios Faux LLM : avant correctif et sain ----------


def test_reproduction_mini_cpu_avant_correctif_completed_with_errors_code_1(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _avec_faux(monkeypatch, _faux_mini_cpu_avant_correctif())
    chemin = _experience(tmp_path, configurations=MINI_CPU)
    res = _wl(str(chemin))
    assert res.exit_code == 1, res.output
    dossier = _un_run(wl_home)
    manifeste = _manifeste(dossier)
    assert manifeste["status"] == "completed_with_errors"

    par_conf: dict[str, list[str]] = {}
    for a in read_answers(dossier).values():
        par_conf.setdefault(a.config_id, []).append(a.status)
    assert {c: sorted(s) for c, s in par_conf.items()} == {
        "bm25": ["ok", "ok"],
        "rag-naif": ["error", "ok"],
        "raptor": ["error", "ok"],
        "pageindex": ["error", "error"],
    }
    assert not [p for p in read_panel(dossier).values() if p.judges]  # panel vide
    causes = {(c["config_id"], c["cause"]): c["count"] for c in manifeste["causes"]}
    assert causes.pop(("pageindex", "no_ok_answer")) == 2
    assert causes.pop(("pageindex", "error_rate")) == 2
    assert causes.pop(("rag-naif", "error_rate")) == 1  # 1/2 > 0,2
    assert causes.pop(("raptor", "error_rate")) == 1
    non_jugees = {c: n for (c, cause), n in causes.items() if cause == "unjudged"}
    assert set(non_jugees) == {"bm25", "rag-naif", "raptor"} and set(causes) == {
        (c, "unjudged") for c in non_jugees
    }
    assert sum(non_jugees.values()) == manifeste["unjudged"] > 0

    # Résumé en français, Configurations et causes nommées.
    assert "completed_with_errors" in res.output
    assert "pageindex : aucune Réponse ok (2 en error)" in res.output
    assert "Critère(s) sans verdict de panel" in res.output
    assert f"--reprendre {dossier.name}" in res.output

    # Le Rapport commence par l'avertissement (après le titre).
    rapport = (dossier / "report" / "report.md").read_text(encoding="utf-8").splitlines()
    assert rapport[0].startswith("# Rapport")
    assert rapport[2].startswith("> **Exécution terminée avec erreurs")
    bandeau = "\n".join(rapport[2:12])
    assert "> - `pageindex` : aucune Réponse `ok` (2 en `error`)" in bandeau
    assert "`rag-naif`" in bandeau and "`raptor`" in bandeau and "(20 %)" in bandeau
    assert not deja_terminee(wl_home, dossier.name)


def test_tolerer_erreurs_code_0_meme_resume(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _avec_faux(monkeypatch, _faux_mini_cpu_avant_correctif())
    res = _wl(str(_experience(tmp_path, configurations=MINI_CPU)), "--tolerer-erreurs")
    assert res.exit_code == 0, res.output
    assert _manifeste(_un_run(wl_home))["status"] == "completed_with_errors"
    assert "completed_with_errors" in res.output
    assert "pageindex : aucune Réponse ok (2 en error)" in res.output


def test_scenario_sain_completed_code_0(tmp_path: Path, wl_home: Path) -> None:
    res = _wl(str(_experience(tmp_path, configurations=MINI_CPU)))
    assert res.exit_code == 0, res.output
    dossier = _un_run(wl_home)
    manifeste = _manifeste(dossier)
    assert manifeste["status"] == "completed" and manifeste["causes"] == []
    assert manifeste["answers"] == {"ok": 8, "error": 0, "inapplicable": 0}
    assert "completed_with_errors" not in res.output
    rapport = (dossier / "report" / "report.md").read_text(encoding="utf-8")
    assert "> **" not in rapport.split("## Expérience")[0]


# --- plafond : budget_exceeded et code 3 priment ----------


def test_plafond_prime_sur_les_erreurs(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian.architectures.bm25_only import Bm25Only

    reel = Bm25Only.answer

    def repondre(self: Any, question: Any) -> Any:
        if question.question_id == "q-002":
            raise RuntimeError("panne simulée")
        if question.question_id == "q-011":
            raise BudgetExceeded("plafond simulé")
        return reel(self, question)

    monkeypatch.setattr(Bm25Only, "answer", repondre)
    res = _wl(str(_experience(tmp_path, max_questions=3)), "--tolerer-erreurs")
    assert res.exit_code == 3, res.output
    manifeste = _manifeste(_un_run(wl_home))
    assert manifeste["status"] == "budget_exceeded" and manifeste["causes"] == []
    assert manifeste["answers"]["error"] == 1


# --- reprise : Questions en error reposées, Critères sans verdict rejugés ----------


def test_reprise_repose_les_erreurs_et_rejuge(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian.architectures.bm25_only import Bm25Only
    from wavelibrarian.components.judges.llm import LLMJudge

    etat = {"panne": True}
    reel_answer, reel_juge = Bm25Only.answer, LLMJudge.judge
    posees: list[str] = []

    def repondre(self: Any, question: Any) -> Any:
        posees.append(question.question_id)
        if etat["panne"] and question.question_id == "q-002":
            raise RuntimeError("panne simulée")
        return reel_answer(self, question)

    def juger(self: Any, *a: Any, **k: Any) -> Any:
        if etat["panne"]:
            raise RuntimeError("Juge en panne simulée")
        return reel_juge(self, *a, **k)

    monkeypatch.setattr(Bm25Only, "answer", repondre)
    monkeypatch.setattr(LLMJudge, "judge", juger)
    chemin = _experience(tmp_path, max_questions=3)
    assert _wl(str(chemin)).exit_code == 1
    dossier = _un_run(wl_home)
    manifeste = _manifeste(dossier)
    assert manifeste["status"] == "completed_with_errors" and manifeste["unjudged"] > 0
    assert {c["cause"] for c in manifeste["causes"]} == {"error_rate", "unjudged"}
    assert sorted(posees) == ["q-002", "q-004", "q-011"]

    etat["panne"] = False
    posees.clear()
    res = _wl(str(chemin), "--reprendre", dossier.name)
    assert res.exit_code == 0, res.output
    assert posees == ["q-002"]  # seule la Question en `error` est reposée
    manifeste = _manifeste(dossier)
    assert manifeste["status"] == "completed" and manifeste["unjudged"] == 0
    assert manifeste["causes"] == [] and manifeste["answers"]["error"] == 0
    assert {a.status for a in read_answers(dossier).values()} == {"ok"}
    assert deja_terminee(wl_home, dossier.name)
    assert "rien à reprendre" in _wl(str(chemin), "--reprendre", dossier.name).output
