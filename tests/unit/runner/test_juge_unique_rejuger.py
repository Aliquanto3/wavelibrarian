"""Story 9.5 (revue) : Juge unique calibré dans `panels_de` et `wl rejuger` (Faux LLM)."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import empreinte
from wavelibrarian.runner.execute import panels_de
from wavelibrarian.runner.rundir import read_panel, read_verdicts

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
TROIS = ("correctness", "completeness", "faithfulness")
UNIQUE = {"pool": ["fake-llm-b", "fake-llm-c"], "panel_size": 1, "excluded_from": "cal.json"}


def _calibration(dossier: Path, criteres: tuple[str, ...] = TROIS) -> None:
    fiche = {"excluded": False, "criteria": {c: {"kappa": 0.8} for c in criteres}}
    donnees = {"judges": {"fake-llm-b": {"excluded": True}, "fake-llm-c": fiche}}
    (dossier / "cal.json").write_text(json.dumps(donnees), encoding="utf-8")


def _toutes_courtes(questions: Path) -> None:
    """Toutes les Questions en `answer_form: short` (réponse de référence `42`), puis re-Gel."""
    doc = io.load(questions)
    nouvelles = tuple(
        q.model_copy(update={"answer_form": "short", "reference_answer": "42"})
        for q in doc.questions
    )
    doc = doc.model_copy(update={"questions": nouvelles})
    assert doc.freeze is not None
    gel = doc.freeze.model_copy(update={"sha256": empreinte(doc)})
    io.save(questions, doc.model_copy(update={"freeze": gel}))


def _experience(dossier: Path, nom: str, juges: dict[str, Any]) -> Path:
    donnees = {
        "experiment_id": "exp-9-5",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(dossier / "questions.yaml"),
        "split": "dev",
        "max_questions": 3,
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "judges": juges,
        "configurations": [{"id": "bm25", "architecture": "bm25_only"}],
    }
    chemin = dossier / nom
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl(*args: str, code: int = 0) -> Any:
    res = CliRunner().invoke(app, list(args))
    assert res.exit_code == code, res.output
    return res


def test_panels_de_juge_unique_saute_l_exclu(tmp_path: Path, wl_home: Path) -> None:
    shutil.copyfile(RACINE / "questions.yaml", tmp_path / "questions.yaml")
    _calibration(tmp_path)
    resolue = validate_file(_experience(tmp_path, "exp.yaml", UNIQUE), wl_home).resolved
    assert panels_de(resolue) == {"bm25": ("fake-llm-c",)}
    _calibration(tmp_path, ("completeness", "faithfulness"))  # calibration changée après coup
    with pytest.raises(ConfigError, match="'fake-llm-c'.*'correctness'"):
        panels_de(resolue)


def test_rejuger_avec_juge_unique_questions_courtes(tmp_path: Path, wl_home: Path) -> None:
    shutil.copyfile(RACINE / "questions.yaml", tmp_path / "questions.yaml")
    _toutes_courtes(tmp_path / "questions.yaml")
    _calibration(tmp_path)
    _wl("run", str(_experience(tmp_path, "source.yaml", {})))
    (source,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    _wl("rejuger", source.name, str(_experience(tmp_path, "rejuge.yaml", UNIQUE)))
    (cible,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir() and d != source]

    verdicts = read_verdicts(cible)
    juges = {m for (_, m, _, _) in verdicts} - {"auto"}
    assert juges == {"fake-llm-c"}  # l'exclu en tête du réservoir n'est jamais appelé
    # Questions courtes : `correctness` par correspondance exacte, jamais par le Juge.
    assert not any(m != "auto" and c == "correctness" for (_, m, c, _) in verdicts)
    panel = read_panel(cible)
    notes = [v for v in panel.values() if v.judges]
    assert notes and all(v.judges == ("fake-llm-c",) and not v.tie for v in notes)
    rapport = (cible / "report" / "report.md").read_text(encoding="utf-8")
    assert "Juge unique calibré : `fake-llm-c` ;" in rapport
