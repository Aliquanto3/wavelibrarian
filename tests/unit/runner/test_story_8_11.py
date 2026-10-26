"""Story 8.11 : `wl calibrer` avec des Juges `provider: anthropic` (SDK factice, aucun réseau)."""

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.errors import BudgetExceeded
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions
from wavelibrarian.llm.providers.anthropic import (
    CONSIGNE_OUTIL,
    OUTIL_SORTIE,
    AnthropicProvider,
)
from wavelibrarian.runner.calibrer import calibrer, fichier_verdicts
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


def _http_400(message: str) -> anthropic.BadRequestError:
    requete = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.BadRequestError(
        message, response=httpx2.Response(400, request=requete), body=None
    )


class _SdkFactice:
    """Remplace `anthropic.Anthropic` : répond par l'outil, `yes` à tout Critère.

    Reprend les refus réels relevés le 2026-10-26 sur `claude-opus-5-5` (HTTP 400) : `tool_choice`
    tool/any et `temperature`. `tronquer` : Réponses (par `answer`) pour lesquelles Opus rend un
    bloc `thinking` seul (`stop_reason: max_tokens`), sans outil.
    """

    def __init__(self, tronquer: frozenset[str] = frozenset()) -> None:
        self.appels: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)
        self._tronquer = tronquer

    def _create(self, **corps: Any) -> Any:
        self.appels.append(corps)
        if "temperature" in corps.get("extra_body", {}):
            raise _http_400("`temperature` is deprecated for this model.")
        if corps["model"] == "claude-opus-5-5" and corps["tool_choice"]["type"] in ("tool", "any"):
            raise _http_400('tool_choice: type "tool" and "any" are not supported for this model.')
        entree = json.loads(corps["messages"][0]["content"])
        verdicts = {c: {"verdict": "yes", "justification": "ok"} for c in entree["criteria"]}
        usage = SimpleNamespace(
            input_tokens=1000,
            output_tokens=300,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        if corps["model"] == "claude-opus-5-5" and entree["answer"] in self._tronquer:
            bloc = SimpleNamespace(type="thinking", thinking="...")
            return SimpleNamespace(content=[bloc], usage=usage, stop_reason="max_tokens")
        bloc = SimpleNamespace(type="tool_use", input={"verdicts": verdicts})
        return SimpleNamespace(content=[bloc], usage=usage, stop_reason="tool_use")


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
    assert (e.forced_tool_choice, e.thinking_reserve_tokens) == (False, 4000)
    haiku = load_catalog(None).get("claude-haiku-5-5")
    assert (haiku.forced_tool_choice, haiku.thinking_reserve_tokens) == (True, 0)
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
    # Sortie structurée par l'outil, sans `temperature` (modèles 5.x) : imposé pour Haiku,
    # `auto` avec consigne pour Opus (thinking adaptatif), budget de sortie relevé de 4000.
    for corps in sdk.appels:
        assert "verdicts" in corps["tools"][0]["input_schema"]["properties"]
        assert "extra_body" not in corps
        if corps["model"] == "claude-haiku-5-5":
            assert corps["tool_choice"] == {"type": "tool", "name": OUTIL_SORTIE}
            assert CONSIGNE_OUTIL not in corps["system"]
        else:
            assert corps["tool_choice"] == {"type": "auto"}
            assert corps["system"].endswith(CONSIGNE_OUTIL)
    budgets = {(c["model"], c["messages"][0]["content"]): c["max_tokens"] for c in sdk.appels}
    for (modele, contenu), budget in budgets.items():
        if modele == "claude-opus-5-5":
            assert budget == budgets[("claude-haiku-5-5", contenu)] + 4000
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
    with pytest.raises(BudgetExceeded) as plafond:
        calibrer(
            exp,
            tmp_path / "ann",
            dossier.name,
            wl_home=wl_home,
            providers={"anthropic": AnthropicProvider(client=sdk)},  # type: ignore[arg-type]
        )
    assert not (dossier / "calibration.json").exists()
    # Story 9.1 : les verdicts reçus avant le plafond restent dans le fichier.
    fichier = dossier / "calibration_verdicts.jsonl"
    recus = fichier.read_text("utf-8").splitlines() if fichier.exists() else []
    assert getattr(plafond.value, "verdicts_recus") == len(recus)  # noqa: B009


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


def test_reponse_opus_sans_outil_verdict_manquant_cout_trace_calibration_ecrite(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path
) -> None:
    """Troncature ou refus (aucun bloc d'outil) : nouvel essai puis verdict manquant et
    avertissement pour cette Réponse ; les appels payés sont tracés ; le reste est écrit."""
    _, dossier = execution
    _annoter(dossier, tmp_path / "ann")
    reponses = sorted(read_answers(dossier).values(), key=lambda a: a.answer_id)
    cible = reponses[0]
    sdk = _SdkFactice(tronquer=frozenset({cible.text}))
    exp = validate_file(_exp_claude(tmp_path, "10.00")).resolved
    res, chemin = calibrer(
        exp,
        tmp_path / "ann",
        dossier.name,
        wl_home=wl_home,
        providers={"anthropic": AnthropicProvider(client=sdk)},  # type: ignore[arg-type]
    )
    assert chemin.is_file() and fichier_verdicts(chemin).is_file()
    echecs = [a for a in res.avertissements if "claude-opus-5-5 en échec" in a]
    assert len(echecs) == 2 and all(cible.answer_id in a for a in echecs)  # 2 passes
    lignes = [json.loads(x) for x in fichier_verdicts(chemin).read_text("utf-8").splitlines()]
    par_juge = {(x["judge_model"], x["answer_id"]) for x in lignes if not x.get("missing")}
    assert ("claude-opus-5-5", cible.answer_id) not in par_juge
    manquants = {(x["judge_model"], x["answer_id"], x["pass_id"]) for x in lignes if "missing" in x}
    assert manquants == {  # verdict manquant consigné (story 9.1)
        ("claude-opus-5-5", cible.answer_id, 0),
        ("claude-opus-5-5", cible.answer_id, 1),
    }
    assert ("claude-haiku-5-5", cible.answer_id) in par_juge
    # Appels sans outil payés et comptés : 2 passes x (essai + nouvel essai) au lieu de 2.
    n = len(reponses) * 2
    attendu = n * Decimal("0.00025") + (n + 2) * Decimal("0.010")
    assert res.cout == {"USD": attendu}


def test_sorties_distinctes_ne_s_ecrasent_pas_et_dossier_cree(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path
) -> None:
    """Deux calibrations de la même Exécution (Ollama par défaut, Claude avec `--sortie`) :
    chacune garde ses verdicts ; un dossier de sortie absent est créé avant les appels."""
    _, dossier = execution
    _annoter(dossier, tmp_path / "ann")
    exp = validate_file(_exp_claude(tmp_path, "10.00")).resolved
    providers = {"anthropic": AnthropicProvider(client=_SdkFactice())}  # type: ignore[arg-type]
    _, defaut = calibrer(exp, tmp_path / "ann", dossier.name, wl_home=wl_home, providers=providers)
    assert fichier_verdicts(defaut) == dossier / "calibration_verdicts.jsonl"
    avant = (dossier / "calibration_verdicts.jsonl").read_bytes()
    sortie = tmp_path / "absent" / "calibration-claude.json"
    _, chemin = calibrer(
        exp, tmp_path / "ann", dossier.name, wl_home=wl_home, sortie=sortie, providers=providers
    )
    assert chemin == sortie and sortie.is_file()
    assert (sortie.parent / "calibration-claude_verdicts.jsonl").is_file()
    assert (dossier / "calibration_verdicts.jsonl").read_bytes() == avant
