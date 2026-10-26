"""Story 8.11 : `wl calibrer` avec des Juges `provider: anthropic` (SDK factice, aucun réseau)."""

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.errors import BudgetExceeded
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions
from wavelibrarian.llm.providers.anthropic import OUTIL_SORTIE, AnthropicProvider
from wavelibrarian.runner.calibrer import calibrer
from wavelibrarian.runner.rundir import read_answers
from wavelibrarian.scoring.panel import criteres_juges

RACINE = Path(__file__).resolve().parents[3]
MINI = RACINE / "corpora" / "minicorpus"
JUGES = ["claude-haiku-5-5", "claude-opus-5-5"]


def _experience(tmp_path: Path, nom: str = "exp.yaml", **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-8-11",
        "seed": 42,
        "profile": "test",
        "corpus": str(MINI / "corpus.yaml"),
        "questions": str(MINI / "questions.yaml"),
        "split": "dev",
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": [{"id": "bm25", "architecture": "bm25_only"}],
        **champs,
    }
    chemin = tmp_path / nom
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _annoter(dossier: Path, cible: Path) -> None:
    """Un annotateur, `yes` partout, sur toutes les Réponses de l'Exécution."""
    questions = {q.id: q for q in select_questions(io.load(MINI / "questions.yaml"), "dev")}
    lignes = [
        {"answer_id": a.answer_id, "criterion": c, "verdict": "yes"}
        for a in sorted(read_answers(dossier).values(), key=lambda a: a.answer_id)
        for c in criteres_juges(questions[a.question_id])
    ]
    cible.mkdir()
    texte = yaml.safe_dump({"annotator": "anael", "annotations": lignes}, allow_unicode=True)
    (cible / "anael.yaml").write_text(texte, encoding="utf-8")


class _SdkFactice:
    """Remplace `anthropic.Anthropic` : répond par l'outil imposé, `yes` à tout Critère."""

    def __init__(self) -> None:
        self.appels: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **corps: Any) -> Any:
        self.appels.append(corps)
        criteres = json.loads(corps["messages"][0]["content"])["criteria"]
        verdicts = {c: {"verdict": "yes", "justification": "ok"} for c in criteres}
        usage = SimpleNamespace(
            input_tokens=1000,
            output_tokens=300,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        bloc = SimpleNamespace(type="tool_use", input={"verdicts": verdicts})
        return SimpleNamespace(content=[bloc], usage=usage)


@pytest.fixture
def execution(tmp_path: Path, wl_home: Path) -> tuple[Path, Path]:
    exp = _experience(tmp_path)
    res = CliRunner().invoke(app, ["run", str(exp)])
    assert res.exit_code == 0, res.output
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return exp, dossier


def _exp_claude(tmp_path: Path, plafond: str) -> Path:
    return _experience(
        tmp_path,
        "claude.yaml",
        judges={"pool": JUGES, "panel_size": 2, "calibration_passes": 2},
        budget={"per_run": {"anthropic": {"amount": plafond, "currency": "USD"}}},
    )


def test_catalogue_opus_5_5_tarifs_et_absence_de_palier() -> None:
    e = load_catalog(None).get("claude-opus-5-5")
    assert (e.provider, e.family, e.kind) == ("anthropic", "claude", "api")
    assert (e.context_window, e.max_output_tokens) == (1_000_000, 128_000)
    assert e.accepts_temperature is False
    assert e.pricing is not None and e.pricing.tiers == ()
    assert e.pricing.per_mtok == {
        "input": Decimal("4"),
        "output": Decimal("20"),
        "cache_read": Decimal("0.20"),
        "cache_write": Decimal("5"),
        "cache_write_1h": Decimal("8"),
    }
    assert e.pricing.batch_per_mtok == {"input": Decimal("2"), "output": Decimal("10")}


def test_calibration_claude_sortie_structuree_cout_par_appel_et_pas_de_temperature(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path
) -> None:
    _, dossier = execution
    _annoter(dossier, tmp_path / "ann")
    sdk = _SdkFactice()
    exp = validate_file(_exp_claude(tmp_path, "10.00")).resolved
    res, chemin = calibrer(
        exp,
        tmp_path / "ann",
        dossier.name,
        wl_home=wl_home,
        providers={"anthropic": AnthropicProvider(client=sdk)},  # type: ignore[arg-type]
    )
    n_reponses = len({a for a in read_answers(dossier)})
    assert res.n_appels == n_reponses * 2 * 2  # 2 Juges × 2 passes
    assert set(res.donnees["judges"]) == set(JUGES)
    assert res.donnees["passes"] == 2
    assert chemin == dossier / "calibration.json"
    # Sortie structurée par l'outil imposé, sans `temperature` (modèles 5.x).
    for corps in sdk.appels:
        assert corps["tool_choice"] == {"type": "tool", "name": OUTIL_SORTIE}
        assert "verdicts" in corps["tools"][0]["input_schema"]["properties"]
        assert "extra_body" not in corps
    assert {c["model"] for c in sdk.appels} == set(JUGES)
    # Coût par appel : 1000 entrée + 300 sortie ; Haiku 0,00025 $, Opus 0,010 $.
    n = n_reponses * 2
    attendu = n * Decimal("0.00025") + n * Decimal("0.010")
    assert res.cout == {"USD": attendu}
    spans = [
        json.loads(ligne)
        for d in (wl_home / "hors-execution").iterdir()
        for ligne in (d / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    juges = [s for s in spans if s.get("wl.post") == "judging" and not s["wl.llm_cache_hit"]]
    assert {s["gen_ai.provider.name"] for s in juges} == {"anthropic"}
    assert {(s["gen_ai.request.model"], Decimal(str(s["wl.cost"]))) for s in juges} == {
        ("claude-haiku-5-5", Decimal("0.00025")),
        ("claude-opus-5-5", Decimal("0.010")),
    }


def test_plafond_anthropic_atteint_leve_budget_exceeded_et_n_ecrit_rien(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path
) -> None:
    _, dossier = execution
    _annoter(dossier, tmp_path / "ann")
    sdk = _SdkFactice()
    exp = validate_file(_exp_claude(tmp_path, "0.01")).resolved
    with pytest.raises(BudgetExceeded):
        calibrer(
            exp,
            tmp_path / "ann",
            dossier.name,
            wl_home=wl_home,
            providers={"anthropic": AnthropicProvider(client=sdk)},  # type: ignore[arg-type]
        )
    assert not (dossier / "calibration.json").exists()
    assert not (dossier / "calibration_verdicts.jsonl").exists()


def test_experience_livree_calibration_claude() -> None:
    r = validate_file(RACINE / "experiments" / "calibration-claude.yaml").resolved
    assert tuple(r.judges.pool or ()) == tuple(JUGES)
    assert (r.judges.panel_size, r.judges.calibration_passes) == (2, 2)
    plafond = r.budget.per_run["anthropic"]
    assert (plafond.amount, plafond.currency) == (Decimal("10.00"), "USD")
    assert {p for c in r.configurations for p in c.answer_producers} <= {
        "minicpm5:1b-q4_k_m",
        "granite4.2:3b",
    }
