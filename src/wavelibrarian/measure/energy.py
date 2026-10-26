"""Énergie (AD-17) : mesure locale par phase, estimation API par appel, répartition au prorata.

`measured` seulement si toutes les parts suivies sont lues par un compteur matériel, `mixed` si une
part est lue et une autre estimée par formule (la RAM de codecarbon l'est toujours), `estimated`
si aucune n'est lue ; `codecarbon` et `ecologits` sont importés au premier usage (extra `energy`).
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

EnergyMethod = Literal["measured", "mixed", "estimated", "unknown"]

_MSG_EXTRA = "installer l'extra energy (`uv sync --extra energy`) : module {} introuvable"
# Modes de codecarbon qui lisent un compteur matériel (RAPL, Power Gadget, powermetrics, NVML,
# Energy Meter Interface de Windows : il suit la charge, mesure de la story 8.6).
_MODES_MATERIELS = frozenset(
    {"intel_rapl", "intel_power_gadget", "apple_powermetrics", "nvml", "windows_emi"}
)


def _importer(nom: str) -> Any:
    try:
        return importlib.import_module(nom)
    except ImportError as exc:
        raise WlError(_MSG_EXTRA.format(nom)) from exc


def spread_energy(
    kwh: float | None, latencies_s: Sequence[float], method: EnergyMethod
) -> list[tuple[float | None, EnergyMethod]]:
    """Répartit l'énergie d'une phase sur ses spans locaux au prorata de leur latence.

    Chaque span reçoit `(kWh, méthode)` ; sans énergie connue : `(None, "unknown")`. Si aucun
    span n'a de durée, l'énergie relevée est répartie à parts égales plutôt que perdue. Les hits
    du Cache sont exclus en amont (`Tracer.end_phase`) : ils ne reçoivent aucune énergie.
    """
    total = sum(latencies_s)
    if kwh is None or not latencies_s:
        return [(None, "unknown")] * len(latencies_s)
    if total <= 0:
        return [(kwh / len(latencies_s), method)] * len(latencies_s)
    return [(kwh * lat / total, method) for lat in latencies_s]


class FakeMeter:
    """Mesureur factice (profil `test`) : énergie fixe, jamais `measured`."""

    method: EnergyMethod = "estimated"
    source = "fake"

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


def _materiels_suivis(tracker: Any, gpu: bool = False) -> list[Any]:
    """Matériels de codecarbon dont l'énergie compte vraiment. Un `GPU` n'en fait partie que si
    le GPU est demandé (`gpu`, champ `energy.gpu` : `gpu_ids=None`, tous les GPU visibles) ou si
    `tracker._gpu_ids` (sinon `gpu_ids` du matériel) désigne au moins un GPU : codecarbon 3.3.x
    instancie un `GPU` même avec `gpu_ids=[]` et, dès le 2e tracker du processus, y remet tous
    les GPU détectés (`[0]`), d'où `nvml` à tort sur un poste NVIDIA sans GPU actif."""
    voulus = getattr(tracker, "_gpu_ids", None)
    suivis = []
    for hw in getattr(tracker, "_hardware", None) or []:
        if type(hw).__name__ == "GPU" and not gpu:
            ids = voulus if voulus is not None else getattr(hw, "gpu_ids", None)
            if not ids:
                continue
        suivis.append(hw)
    return suivis


def _mode(hw: Any) -> str:
    if type(hw).__name__ == "GPU":
        return "nvml"
    return str(getattr(hw, "_mode", "") or getattr(hw, "mode", "")).lower()


def energy_source(tracker: Any, gpu: bool = False) -> str:
    """Mode du compteur lu par codecarbon (`wl.energy_source`, contracts.md §6) : `nvml` pour un
    GPU suivi, sinon le mode matériel s'il y en a un, sinon le premier mode connu, sinon
    `unknown`. Un GPU non suivi (hors `gpu_ids`, ou GPU désactivé) ne donne rien. Toujours une
    chaîne, même sans compteur. La RAM de codecarbon n'a pas de mode : sa part est estimée par
    formule, quel que soit le compteur CPU ou GPU."""
    modes = [m for m in (_mode(hw) for hw in _materiels_suivis(tracker, gpu)) if m]
    if "nvml" in modes:  # le GPU domine l'énergie d'une phase qui en suit un
        return "nvml"
    for mode in modes:
        if mode in _MODES_MATERIELS:
            return mode
    return modes[0] if modes else "unknown"


def is_hardware_counter(tracker: Any) -> bool:
    """Vrai si l'un des matériels suivis par codecarbon a été lu sur un compteur matériel."""
    return any(_mode(hw) in _MODES_MATERIELS for hw in _materiels_suivis(tracker))


def energy_method(tracker: Any, gpu: bool = False) -> EnergyMethod:
    """Méthode d'une phase (contracts.md §6, AD-17, A8) : `measured` si toutes les parts suivies
    sont lues par un compteur matériel ; `mixed` si une part est lue et une autre estimée par
    formule (la RAM de codecarbon, sans compteur DRAM, l'est toujours : CPU `windows_emi` de la
    story 8.6 ou GPU NVML à côté d'elle) ; `estimated` si aucune part n'est lue."""
    lues = [_mode(hw) in _MODES_MATERIELS for hw in _materiels_suivis(tracker, gpu)]
    if not any(lues):
        return "estimated"
    return "measured" if all(lues) else "mixed"


def _retirer_gpu(tracker: Any) -> None:
    """`gpu_ids=[]` ne suffit pas : retirer le GPU garde son énergie (au repos) hors de la phase.
    codecarbon 3.3.x ne remplit `_hardware` qu'au `start()` (`_ensure_hardware_ready`, idempotent) :
    on l'initialise d'abord, sinon le filtre porterait sur une liste vide. API privée : si elle
    change, avertissement et mesure inchangée, sans exception."""
    try:
        preparer = getattr(tracker, "_ensure_hardware_ready", None)
        if callable(preparer):
            preparer()
        materiels = getattr(tracker, "_hardware", None)
        if not isinstance(materiels, list):
            raise AttributeError("`_hardware` absent")
        tracker._hardware = [hw for hw in materiels if type(hw).__name__ != "GPU"]
    except Exception as exc:
        _log.warning("codecarbon : GPU non retiré de la mesure (%s)", exc)


class CodecarbonMeter:
    """Énergie locale par phase via `codecarbon.OfflineEmissionsTracker`. CPU seul, sans NVML,
    par défaut (fix-8-8) ; `gpu=True` (champ `energy.gpu` du profil `gpu`) suit tous les GPU
    visibles (`gpu_ids=None` : codecarbon 3.3.x respecte alors `CUDA_VISIBLE_DEVICES`)."""

    def __init__(self, country_iso_code: str = "FRA", *, gpu: bool = False) -> None:
        self._cc = _importer("codecarbon")
        self._country = country_iso_code
        self._gpu = gpu
        self._tracker: Any = None
        self.method: EnergyMethod = "estimated"
        self.source = "unknown"  # mode du compteur lu à la dernière phase (`wl.energy_source`)

    def start(self, phase: str) -> None:
        self._tracker = self._cc.OfflineEmissionsTracker(
            country_iso_code=self._country,
            project_name=phase,
            save_to_file=False,
            log_level="error",
            gpu_ids=None if self._gpu else [],  # sans `energy.gpu`, jamais d'interrogation du GPU
        )
        if not self._gpu:
            _retirer_gpu(self._tracker)
        self._tracker.start()

    def stop(self) -> float | None:
        tracker, self._tracker = self._tracker, None
        if tracker is None:
            return None
        tracker.stop()
        self.method = energy_method(tracker, self._gpu)
        self.source = energy_source(tracker, self._gpu)
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
    return CodecarbonMeter(settings.country_iso_code, gpu=settings.gpu)


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
