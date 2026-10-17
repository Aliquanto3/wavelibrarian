"""Énergie (AD-17) : mesure locale par phase, estimation API par appel, répartition au prorata.

`measured` seulement si un compteur matériel a été lu ; `codecarbon` et `ecologits` sont importés
au premier usage (extra `energy`).
"""

import importlib
import logging
from collections.abc import Sequence
from typing import Any, Literal

from wavelibrarian.config.schemas import EnergySettings
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import Usage
from wavelibrarian.ports.measure import EnergyEstimator, EnergyMeter

_log = logging.getLogger(__name__)

EnergyMethod = Literal["measured", "estimated", "unknown"]

_MSG_EXTRA = "installer l'extra energy (`uv sync --extra energy`) : module {} introuvable"
# Modes de codecarbon qui lisent un compteur matériel (RAPL, Power Gadget, powermetrics, NVML).
_MODES_MATERIELS = frozenset({"intel_rapl", "intel_power_gadget", "apple_powermetrics", "nvml"})


def _importer(nom: str) -> Any:
    try:
        return importlib.import_module(nom)
    except ImportError as exc:
        raise WlError(_MSG_EXTRA.format(nom)) from exc


def spread_energy(
    kwh: float | None, latencies_s: Sequence[float], method: EnergyMethod
) -> list[tuple[float | None, EnergyMethod]]:
    """Répartit l'énergie d'une phase sur ses spans locaux au prorata de leur latence.

    Chaque span reçoit `(kWh, méthode)` ; sans énergie connue ou sans durée : `(None, "unknown")`.
    """
    total = sum(latencies_s)
    if kwh is None or total <= 0:
        return [(None, "unknown")] * len(latencies_s)
    return [(kwh * lat / total, method) for lat in latencies_s]


class FakeMeter:
    """Mesureur factice (profil `test`) : énergie fixe, jamais `measured`."""

    method: EnergyMethod = "estimated"

    def __init__(self, kwh: float = 0.001) -> None:
        self._kwh = kwh
        self.phase: str | None = None

    def start(self, phase: str) -> None:
        self.phase = phase

    def stop(self) -> float | None:
        self.phase = None
        return self._kwh


class FakeEstimator:
    """Estimateur d'API factice : proportionnel aux tokens, déterministe."""

    def estimate(self, model_id: str, usage: Usage, latency_s: float) -> float | None:
        return (usage.input_tokens + usage.output_tokens) * 1e-7


def is_hardware_counter(tracker: Any) -> bool:
    """Vrai si l'un des matériels suivis par codecarbon a été lu sur un compteur matériel."""
    for hw in getattr(tracker, "_hardware", None) or []:
        mode = str(getattr(hw, "_mode", "") or getattr(hw, "mode", "")).lower()
        if mode in _MODES_MATERIELS or type(hw).__name__ == "GPU":
            return True
    return False


class CodecarbonMeter:
    """Énergie locale par phase via `codecarbon.OfflineEmissionsTracker` (CPU seul, sans NVML)."""

    def __init__(self, country_iso_code: str = "FRA") -> None:
        self._cc = _importer("codecarbon")
        self._country = country_iso_code
        self._tracker: Any = None
        self.method: EnergyMethod = "estimated"

    def start(self, phase: str) -> None:
        self._tracker = self._cc.OfflineEmissionsTracker(
            country_iso_code=self._country,
            project_name=phase,
            save_to_file=False,
            log_level="error",
            gpu_ids=[],  # jamais d'interrogation du GPU
        )
        self._tracker.start()

    def stop(self) -> float | None:
        tracker, self._tracker = self._tracker, None
        if tracker is None:
            return None
        tracker.stop()
        self.method = "measured" if is_hardware_counter(tracker) else "estimated"
        data = getattr(tracker, "final_emissions_data", None)
        energy = getattr(data, "energy_consumed", None)
        return None if energy is None else float(energy)


class EcoLogitsEstimator:
    """Énergie estimée d'un appel d'API (EcoLogits) ; `None` si le modèle est inconnu.

    `ecologits.tracers.utils.llm_impacts` n'est pas documentée (review-versions.md, point 5) :
    son absence ou une signature changée lèvent un `WlError`, et tout autre échec est journalisé.
    La voie documentée (`EcoLogits.init` puis `response.impacts`) revient à l'adaptateur Anthropic.
    """

    def __init__(self, provider: str = "anthropic") -> None:
        utils: Any = _importer("ecologits.tracers.utils")
        self._llm_impacts: Any = getattr(utils, "llm_impacts", None)
        if not callable(self._llm_impacts):
            raise WlError(
                "ecologits installé sans `ecologits.tracers.utils.llm_impacts` : "
                "version incompatible (attendu 0.11.x, extra energy)"
            )
        self._provider = provider

    def estimate(self, model_id: str, usage: Usage, latency_s: float) -> float | None:
        try:
            impacts = self._llm_impacts(
                provider=self._provider,
                model_name=model_id,
                output_token_count=usage.output_tokens,
                request_latency=latency_s,
            )
        except TypeError as exc:  # signature changée : défaut d'intégration, pas un modèle inconnu
            raise WlError(f"API EcoLogits `llm_impacts` incompatible : {exc}") from exc
        except Exception as exc:
            _log.warning("EcoLogits : estimation impossible pour %s (%s)", model_id, exc)
            return None
        if impacts is None:  # modèle inconnu d'EcoLogits
            _log.warning("EcoLogits : modèle %s inconnu, énergie `unknown`", model_id)
            return None
        valeur = getattr(getattr(impacts, "energy", None), "value", None)
        if valeur is None:
            _log.warning("EcoLogits : impacts sans énergie pour %s", model_id)
            return None
        if hasattr(valeur, "min") and hasattr(valeur, "max"):
            return (float(valeur.min) + float(valeur.max)) / 2
        return float(valeur)


def make_meter(settings: EnergySettings) -> EnergyMeter:
    if settings.local == "fake":
        return FakeMeter()
    return CodecarbonMeter(settings.country_iso_code)


def make_estimator(settings: EnergySettings) -> EnergyEstimator:
    if settings.api == "fake":
        return FakeEstimator()
    return EcoLogitsEstimator()


_ecologits_initialise = False


def init_ecologits(electricity_mix_zone: str | None = None) -> None:
    """`EcoLogits.init(providers=["anthropic"])` (AD-17) : le SDK renvoie alors `response.impacts`.

    À appeler une fois au démarrage d'un run qui utilise le provider Anthropic. Sans l'extra
    `energy`, lève `WlError` ; l'adaptateur lit `impacts` s'il existe et ne dépend pas de l'appel.
    """
    global _ecologits_initialise
    if _ecologits_initialise:  # une fois par processus : `init` patche le SDK
        return
    eco: Any = _importer("ecologits")
    eco.EcoLogits.init(providers=["anthropic"], electricity_mix_zone=electricity_mix_zone)
    _ecologits_initialise = True
