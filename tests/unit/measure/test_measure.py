"""Story 1.7 : traces, tokenizers, énergie et coût de possession (sans réseau, sans GPU)."""

import builtins
import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_costs, load_profile
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import Condition, CostPost, Phase, Usage
from wavelibrarian.measure import energy, tokenizers
from wavelibrarian.measure.energy import (
    CodecarbonMeter,
    EcoLogitsEstimator,
    FakeEstimator,
    FakeMeter,
    is_hardware_counter,
    make_estimator,
    make_meter,
    spread_energy,
)
from wavelibrarian.measure.tco import possession_cost
from wavelibrarian.measure.tokenizers import (
    ApproxTokenizer,
    ReferenceTokenizer,
    ScaledTokenizer,
    make_tokenizer,
    tokenizer_for,
)
from wavelibrarian.measure.tracing import Tracer


class _Ctx:
    run_id = "run-1"
    config_id = "cfg-1"
    condition: Condition = "standard"
    tier: int | None = 10
    phase: Phase = "base"
    post: CostPost = "query"
    question_id: str | None = "q-1"


def _record(tracer: Tracer, step: str = "generate", **kw: Any) -> None:
    tracer.record(
        step,
        "llm",
        model_id="fake-llm-a",
        provider="fake",
        usage=Usage(input_tokens=100, output_tokens=20, cache_read_tokens=5, cache_write_tokens=7),
        cost=Decimal("0.0012"),
        cost_uncached=Decimal("0.0030"),
        currency="USD",
        latency_s=0.5,
        from_cache=False,
        **kw,
    )


def _lignes(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


# --- Traces ---------------------------------------------------------------------------------


def test_deux_records_deux_lignes_avec_tous_les_attributs(tmp_path: Path) -> None:
    chemin = tmp_path / "traces.jsonl"
    tracer = Tracer(_Ctx(), chemin)
    _record(tracer, "generate")
    _record(
        tracer, "judge", extra={"wl.loop": 2, "wl.energy_kwh": 0.5, "wl.energy_method": "estimated"}
    )
    lignes = _lignes(chemin)
    assert len(lignes) == 2
    l1 = lignes[0]
    assert len(l1["trace_id"]) == 32 and len(l1["span_id"]) == 16
    assert l1["name"] == "generate"
    assert isinstance(l1["start_time"], int) and l1["end_time"] - l1["start_time"] == pytest.approx(
        5e8, abs=1e6
    )
    attendu = {
        "wl.run_id": "run-1",
        "wl.config_id": "cfg-1",
        "wl.question_id": "q-1",
        "wl.condition": "standard",
        "wl.phase": "base",
        "wl.tier": 10,
        "wl.post": "query",
        "wl.step": "generate",
        "wl.kind": "llm",
        "gen_ai.provider.name": "fake",
        "gen_ai.request.model": "fake-llm-a",
        "gen_ai.usage.input_tokens": 100,
        "gen_ai.usage.output_tokens": 20,
        "wl.usage.cache_read_tokens": 5,
        "wl.usage.cache_write_tokens": 7,
        "wl.cost": "0.0012",
        "wl.cost_uncached": "0.0030",
        "wl.currency": "USD",
        "wl.llm_cache_hit": False,
        "wl.latency_s": 0.5,
        "wl.status": "ok",
    }
    for cle, valeur in attendu.items():
        assert l1[cle] == valeur, cle
        assert type(l1[cle]) is type(valeur), cle
    assert lignes[1]["wl.loop"] == 2 and lignes[1]["wl.energy_method"] == "estimated"


def test_tier_absent_et_post_lu_dans_le_contexte(tmp_path: Path) -> None:
    ctx = _Ctx()
    ctx.tier = None
    ctx.question_id = None
    chemin = tmp_path / "t.jsonl"
    tracer = Tracer(ctx, chemin)
    _record(tracer)
    ctx.post = "indexing"  # le runner change le poste : le Tracer le relit
    _record(tracer, extra={"wl.post": "forge"})  # l'appelant ne peut pas imposer le poste
    a, b = _lignes(chemin)
    assert "wl.tier" not in a
    assert a["wl.question_id"] == "" and a["wl.post"] == "query"
    assert b["wl.post"] == "indexing"


def test_export_synchrone_local_sans_otlp(tmp_path: Path) -> None:
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    tracer = Tracer(_Ctx(), tmp_path / "t.jsonl")
    assert type(tracer.processor) is SimpleSpanProcessor
    assert len(tracer._provider._active_span_processor._span_processors) == 1
    _record(tracer)
    assert len(_lignes(tmp_path / "t.jsonl")) == 1  # écrit dès record, sans flush


def test_otlp_demande_sans_paquet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter.otlp.proto.http.trace_exporter", None)
    with pytest.raises(WlError, match="OTLP"):
        Tracer(_Ctx(), tmp_path / "t.jsonl", otlp_endpoint="http://localhost:4318")


# --- Tokenizers -----------------------------------------------------------------------------


def test_approx_compte_les_mots() -> None:
    assert ApproxTokenizer().count(" ".join(f"mot{i}" for i in range(12))) == 12
    assert make_tokenizer("approx").count("a  b\nc") == 3
    with pytest.raises(WlError):
        make_tokenizer("inconnu")


def test_reference_sans_encodage_local_ne_telecharge_pas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    tok = ReferenceTokenizer()
    assert tok.name == "reference"
    with pytest.raises(WlError, match="wl installer"):
        tok.count("bonjour")


def test_reference_avec_cache_illisible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fichier présent mais illisible : WlError, sans téléchargement (pytest-socket)."""
    import hashlib

    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    cle = hashlib.sha1(tokenizers._URL_ENCODAGE.encode()).hexdigest()
    assert not tokenizers.encodage_installe()
    (tmp_path / cle).write_text("x", encoding="utf-8")
    assert tokenizers.encodage_installe()
    # Le contenu est invalide pour tiktoken : l'échec reste un WlError, sans téléchargement.
    with pytest.raises(WlError, match="wl installer"):
        ReferenceTokenizer().count("bonjour")


def test_tokenizer_for_applique_token_factor() -> None:
    catalog = load_catalog()
    ref = ApproxTokenizer()
    texte = " ".join(["m"] * 10)
    # Embedder factice déclaré `approx` : référence x token_factor (défaut 1,2).
    approx_ids = [m.id for m in catalog.models if m.tokenizer == "approx"]
    assert approx_ids
    scaled = tokenizer_for(approx_ids[0], catalog, ref)
    assert isinstance(scaled, ScaledTokenizer)
    assert scaled.count(texte) == 12
    assert ScaledTokenizer(ref, Decimal("1.5")).count(texte) == 15
    assert ScaledTokenizer(ref, Decimal("1.2")).count("a b c") == 4  # arrondi au supérieur
    # Modèle qui déclare `reference` : tokenizer de référence tel quel.
    assert tokenizer_for("claude-haiku-5-5", catalog, ref) is ref


# --- Énergie --------------------------------------------------------------------------------


def test_fake_demarre_arrete_et_repartit_au_prorata() -> None:
    profil = load_profile("test")
    meter = make_meter(profil.energy)
    assert isinstance(meter, FakeMeter)
    meter.start("query")
    kwh = meter.stop()
    assert kwh is not None
    parts = spread_energy(kwh, [1.0, 1.0, 2.0], "estimated")
    assert [p[0] for p in parts] == pytest.approx([kwh * 0.25, kwh * 0.25, kwh * 0.5])
    assert all(p[1] == "estimated" for p in parts)
    assert isinstance(make_estimator(profil.energy), FakeEstimator)
    assert make_estimator(profil.energy).estimate("m", Usage(input_tokens=10), 1.0) is not None


def test_repartition_sans_energie_ou_sans_duree() -> None:
    assert spread_energy(None, [1.0, 2.0], "measured") == [(None, "unknown")] * 2
    assert spread_energy(1.0, [0.0, 0.0], "measured") == [(None, "unknown")] * 2


def test_energie_portee_par_les_spans(tmp_path: Path) -> None:
    chemin = tmp_path / "t.jsonl"
    tracer = Tracer(_Ctx(), chemin)
    for kwh, methode in spread_energy(0.4, [1.0, 1.0, 2.0], "estimated"):
        _record(tracer, "local", extra={"wl.energy_kwh": kwh, "wl.energy_method": methode})  # type: ignore[dict-item]
    lignes = _lignes(chemin)
    assert [x["wl.energy_kwh"] for x in lignes] == pytest.approx([0.1, 0.1, 0.2])
    assert {x["wl.energy_method"] for x in lignes} == {"estimated"}


@pytest.mark.parametrize("nom", ["codecarbon", "ecologits"])
def test_adaptateurs_sans_extra_energy(nom: str, monkeypatch: pytest.MonkeyPatch) -> None:
    cible = "ecologits.tracers.utils" if nom == "ecologits" else nom
    reel = builtins.__import__

    def faux_import(name: str, *a: Any, **k: Any) -> Any:
        if name.split(".")[0] == nom:
            raise ImportError(name)
        return reel(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", faux_import)
    for m in [k for k in sys.modules if k.split(".")[0] == nom]:
        monkeypatch.delitem(sys.modules, m)
    classe = CodecarbonMeter if nom == "codecarbon" else EcoLogitsEstimator
    with pytest.raises(WlError, match="installer l'extra energy") as exc:
        classe()
    assert cible in str(exc.value)


def test_import_paresseux_des_adaptateurs() -> None:
    # Importer le module d'énergie ne charge ni codecarbon ni ecologits.
    src = Path(energy.__file__).read_text(encoding="utf-8")
    assert "\nimport codecarbon" not in src and "\nimport ecologits" not in src


def test_codecarbon_double_sans_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    """Faux module codecarbon : aucun vrai suivi, donc aucun accès NVML."""
    appels: dict[str, Any] = {}

    class FauxTracker:
        def __init__(self, **kw: Any) -> None:
            appels.update(kw)
            self._hardware = [SimpleNamespace(_mode="tdp_constant")]
            self.final_emissions_data = SimpleNamespace(energy_consumed=0.002)

        def start(self) -> None: ...

        def stop(self) -> float:
            return 0.0

    monkeypatch.setitem(
        sys.modules, "codecarbon", SimpleNamespace(OfflineEmissionsTracker=FauxTracker)
    )
    meter = CodecarbonMeter("FRA")
    meter.start("index")
    assert meter.stop() == 0.002
    assert appels["gpu_ids"] == [] and appels["country_iso_code"] == "FRA"
    assert meter.method == "estimated"
    assert meter.stop() is None  # rien en cours


def test_mesure_materielle_seulement_avec_compteur() -> None:
    rapl = SimpleNamespace(_hardware=[SimpleNamespace(_mode="intel_rapl")])
    charge = SimpleNamespace(_hardware=[SimpleNamespace(_mode="cpu_load")])
    tdp = SimpleNamespace(_hardware=[SimpleNamespace(_mode="tdp_constant")])
    assert is_hardware_counter(rapl)
    assert not is_hardware_counter(charge) and not is_hardware_counter(tdp)
    assert not is_hardware_counter(SimpleNamespace())


def test_ecologits_double(monkeypatch: pytest.MonkeyPatch) -> None:
    def impacts(**kw: Any) -> Any:
        return SimpleNamespace(energy=SimpleNamespace(value=SimpleNamespace(min=1.0, max=3.0)))

    monkeypatch.setitem(
        sys.modules, "ecologits.tracers.utils", SimpleNamespace(llm_impacts=impacts)
    )
    est = EcoLogitsEstimator()
    assert est.estimate("claude-haiku-5-5", Usage(output_tokens=5), 1.0) == 2.0

    def inconnu(**kw: Any) -> Any:
        raise ValueError("modèle inconnu")

    monkeypatch.setitem(
        sys.modules, "ecologits.tracers.utils", SimpleNamespace(llm_impacts=inconnu)
    )
    assert EcoLogitsEstimator().estimate("zzz", Usage(), 1.0) is None


# --- Coût de possession ---------------------------------------------------------------------


def test_cout_de_possession(wl_home: Path) -> None:
    costs = load_costs(wl_home)
    total = possession_cost(costs, kwh="0.5", compute_seconds=3600, index_gb=2, months=1)
    own = costs.owned_costs
    attendu = (
        Decimal("0.5") * own.kwh_price_eur
        + own.hardware_price_eur / Decimal(own.hardware_life_hours) * 1
        + Decimal(2) * own.storage_eur_per_gb_month
    )
    assert isinstance(total, Decimal) and total == attendu
    assert total == Decimal("0.20005")
    assert possession_cost(costs, kwh=0, compute_seconds=0, index_gb=0) == 0
