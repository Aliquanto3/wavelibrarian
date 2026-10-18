"""Traces OpenTelemetry (AD-8, AD-11, contracts.md §6) : un span par appel, écrit en JSONL local."""

import json
import logging
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
from wavelibrarian.measure.energy import EnergyMethod, spread_energy

# Spans d'un calcul local : leur énergie est relevée par phase, puis répartie (AD-17).
_LOCAUX = frozenset({"local", "embed", "rerank"})


_log = logging.getLogger(__name__)

_Retenu = tuple[str, int, int, float, dict[str, str | int | float | bool]]


def temps_propre(mur_s: float, deja_traces_s: float) -> float:
    """Temps d'une étape hors spans déjà tracés pendant elle ; un écart négatif (latence déclarée
    par un provider supérieure au temps mural) est ramené à 0 et signalé."""
    propre = mur_s - deja_traces_s
    if propre < 0:
        _log.warning(
            "temps propre négatif (%.6f s : %.6f s mesurés, %.6f s déjà tracés), ramené à 0",
            propre,
            mur_s,
            deja_traces_s,
        )
        return 0.0
    return propre


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
        self.latency_total = 0.0  # somme des `wl.latency_s` de tous les spans enregistrés
        # Temps réellement passé dans ces spans : un hit du Cache de réponses porte la latence
        # de l'appel d'origine (p50/p95 comparables au rejeu) mais n'a rien coûté en temps.
        self.elapsed_total = 0.0
        self._phase: list[_Retenu] | None = None
        # Reprise (story 4.8) : clés (config_id, condition, tier, phase, question_id) de Questions
        # interrompues dont les appels déjà tracés sont refaits ; un hit du cache sur l'une d'elles
        # porte `wl.resumed`, pour que le Rapport ne recompte ni l'appel ni sa latence.
        self.reprises: frozenset[tuple[str, str, int | None, str, str]] = frozenset()

    def begin_phase(self) -> None:
        """Retient les spans locaux jusqu'à `end_phase` : leur énergie n'est connue qu'en fin de
        phase et `traces.jsonl` n'est jamais réécrit (AD-17)."""
        if self._phase is not None:
            raise WlError("phase d'énergie déjà ouverte")
        self._phase = []

    def end_phase(self, kwh: float | None, method: EnergyMethod = "estimated") -> None:
        """Répartit `kwh` sur les spans locaux retenus (prorata du temps réellement passé, un
        hit du cache ne compte pas), puis les écrit."""
        tampon, self._phase = self._phase, None
        if not tampon:
            return
        parts = spread_energy(kwh, [latence for *_, latence, _ in tampon], method)
        for (step, debut, fin, _, attrs), (energie, methode) in zip(tampon, parts, strict=True):
            if energie is not None:
                attrs["wl.energy_kwh"] = energie
                attrs["wl.energy_method"] = methode
            else:
                attrs.setdefault("wl.energy_method", "unknown")
            self._emettre(step, debut, fin, attrs)

    def _emettre(
        self, step: str, debut: int, fin: int, attrs: dict[str, str | int | float | bool]
    ) -> None:
        avant = self.exporter.ecrits
        span = self._tracer.start_span(step, start_time=debut, attributes=attrs)
        span.end(end_time=fin)
        if self.exporter.ecrits != avant + 1:
            # Les traces sont la seule source des coûts : une ligne perdue arrête l'Exécution.
            erreur, self.exporter.erreur = self.exporter.erreur, None
            cause = f" : {erreur}" if erreur else " (SDK OpenTelemetry désactivé ?)"
            raise WlError(f"trace `{step}` non écrite dans {self.exporter.path}{cause}") from erreur

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
        if (
            from_cache
            and ctx.post == "query"
            and (ctx.config_id, ctx.condition, ctx.tier, ctx.phase, ctx.question_id or "")
            in self.reprises
        ):
            attrs["wl.resumed"] = True
        reel = 0.0 if from_cache else float(latency_s)
        self.latency_total += float(latency_s)
        self.elapsed_total += reel
        local = kind in _LOCAUX or (kind == "llm" and provider == "ollama")
        if self._phase is not None and local:
            self._phase.append((step, debut, fin, reel, attrs))
            return
        self._emettre(step, debut, fin, attrs)


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
