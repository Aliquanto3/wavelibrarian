"""Mesure : tokenizer, traces, énergie (contracts.md §2.2). Aucune entrée-sortie."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal, Protocol

from wavelibrarian.core.types import Usage


class Tokenizer(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class Tracer(Protocol):
    def record(
        self,
        step: str,
        kind: Literal["llm", "embed", "rerank", "local"],
        *,
        model_id: str | None,
        provider: str | None,
        usage: Usage,
        cost: Decimal,
        cost_uncached: Decimal,
        currency: str,
        latency_s: float,
        from_cache: bool,
        status: str = "ok",
        extra: Mapping[str, str | int | float | bool] = {},
    ) -> None:
        """run_id, config_id, question_id, post et condition viennent du RunContext (AD-8)."""
        ...


class EnergyMeter(Protocol):
    """Local : mesuré par phase."""

    def start(self, phase: str) -> None: ...
    def stop(self) -> float | None: ...  # kWh, None si indisponible


class EnergyEstimator(Protocol):
    """API : estimé par appel."""

    def estimate(self, model_id: str, usage: Usage, latency_s: float) -> float | None: ...
