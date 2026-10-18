"""Story 4.5 : mesure de l'Exécution (postes, latence, énergie par phase, rejeu sans coût)."""

import dataclasses
import json
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.architectures.bm25_only import Bm25Only
from wavelibrarian.architectures.long_context import LongContext
from wavelibrarian.architectures.no_context import NoContext
from wavelibrarian.cli import app
from wavelibrarian.core.errors import BudgetExceeded, WlError
from wavelibrarian.core.types import Answer, ArchAnswer, QuestionInput, Usage
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions
from wavelibrarian.llm.providers.base import ProviderResponse
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.measure.energy import FakeMeter
from wavelibrarian.ports.architecture import ArchitectureBase
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.execute import _Runner
from wavelibrarian.runner.index_cache import IndexCache

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
CONFIGS = ("sans-contexte", "contexte-long", "bm25")
BASELINES = [
    {"id": "sans-contexte", "architecture": "no_context"},
    {"id": "contexte-long", "architecture": "long_context"},
    {"id": "bm25", "architecture": "bm25_only"},
]
LATENCE_EMBED = 0.03  # latence déclarée par l'embedding simulé (comprise dans les 40 ms)


def _experience(tmp_path: Path) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-4-5",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": BASELINES,
    }
    chemin = tmp_path / "exp.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl_run(chemin: Path, wl_home: Path) -> Path:
    avant = set((wl_home / "runs").glob("*")) if (wl_home / "runs").exists() else set()
    # `--tolerer-erreurs` : les Questions en erreur scénarisées ici rendent `completed_with_errors`
    res = CliRunner().invoke(app, ["run", str(chemin), "--tolerer-erreurs"])
    assert res.exit_code == 0, res.output
    (nouveau,) = set((wl_home / "runs").glob("*")) - avant
    return nouveau


def _jsonl(chemin: Path) -> list[dict[str, Any]]:
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


def _ids_dev() -> list[str]:
    return sorted(q.id for q in select_questions(io.load(RACINE / "questions.yaml"), "dev"))


def _record_local(ctx: Context, step: str, kind: Any, latence: float) -> None:
    ctx.tracer.record(
        step,
        kind,
        model_id=None,
        provider="fake",
        usage=Usage(),
        cost=Decimal(0),
        cost_uncached=Decimal(0),
        currency="EUR",
        latency_s=latence,
        from_cache=False,
    )


def _ralentir_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """`answer` des trois Baselines : 40 ms dont un embedding tracé de 30 ms."""

    def envelopper(cls: type[ArchitectureBase]) -> None:
        original: Callable[..., ArchAnswer] = cls.answer

        def answer(self: Any, q: QuestionInput) -> ArchAnswer:
            time.sleep(0.04)
            _record_local(self.ctx, "embed", "embed", LATENCE_EMBED)
            return original(self, q)

        monkeypatch.setattr(cls, "answer", answer)

    for cls in (NoContext, LongContext, Bm25Only):
        envelopper(cls)


# --- AC 1 : postes et span `answer` -------------------------------------------------------------


def test_postes_fixes_par_le_runner_et_span_answer_par_question(
    tmp_path: Path, wl_home: Path
) -> None:
    dossier = _wl_run(_experience(tmp_path), wl_home)
    spans = _jsonl(dossier / "traces.jsonl")
    ids = _ids_dev()
    assert {s["wl.post"] for s in spans} == {"indexing", "query", "judging"}
    spans = [s for s in spans if s["wl.post"] != "judging"]  # le jugement : story 4.9
    for s in spans:
        if s["name"] == "index":
            assert s["wl.post"] == "indexing" and s["wl.question_id"] == ""
        else:
            assert s["wl.post"] == "query" and s["wl.question_id"] in ids
    answers = [s for s in spans if s["name"] == "answer"]
    assert len(answers) == 3 * len(ids)
    assert {(s["wl.config_id"], s["wl.question_id"]) for s in answers} == {
        (c, q) for c in CONFIGS for q in ids
    }
    for s in answers:
        assert s["wl.kind"] == "local" and s["wl.status"] == "ok"
        assert s["wl.invalid_citations"] == 0 and s["wl.post"] == "query"
    assert len([s for s in spans if s["name"] == "index"]) == 3


def test_citations_invalides_comptees_dans_le_span_answer(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Bm25Only.answer

    def answer(self: Any, q: QuestionInput) -> ArchAnswer:
        return original(self, q).model_copy(update={"invalid_citations": 2})

    monkeypatch.setattr(Bm25Only, "answer", answer)
    spans = _jsonl(_wl_run(_experience(tmp_path), wl_home) / "traces.jsonl")
    par_config = {
        c: {
            s["wl.invalid_citations"]
            for s in spans
            if s["name"] == "answer" and s["wl.config_id"] == c
        }
        for c in CONFIGS
    }
    assert par_config["bm25"] == {2} and par_config["sans-contexte"] == {0}


def test_load_est_impute_a_l_indexation(tmp_path: Path) -> None:
    """Un span émis pendant `load` porte `wl.post=indexing`, fixé par le runner."""
    with Context.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-load", providers={"fake": FakeProvider()}
    ) as ctx:
        ctx.parser = "markdown+pdf_text"
        parse = ingest(declare(RACINE / "corpus.yaml"), "markdown+pdf_text", wl_home=ctx.wl_home)

        def fabrique() -> ArchitectureBase:
            arch: ArchitectureBase = ctx.build("architecture", ComponentSpec(name="bm25_only"))
            charger = arch.load

            def load(dossier: Path) -> None:
                _record_local(ctx, "embed", "embed", 0.0)
                charger(dossier)

            arch.load = load  # type: ignore[method-assign]
            return arch

        IndexCache(ctx.wl_home).build(ctx, fabrique, parse)
        spans = _jsonl(ctx.run_dir / "traces.jsonl")
    assert [s["name"] for s in spans].count("embed") == 1
    assert {s["wl.post"] for s in spans} == {"indexing"}


# --- AC 2 : latence ------------------------------------------------------------------------------


def test_latency_s_egale_somme_des_spans_query_de_la_question(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ralentir_answer(monkeypatch)
    dossier = _wl_run(_experience(tmp_path), wl_home)
    spans = _jsonl(dossier / "traces.jsonl")
    reponses = [Answer.model_validate(a) for a in _jsonl(dossier / "answers.jsonl")]
    assert reponses
    for a in reponses:
        mes = [
            s
            for s in spans
            if s["wl.post"] == "query"
            and s["wl.config_id"] == a.config_id
            and s["wl.question_id"] == a.question_id
        ]
        somme = sum(s["wl.latency_s"] for s in mes)
        assert a.latency_s == pytest.approx(somme)
        assert a.latency_s >= 0.04
        # Le span `answer` ne recompte pas la latence déjà portée par l'embedding.
        (propre,) = [s["wl.latency_s"] for s in mes if s["name"] == "answer"]
        assert propre == pytest.approx(a.latency_s - LATENCE_EMBED)


def test_latence_positive_pour_une_reponse_ok(tmp_path: Path, wl_home: Path) -> None:
    dossier = _wl_run(_experience(tmp_path), wl_home)
    reponses = [Answer.model_validate(a) for a in _jsonl(dossier / "answers.jsonl")]
    assert all(a.latency_s > 0 for a in reponses)


# --- AC 3 : énergie par phase --------------------------------------------------------------------


def test_energie_fake_relevee_par_phase_et_repartie_au_prorata(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ralentir_answer(monkeypatch)
    spans = _jsonl(_wl_run(_experience(tmp_path), wl_home) / "traces.jsonl")
    locaux = [s for s in spans if s["wl.kind"] in ("local", "embed")]
    for config in CONFIGS:
        for post in ("indexing", "query"):
            phase = [s for s in locaux if s["wl.config_id"] == config and s["wl.post"] == post]
            assert phase
            assert all(s["wl.energy_method"] == "estimated" for s in phase)
            total = sum(s["wl.energy_kwh"] for s in phase)
            assert total == pytest.approx(0.001)  # FakeMeter : 0,001 kWh par phase
            lat = sum(s["wl.latency_s"] for s in phase)
            for s in phase:  # prorata de la latence
                assert s["wl.energy_kwh"] == pytest.approx(0.001 * s["wl.latency_s"] / lat)
    for s in spans:  # l'énergie d'un appel d'API reste celle de la passerelle
        if s["wl.kind"] == "llm":
            assert s["wl.energy_method"] in ("estimated", "unknown")


def test_phase_sans_duree_energie_a_parts_egales(tmp_path: Path) -> None:
    with Context.from_profile("test", wl_home=tmp_path / "wl", run_id="r-e") as ctx:
        ctx.traceur.begin_phase()
        with ctx.scope(post="query"):
            _record_local(ctx, "answer", "local", 0.0)
        assert not (ctx.run_dir / "traces.jsonl").exists()  # retenu jusqu'à la fin de phase
        ctx.traceur.end_phase(0.001, "estimated")
        (span,) = _jsonl(ctx.run_dir / "traces.jsonl")
    assert span["wl.energy_method"] == "estimated" and span["wl.energy_kwh"] == 0.001


def test_phase_deja_ouverte_refusee(tmp_path: Path) -> None:
    with Context.from_profile("test", wl_home=tmp_path / "wl", run_id="r-d") as ctx:
        ctx.traceur.begin_phase()
        with pytest.raises(WlError):
            ctx.traceur.begin_phase()
        ctx.traceur.end_phase(None)


def test_question_en_erreur_garde_son_span_answer_et_la_phase_se_ferme(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def answer(self: Any, q: QuestionInput) -> ArchAnswer:
        raise RuntimeError("panne")

    monkeypatch.setattr(NoContext, "answer", answer)
    dossier = _wl_run(_experience(tmp_path), wl_home)
    spans = _jsonl(dossier / "traces.jsonl")
    en_erreur = [s for s in spans if s["name"] == "answer" and s["wl.config_id"] == "sans-contexte"]
    assert len(en_erreur) == len(_ids_dev())
    assert {s["wl.status"] for s in en_erreur} == {"error"}
    assert all("wl.energy_method" in s for s in en_erreur)
    reponses = [Answer.model_validate(a) for a in _jsonl(dossier / "answers.jsonl")]
    assert {a.status for a in reponses if a.config_id == "sans-contexte"} == {"error"}
    assert {a.status for a in reponses if a.config_id == "bm25"} == {"ok"}


# --- AC 4 : rejeu --------------------------------------------------------------------------------


def test_rejeu_memes_reponses_aucun_cout_caches_servis(tmp_path: Path, wl_home: Path) -> None:
    chemin = _experience(tmp_path)
    premier = _wl_run(chemin, wl_home)
    second = _wl_run(chemin, wl_home)
    assert premier != second

    def lire(dossier: Path) -> list[dict[str, Any]]:
        lignes = _jsonl(dossier / "answers.jsonl")
        for ligne in lignes:  # identifiants et durées propres à l'Exécution
            ligne.pop("answer_id")
            ligne.pop("latency_s")
        return lignes

    assert lire(premier) == lire(second)
    assert any(a["retrieved"] for a in lire(second))  # des Passages retrouvés à comparer

    spans = _jsonl(second / "traces.jsonl")
    assert all(Decimal(s["wl.cost"]) == 0 for s in spans)
    index = [s for s in spans if s["name"] == "index"]
    assert len(index) == 3 and all(s["wl.index_cache_hit"] is True for s in index)
    llm = [s for s in spans if s["wl.kind"] == "llm"]
    assert llm and all(s["wl.llm_cache_hit"] is True for s in llm)
    assert all(s["wl.status"] == "ok" for s in spans)


# --- revue : latence d'origine au rejeu, cycle de phase, ordre spans / Réponses ------------------

LATENCE_LLM = 0.25  # latence déclarée par le Faux LLM au premier passage


def _par_question(spans: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    par_q: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for s in spans:
        if s["wl.post"] == "query":
            par_q.setdefault((s["wl.config_id"], s["wl.question_id"]), []).append(s)
    return par_q


def test_rejeu_retrace_la_latence_d_origine_des_appels_llm(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """review-reconcile §1 : un hit du Cache de réponses porte la latence de l'appel d'origine,
    sinon p50/p95 valent 0 au rejeu ; il ne compte ni dans le temps propre ni dans l'énergie."""
    original = FakeProvider.complete

    def lent(self: Any, request: Any, **kw: Any) -> ProviderResponse:
        return dataclasses.replace(original(self, request, **kw), latency_s=LATENCE_LLM)

    monkeypatch.setattr(FakeProvider, "complete", lent)
    chemin = _experience(tmp_path)
    premier = _wl_run(chemin, wl_home)

    def interdit(self: Any, request: Any, **kw: Any) -> ProviderResponse:
        raise AssertionError("appel LLM au rejeu")

    monkeypatch.setattr(FakeProvider, "complete", interdit)
    second = _wl_run(chemin, wl_home)

    for dossier, hit in ((premier, False), (second, True)):
        spans = _jsonl(dossier / "traces.jsonl")
        llm = [s for s in spans if s["wl.kind"] == "llm"]
        assert llm and all(s["wl.llm_cache_hit"] is hit for s in llm)
        assert all(s["wl.latency_s"] == LATENCE_LLM for s in llm)
        par_q = _par_question(spans)
        for a in _jsonl(dossier / "answers.jsonl"):
            mes = par_q[(a["config_id"], a["question_id"])]
            assert a["latency_s"] == pytest.approx(sum(s["wl.latency_s"] for s in mes))
            if any(s["wl.kind"] == "llm" for s in mes):
                assert a["latency_s"] >= LATENCE_LLM
            # Le span `answer` ne recompte pas la latence de l'appel LLM, servi ou non.
            (propre,) = [s["wl.latency_s"] for s in mes if s["name"] == "answer"]
            assert propre < LATENCE_LLM
    hits = [s for s in _jsonl(second / "traces.jsonl") if s["wl.kind"] == "llm"]
    assert all("wl.energy_kwh" not in s for s in hits)  # un hit n'a rien consommé


def test_echec_du_mesureur_ne_laisse_pas_la_phase_ouverte(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le mesureur échoue au départ de la première phase : seule cette Configuration est en
    erreur, les suivantes s'exécutent (pas de « phase déjà ouverte » en cascade)."""
    original = FakeMeter.start
    appels: list[str] = []

    def start(self: FakeMeter, phase: str) -> None:
        appels.append(phase)
        if len(appels) == 1:
            raise RuntimeError("compteur indisponible")
        original(self, phase)

    monkeypatch.setattr(FakeMeter, "start", start)
    dossier = _wl_run(_experience(tmp_path), wl_home)
    reponses = [Answer.model_validate(a) for a in _jsonl(dossier / "answers.jsonl")]
    premiere = appels[0].split(":")[0]
    statuts = {c: {a.status for a in reponses if a.config_id == c} for c in CONFIGS}
    assert statuts[premiere] == {"error"}
    assert all(statuts[c] == {"ok"} for c in CONFIGS if c != premiere)


def test_reponses_ecrites_apres_les_spans_de_leur_phase(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pendant la phase query, aucune Réponse n'est encore écrite : un arrêt dur perd les spans
    retenus et les Réponses ensemble, la reprise repose alors ces Questions (AD-9, AD-11)."""
    vues: list[int] = []
    original = Bm25Only.answer

    def answer(self: Any, q: QuestionInput) -> ArchAnswer:
        chemin = self.ctx.run_dir / "answers.jsonl"
        lignes = _jsonl(chemin) if chemin.exists() else []
        vues.append(sum(1 for a in lignes if a["config_id"] == "bm25"))
        return original(self, q)

    monkeypatch.setattr(Bm25Only, "answer", answer)
    dossier = _wl_run(_experience(tmp_path), wl_home)
    assert len(vues) == len(_ids_dev()) and set(vues) == {0}
    spans = _jsonl(dossier / "traces.jsonl")
    reponses = [a for a in _jsonl(dossier / "answers.jsonl") if a["config_id"] == "bm25"]
    assert len(reponses) == len(_ids_dev())
    spans_answer = {
        s["wl.question_id"] for s in spans if s["name"] == "answer" and s["wl.config_id"] == "bm25"
    }
    assert spans_answer == {a["question_id"] for a in reponses}


class _TraceurEnPanne:
    def __init__(self) -> None:
        self.ouvertes = 0

    def begin_phase(self) -> None:
        self.ouvertes += 1

    def end_phase(
        self, kwh: float | None, method: Any = "estimated", source: str = "unknown"
    ) -> None:
        self.ouvertes -= 1
        raise WlError("trace non écrite")


def _faux_runner(traceur: Any) -> Any:
    return SimpleNamespace(ctx=SimpleNamespace(traceur=traceur), meter=FakeMeter())


def test_fin_de_phase_en_echec_ne_masque_pas_le_plafond() -> None:
    traceur = _TraceurEnPanne()
    appele: list[bool] = []
    conf: Any = SimpleNamespace(id="c")
    phase = _Runner.energie_de_phase(
        _faux_runner(traceur), conf, "query", lambda: appele.append(True)
    )
    with pytest.raises(BudgetExceeded), phase:
        raise BudgetExceeded("plafond")
    assert traceur.ouvertes == 0 and not appele  # pas de Réponse sans ses spans


def test_fin_de_phase_en_echec_sans_exception_remonte() -> None:
    conf: Any = SimpleNamespace(id="c")
    phase = _Runner.energie_de_phase(_faux_runner(_TraceurEnPanne()), conf, "index")
    with pytest.raises(WlError), phase:
        pass


def test_hit_du_cache_hors_temps_ecoule_et_hors_energie(tmp_path: Path) -> None:
    with Context.from_profile("test", wl_home=tmp_path / "wl", run_id="r-h") as ctx:
        traceur = ctx.traceur
        traceur.begin_phase()
        with ctx.scope(post="query"):
            for hit in (True, False):
                ctx.tracer.record(
                    "generate", "llm", model_id="m", provider="ollama", usage=Usage(),
                    cost=Decimal(0), cost_uncached=Decimal(0), currency="EUR",
                    latency_s=1.0, from_cache=hit,
                )  # fmt: skip
        assert traceur.latency_total == 2.0 and traceur.elapsed_total == 1.0
        traceur.end_phase(0.002, "estimated")
        spans = _jsonl(ctx.run_dir / "traces.jsonl")
    par_hit = {s["wl.llm_cache_hit"]: s for s in spans}
    assert par_hit[False]["wl.energy_kwh"] == pytest.approx(0.002)
    assert par_hit[True]["wl.energy_kwh"] == 0.0  # servi par le cache : rien consommé


def test_temps_propre_negatif_ramene_a_zero_et_signale(caplog: pytest.LogCaptureFixture) -> None:
    from wavelibrarian.measure.tracing import temps_propre

    assert temps_propre(1.0, 0.25) == 0.75
    with caplog.at_level("WARNING"):
        assert temps_propre(0.1, 0.3) == 0.0
    assert "temps propre négatif" in caplog.text
