"""Correctif fix-arbitrages-8-3-8-8 : arbitrages d'Anaël du 2026-10-19 sur 8.3 restés non codés
(AC 2, AC 3 de la spec). `all_failed` (AC 1) est couvert par `test_story_8_3.py` (test mis à
jour)."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.llm.providers.fake import FakeProvider, default_output
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.execute import run_experiment

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
BM25 = {"id": "bm25", "architecture": "bm25_only"}
CONTEXTE_LONG = {
    "id": "contexte-long",
    "architecture": "long_context",
    "params": {"generator": {"name": "llm", "params": {"max_tokens": 99000}}},
}


def _experience(tmp_path: Path, **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-fix-8-3-8-8",
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


# --- AC 2 : une Configuration seulement inapplicable n'est pas une erreur ----------


def test_configuration_entierement_inapplicable_nest_pas_all_failed(
    tmp_path: Path, wl_home: Path
) -> None:
    """Une seule Configuration, inapplicable à toutes les Questions (fenêtre de contexte) :
    ni `ok` ni `error`, donc ni `all_failed` ni `completed_with_errors` (règle confirmée par
    Anaël le 2026-10-19 ; `core/bilan.py::causes_execution` et `RunOutcome.all_failed` déjà
    conformes, ce test fige le comportement bout en bout)."""
    res = _wl(str(_experience(tmp_path, configurations=[CONTEXTE_LONG])))
    assert res.exit_code == 0, res.output
    dossier = _un_run(wl_home)
    manifeste = _manifeste(dossier)
    assert manifeste["status"] == "completed" and manifeste["causes"] == []
    assert manifeste["answers"] == {"ok": 0, "error": 0, "inapplicable": 2}
    assert "all_failed" not in res.output and "Aucune Réponse valide" not in res.output


# --- AC 3 : max_error_rate relevable à la reprise ----------


def _faux_deuxieme_question_en_erreur_deterministe() -> FakeProvider:
    """La 2e Question distincte posée échoue (sortie non conforme) à chaque appel, y compris
    reposée à la reprise (erreur déterministe, cf. story 8.3) ; la 1re réussit toujours."""
    vues: list[str] = []

    def generer(request: LLMRequest) -> str:
        question = request.inputs["question"]
        if question not in vues:
            vues.append(question)
        if len(vues) >= 2 and question == vues[1]:
            return "pas du JSON"
        return default_output("generate", request.inputs)

    faux = FakeProvider()
    faux.script("generate", "generate", generer)
    return faux


def test_max_error_rate_relevable_a_la_reprise(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`max_error_rate` suit désormais la règle des plafonds (`budget`, AC 2 de la 4.8) : relevé
    dans l'Expérience, il est accepté à `--reprendre` (empreinte exceptée) et consigné dans
    `resumptions` (AC 3 de fix-arbitrages-8-3-8-8)."""
    _avec_faux(monkeypatch, _faux_deuxieme_question_en_erreur_deterministe())
    chemin = _experience(tmp_path)
    res = _wl(str(chemin))
    assert res.exit_code == 1, res.output
    dossier = _un_run(wl_home)
    manifeste = _manifeste(dossier)
    assert manifeste["status"] == "completed_with_errors"
    assert {c["cause"] for c in manifeste["causes"]} == {"error_rate"}
    assert manifeste["answers"]["ok"] == 1 and manifeste["answers"]["error"] == 1

    chemin_releve = _experience(tmp_path, max_error_rate=0.6)
    res = _wl(str(chemin_releve), "--reprendre", dossier.name)
    assert res.exit_code == 0, res.output
    manifeste = _manifeste(dossier)
    assert manifeste["status"] == "completed" and manifeste["causes"] == []
    assert manifeste["answers"]["ok"] == 1 and manifeste["answers"]["error"] == 1
    assert len(manifeste["resumptions"]) == 1
    assert manifeste["resumptions"][0]["max_error_rate"] == 0.6


def test_max_error_rate_non_releve_refuse_un_autre_ecart(tmp_path: Path, wl_home: Path) -> None:
    """Sans relever `max_error_rate`, toute autre différence d'Expérience reste refusée (code 2) :
    la règle des plafonds ne dispense pas des autres contrôles de `verifier_reprise`."""
    chemin = _experience(tmp_path)
    res = _wl(str(chemin))
    assert res.exit_code == 0, res.output
    dossier = _un_run(wl_home)
    chemin_differente = _experience(tmp_path, seed=99)
    res = _wl(str(chemin_differente), "--reprendre", dossier.name)
    assert res.exit_code == 2, res.output
