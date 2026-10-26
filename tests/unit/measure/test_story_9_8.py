"""Story 9.8 : méthode `mixed`, phase `judging`, GPU du profil `gpu` (sans GPU ni réseau)."""

import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from wavelibrarian.config.defaults import load_profile
from wavelibrarian.core.types import Usage
from wavelibrarian.measure import energy
from wavelibrarian.measure.energy import CodecarbonMeter, FakeMeter, energy_method, make_meter
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.execute import _Runner

RAM = type("RAM", (), {})()
GPU_SUIVI = type("GPU", (), {"gpu_ids": [0]})()
CPU_EMI = SimpleNamespace(_mode="windows_emi")
CPU_ESTIME = SimpleNamespace(_mode="cpu_load")


@pytest.mark.parametrize(
    ("materiels", "gpu_ids", "attendu"),
    [
        ([RAM, CPU_EMI], [], "mixed"),  # poste Windows de la 8.6 : CPU lu, RAM estimée
        ([CPU_EMI], [], "measured"),  # aucune part estimée
        ([RAM, CPU_ESTIME], [], "estimated"),
        ([RAM], [], "estimated"),
        # décision du 2026-10-26 (A8) : `measured` seulement si toutes les parts sont lues
        ([RAM, CPU_EMI, GPU_SUIVI], [0], "mixed"),  # la RAM reste estimée
        ([CPU_EMI, GPU_SUIVI], [0], "measured"),
        ([RAM, CPU_ESTIME, GPU_SUIVI], [0], "mixed"),  # CPU estimé à côté d'un GPU lu
        ([RAM, GPU_SUIVI], [0], "mixed"),
        ([RAM, CPU_EMI, GPU_SUIVI], [], "mixed"),  # GPU non demandé : ignoré, il reste CPU + RAM
    ],
)
def test_methode_de_la_phase(materiels: list[Any], gpu_ids: list[int], attendu: str) -> None:
    tracker = SimpleNamespace(_hardware=materiels, _gpu_ids=gpu_ids)
    assert energy_method(tracker) == attendu


def _faux_codecarbon(
    monkeypatch: pytest.MonkeyPatch, materiels: list[Any], appels: dict[str, Any]
) -> None:
    class FauxTracker:
        def __init__(self, **kw: Any) -> None:
            appels.update(kw)
            self._gpu_ids = kw["gpu_ids"]
            self._hardware = list(materiels)
            self.final_emissions_data = SimpleNamespace(energy_consumed=0.004)

        def start(self) -> None: ...

        def stop(self) -> None: ...

    monkeypatch.setitem(
        sys.modules, "codecarbon", SimpleNamespace(OfflineEmissionsTracker=FauxTracker)
    )


def test_meter_mixte_sous_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    _faux_codecarbon(monkeypatch, [RAM, CPU_EMI], {})
    meter = CodecarbonMeter("FRA")
    meter.start("index")
    assert meter.stop() == 0.004
    assert (meter.method, meter.source) == ("mixed", "windows_emi")


def test_gpu_demande_n_est_pas_retire_et_la_source_est_nvml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appels: dict[str, Any] = {}
    _faux_codecarbon(monkeypatch, [RAM, GPU_SUIVI, CPU_EMI], appels)
    retires: list[bool] = []
    monkeypatch.setattr(energy, "_retirer_gpu", lambda t: retires.append(True))
    meter = CodecarbonMeter("FRA", gpu=True)
    meter.start("query")
    assert meter._tracker is not None and len(meter._tracker._hardware) == 3
    assert meter.stop() == 0.004
    # `None` : tous les GPU visibles (codecarbon respecte `CUDA_VISIBLE_DEVICES`), aucun indice
    assert appels["gpu_ids"] is None and not retires
    assert (meter.method, meter.source) == ("mixed", "nvml")  # RAM estimée à côté du GPU lu


def test_gpu_demande_suivi_meme_sans_indice_resolu(monkeypatch: pytest.MonkeyPatch) -> None:
    """`gpu_ids=None` : ni le tracker ni le GPU de codecarbon ne portent d'indice avant la
    mesure ; le GPU demandé compte quand même."""
    gpu = type("GPU", (), {"gpu_ids": None})()
    _faux_codecarbon(monkeypatch, [gpu, CPU_EMI], {})
    meter = CodecarbonMeter("FRA", gpu=True)
    meter.start("query")
    meter.stop()
    assert (meter.method, meter.source) == ("measured", "nvml")


def test_profil_cpu_etiquette_mixed_de_bout_en_bout(monkeypatch: pytest.MonkeyPatch) -> None:
    gpu = type("GPU", (), {"gpu_ids": [0]})()
    _faux_codecarbon(monkeypatch, [RAM, gpu, CPU_EMI], {})
    meter = make_meter(load_profile("cpu").energy)
    meter.start("query")
    meter.stop()
    assert (meter.method, meter.source) == ("mixed", "windows_emi")  # type: ignore[attr-defined]


def test_sans_gpu_le_comportement_de_fix_8_8_est_inchange(monkeypatch: pytest.MonkeyPatch) -> None:
    appels: dict[str, Any] = {}
    gpu = type("GPU", (), {"gpu_ids": [0]})()
    _faux_codecarbon(monkeypatch, [RAM, gpu, CPU_EMI], appels)
    meter = CodecarbonMeter("FRA")
    meter.start("query")
    assert meter._tracker is not None
    assert [type(h).__name__ for h in meter._tracker._hardware] == ["RAM", "SimpleNamespace"]
    meter.stop()
    assert appels["gpu_ids"] == [] and meter.source == "windows_emi"


def test_profils_gpu_et_cpu() -> None:
    assert load_profile("gpu").energy.gpu is True
    assert load_profile("cpu").energy.gpu is False
    assert load_profile("test").energy.gpu is False
    assert isinstance(make_meter(load_profile("test").energy), FakeMeter)


def test_make_meter_transmet_le_champ_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    _faux_codecarbon(monkeypatch, [], {})
    assert make_meter(load_profile("gpu").energy)._gpu is True  # type: ignore[attr-defined]
    assert make_meter(load_profile("cpu").energy)._gpu is False  # type: ignore[attr-defined]


# --- Phase `judging` --------------------------------------------------------------------------


def _appel(ctx: Context, provider: str, modele: str, latence: float, hit: bool = False) -> None:
    with ctx.scope(post="judging", question_id="q1"):
        ctx.tracer.record(
            "judge", "llm", model_id=modele, provider=provider, usage=Usage(),
            cost=Decimal(0), cost_uncached=Decimal(0), currency="EUR",
            latency_s=latence, from_cache=hit,
            extra={"wl.energy_method": "estimated", "wl.energy_source": "ecologits"}
            if provider == "anthropic"
            else {},
        )  # fmt: skip


class _Meter(FakeMeter):
    method = "mixed"  # type: ignore[assignment]
    source = "windows_emi"
    demarrages: list[str] = []

    def start(self, phase: str) -> None:
        self.demarrages.append(phase)
        super().start(phase)


def _lancer(
    tmp_path: Path, membres: tuple[str, ...], panne: bool = False, hits: bool = False
) -> list[dict[str, Any]]:
    _Meter.demarrages = []
    with Context.from_profile("test", wl_home=tmp_path / "wl", run_id="r-j") as ctx:
        runner: Any = SimpleNamespace(ctx=ctx, meter=_Meter(0.01))
        essais = {"n": 0}

        def _juger(experience: Any, panels: Any) -> None:
            essais["n"] += 1
            _appel(ctx, "ollama", "qwen3.5:4b", 1.0, hits)
            if panne and essais["n"] == 1:
                raise KeyboardInterrupt  # interruption en plein Panel, phase ouverte
            _appel(ctx, "ollama", "qwen3.5:4b", 3.0, hits)
            _appel(ctx, "anthropic", "claude-haiku-5-5", 2.0)

        runner.energie_de_phase = lambda *a, **k: _Runner.energie_de_phase(runner, *a, **k)
        runner._juger = _juger
        if panne:
            with pytest.raises(KeyboardInterrupt):
                _Runner.juger(runner, cast(Any, None), {"c": membres})
        _Runner.juger(runner, cast(Any, None), {"c": membres})  # reprise : la phase est refermée
        trace = ctx.run_dir / "traces.jsonl"
    return [json.loads(x) for x in trace.read_text(encoding="utf-8").splitlines()]


def test_juges_locaux_ouvrent_la_phase_judging_repartie_au_prorata(tmp_path: Path) -> None:
    spans = _lancer(tmp_path, ("qwen3.5:4b", "claude-haiku-5-5"))
    assert _Meter.demarrages == ["judging:judging"]
    api = [s for s in spans if s["gen_ai.provider.name"] == "anthropic"]
    local = [s for s in spans if s["gen_ai.provider.name"] == "ollama"]
    assert [s["wl.energy_kwh"] for s in local] == pytest.approx([0.0025, 0.0075])
    assert {s["wl.energy_method"] for s in local} == {"mixed"}
    assert {s["wl.energy_source"] for s in local} == {"windows_emi"}
    assert {s["wl.post"] for s in local} == {"judging"}
    # le Juge d'API garde son énergie estimée par appel, hors de la phase
    assert "wl.energy_kwh" not in api[0] and api[0]["wl.energy_source"] == "ecologits"


def test_juges_d_api_seuls_n_ouvrent_pas_de_phase(tmp_path: Path) -> None:
    spans = _lancer(tmp_path, ("claude-haiku-5-5",))
    assert _Meter.demarrages == []
    assert all("wl.energy_kwh" not in s or s["gen_ai.provider.name"] != "ollama" for s in spans)


def test_reprise_apres_interruption_la_phase_judging_est_refermee(tmp_path: Path) -> None:
    spans = _lancer(tmp_path, ("qwen3.5:4b",), panne=True)
    assert _Meter.demarrages == ["judging:judging"] * 2
    local = [s for s in spans if s["gen_ai.provider.name"] == "ollama"]
    # 1er passage : le span déjà tracé est écrit avec l'énergie de la phase interrompue
    assert [s["wl.energy_kwh"] for s in local] == pytest.approx([0.01, 0.0025, 0.0075])


def test_hits_du_cache_seuls_ne_recoivent_aucune_energie(tmp_path: Path) -> None:
    spans = _lancer(tmp_path, ("qwen3.5:4b",), hits=True)
    local = [s for s in spans if s["gen_ai.provider.name"] == "ollama"]
    assert [s["wl.energy_kwh"] for s in local] == [0.0, 0.0]
    assert {s["wl.energy_method"] for s in local} == {"mixed"}
