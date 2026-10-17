"""Traces OpenTelemetry (AD-8, AD-11, contracts.md §6) : un span par appel, écrit en JSONL local."""

import json
import time
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import Condition, CostPost, Phase, Usage


class TraceContext(Protocol):
    """Partie du `RunContext` lue par le Tracer, au moment de chaque `record`."""

    run_id: str
    config_id: str
    condition: Condition
    tier: int | None
    phase: Phase

    @property
    def post(self) -> CostPost: ...

    @property
    def question_id(self) -> str | None: ...


class JsonlSpanExporter(SpanExporter):
    """Une ligne JSON par span : identifiants, nom, bornes en ns, puis les attributs à plat."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.ecrits = 0  # spans effectivement écrits
        self.erreur: OSError | None = None  # dernière écriture ratée (le processeur l'avale)
        path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        lignes = []
        for span in spans:
            ctx = span.get_span_context()
            ligne: dict[str, Any] = {
                "trace_id": format(ctx.trace_id, "032x") if ctx else "",
                "span_id": format(ctx.span_id, "016x") if ctx else "",
                "name": span.name,
                "start_time": span.start_time,
                "end_time": span.end_time,
            }
            ligne.update(dict(span.attributes or {}))
            lignes.append(json.dumps(ligne, ensure_ascii=False))
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write("\n".join(lignes) + "\n")
        except OSError as exc:
            self.erreur = exc
            return SpanExportResult.FAILURE
        self.ecrits += len(lignes)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


class Tracer:
    """Implémente le port `Tracer`. Export local synchrone ; OTLP désactivé par défaut."""

    def __init__(
        self, context: TraceContext, path: Path, *, otlp_endpoint: str | None = None
    ) -> None:
        self._ctx = context
        self.exporter = JsonlSpanExporter(path)
        self.processor = SimpleSpanProcessor(self.exporter)
        # Échantillonnage explicite : `OTEL_TRACES_SAMPLER` ne doit écarter aucun span.
        self._provider = TracerProvider(sampler=ALWAYS_ON)
        self._provider.add_span_processor(self.processor)
        if otlp_endpoint is not None:
            self._provider.add_span_processor(_otlp_processor(otlp_endpoint))
        self._tracer = self._provider.get_tracer("wavelibrarian")

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
        ctx = self._ctx
        fin = time.time_ns()
        debut = fin - int(latency_s * 1e9)
        attrs: dict[str, str | int | float | bool] = dict(extra)
        attrs.update(
            {
                "wl.run_id": ctx.run_id,
                "wl.config_id": ctx.config_id,
                "wl.question_id": ctx.question_id or "",
                "wl.condition": ctx.condition,
                "wl.phase": ctx.phase,
                "wl.post": ctx.post,
                "wl.step": step,
                "wl.kind": kind,
                "gen_ai.usage.input_tokens": usage.input_tokens,
                "gen_ai.usage.output_tokens": usage.output_tokens,
                "wl.usage.cache_read_tokens": usage.cache_read_tokens,
                "wl.usage.cache_write_tokens": usage.cache_write_tokens,
                "wl.cost": str(cost),
                "wl.cost_uncached": str(cost_uncached),
                "wl.currency": currency,
                "wl.llm_cache_hit": from_cache,
                "wl.latency_s": float(latency_s),
                "wl.status": status,
            }
        )
        if ctx.tier is not None:
            attrs["wl.tier"] = ctx.tier
        if provider is not None:
            attrs["gen_ai.provider.name"] = provider
        if model_id is not None:
            attrs["gen_ai.request.model"] = model_id
        avant = self.exporter.ecrits
        span = self._tracer.start_span(step, start_time=debut, attributes=attrs)
        span.end(end_time=fin)
        if self.exporter.ecrits != avant + 1:
            # Les traces sont la seule source des coûts : une ligne perdue arrête l'Exécution.
            erreur, self.exporter.erreur = self.exporter.erreur, None
            cause = f" : {erreur}" if erreur else " (SDK OpenTelemetry désactivé ?)"
            raise WlError(f"trace `{step}` non écrite dans {self.exporter.path}{cause}") from erreur


def _otlp_processor(endpoint: str) -> Any:
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
            OTLPSpanExporter,
        )
    except ImportError as exc:
        raise WlError(
            "export OTLP demandé mais `opentelemetry-exporter-otlp` n'est pas installé"
        ) from exc
    return SimpleSpanProcessor(OTLPSpanExporter(endpoint=endpoint))  # AD-11 : synchrone
