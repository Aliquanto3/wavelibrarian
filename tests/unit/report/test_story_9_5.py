"""Story 9.5 : Rapport d'une Exécution à Juge unique calibré et à Juges factices."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.report.generer import _juge_unique, _juges, generer_rapport
from wavelibrarian.report.lecture import charger

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"


def _executer(tmp_path: Path, wl_home: Path, juges: dict[str, Any]) -> Path:
    donnees = {
        "experiment_id": "exp-9-5",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "max_questions": 3,
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "judges": juges,
        "configurations": [{"id": "bm25", "architecture": "bm25_only"}],
    }
    chemin = tmp_path / "exp.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    res = CliRunner().invoke(app, ["run", str(chemin)])
    assert res.exit_code == 0, res.output
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return dossier


def test_rapport_juge_unique_calibre_avec_kappas(tmp_path: Path, wl_home: Path) -> None:
    kappas = {"correctness": 0.81, "completeness": 0.72, "faithfulness": 0.65}
    fiche = {"excluded": False, "criteria": {c: {"kappa": k} for c, k in kappas.items()}}
    cal = tmp_path / "cal.json"
    cal.write_text(
        json.dumps({"run_id": "cal-1", "kappa_threshold": 0.6, "judges": {"fake-llm-c": fiche}}),
        encoding="utf-8",
    )
    dossier = _executer(
        tmp_path,
        wl_home,
        {"pool": ["fake-llm-c"], "panel_size": 1, "excluded_from": str(cal)},
    )
    md = (generer_rapport(dossier) / "report.md").read_text(encoding="utf-8")
    assert "Juge unique calibré : `fake-llm-c`" in md
    assert "sans règle de majorité ni égalité" in md
    assert "Kappas juge-humain : completeness 0,72, correctness 0,81, faithfulness 0,65." in md
    assert "Qualité non interprétable" not in md  # Generator factice aussi


def test_rapport_panel_de_deux_sans_mention_de_juge_unique(tmp_path: Path, wl_home: Path) -> None:
    dossier = _executer(tmp_path, wl_home, {})
    md = (generer_rapport(dossier) / "report.md").read_text(encoding="utf-8")
    assert "Juge unique calibré" not in md
    assert "Qualité non interprétable" not in md


def test_rapport_juges_factices_avec_generator_reel(tmp_path: Path, wl_home: Path) -> None:
    dossier = _executer(tmp_path, wl_home, {})
    ex = charger(dossier)
    reelles = tuple(
        c.model_copy(update={"answer_producers": ("claude-haiku-5-5",)})
        for c in ex.experience.configurations
    )
    md = "\n".join(
        _juges(replace(ex, experience=ex.experience.model_copy(update={"configurations": reelles})))
    )
    assert "**Qualité non interprétable : Juges factices.**" in md


def test_rapport_juge_unique_par_configuration_et_fiche_sans_kappas(
    tmp_path: Path, wl_home: Path
) -> None:
    """Revue 9.5 : Generators de Familles différentes, un Juge unique par Configuration ; une
    fiche sans `criteria` n'est pas « calibration absente »."""
    trois = {c: {"kappa": 0.7} for c in ("correctness", "completeness", "faithfulness")}
    cal = tmp_path / "cal.json"
    cal.write_text(
        json.dumps({"judges": {"fake-llm-c": {"excluded": False, "criteria": trois}}}),
        encoding="utf-8",
    )
    juges = {"pool": ["fake-llm-c"], "panel_size": 1, "excluded_from": str(cal)}
    ex = charger(_executer(tmp_path, wl_home, juges))
    fiche = {"excluded": False, "criteria": {"completeness": {"kappa": 0.7}}}
    cal.write_text(
        json.dumps({"judges": {"fake-llm-b": {"excluded": False}, "fake-llm-c": fiche}}),
        encoding="utf-8",
    )
    (conf,) = ex.experience.configurations
    deux = (conf, conf.model_copy(update={"id": "autre"}))
    ex = replace(ex, experience=ex.experience.model_copy(update={"configurations": deux}))
    lignes = _juge_unique(ex, {"bm25": {"fake-llm-c"}, "autre": {"fake-llm-b"}, "x": set()})
    md = "\n".join(lignes)
    assert "Juge unique calibré : `fake-llm-b` (Configurations `autre`)" in md
    assert "aucun kappa par Critère dans la calibration" in md
    assert "Juge unique calibré : `fake-llm-c` (Configurations `bm25`)" in md
    assert "completeness 0,70" in md
    assert "calibration absente" in "\n".join(_juge_unique(ex, {"bm25": {"inconnu"}}))
