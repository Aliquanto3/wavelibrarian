"""Passerelle mesurée (AD-3) : point de passage unique de tout appel de modèle.

Ordre fixe : marqueur de rôle, cache, réservation au registre, appel (essais exponentiels),
coût par le Catalogue, règlement, mise en cache, span. Seule la passerelle émet les spans LLM.
"""

import json
import logging
import time
from collections.abc import Callable, Mapping
from decimal import Decimal
from math import ceil
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from wavelibrarian.config.catalog import ModelCatalog
from wavelibrarian.config.experiment import RetrySettings
from wavelibrarian.config.schemas import OllamaSettings
from wavelibrarian.core.errors import BudgetExceeded, NonConformantOutput, ProviderError, WlError
from wavelibrarian.core.types import Usage
from wavelibrarian.llm.budget import Ledger
from wavelibrarian.llm.cache import ResponseCache, cache_key, role_marker
from wavelibrarian.llm.providers.base import Provider, ProviderResponse
from wavelibrarian.llm.providers.logs import (  # réexport pour run.log (AD-3)
    limiter_journaux as limiter_journaux,
)
from wavelibrarian.llm.roles import check_inputs
from wavelibrarian.ports.gateway import LLMRequest, LLMResult
from wavelibrarian.ports.measure import EnergyEstimator, Tokenizer, Tracer

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)

Providers = Mapping[str, Provider]  # nom du Catalogue -> adaptateur ; seul `gateway` les importe
_DEVISE_LOCALE = "EUR"  # modèle local : coût nul, devise du coût de possession (costs.yaml)
_Statut = Literal["ok", "error", "budget_refused", "non_conformant"]


def build_providers(catalog: ModelCatalog, ollama: OllamaSettings) -> dict[str, Provider]:
    """Adaptateurs du Catalogue : `anthropic` (clé lue au premier appel), `ollama` (`num_ctx`
    tiré du `context_window` du Catalogue) et `fake`. Seule la passerelle importe les providers."""
    from wavelibrarian.llm.providers.anthropic import AnthropicProvider
    from wavelibrarian.llm.providers.fake import FakeProvider
    from wavelibrarian.llm.providers.ollama import OllamaProvider

    fenetres = {
        m.id: m.context_window
        for m in catalog.models
        if m.provider == "ollama" and m.context_window is not None
    }
    return {
        "anthropic": AnthropicProvider(),
        "ollama": OllamaProvider(ollama, context_windows=fenetres),
        "fake": FakeProvider(),
    }


class MeteredGateway:
    """Implémente le port `ModelGateway`."""

    def __init__(
        self,
        *,
        catalog: ModelCatalog,
        providers: Providers,
        ledger: Ledger,
        cache: ResponseCache,
        tracer: Tracer,
        tokenizer_for: Callable[[str], Tokenizer],
        estimator: EnergyEstimator,
        retries: RetrySettings | None = None,
        default_timeout_s: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        """`tokenizer_for` : `RunContext.tokenizer_for` ; `sleep` et `timer` sont injectables."""
        self._catalog = catalog
        self._providers = providers
        self._ledger = ledger
        self._cache = cache
        self._tracer = tracer
        self._tokenizer_for = tokenizer_for
        self._estimator = estimator
        self._retries = retries or RetrySettings()
        self._timeout = default_timeout_s
        self._sleep = sleep
        self._timer = timer

    # --- API publique ------------------------------------------------------------------------

    def complete(self, request: LLMRequest, *, use_cache: bool = True) -> LLMResult:
        """`use_cache=False` : ne lit pas le Cache de réponses (l'appel part toujours chez le
        fournisseur) ; la réponse remplace l'entrée. Sert au préchargement CAG (story 6.5)."""
        return self._run(request, None, use_cache=use_cache)[1]

    def complete_structured(
        self, request: LLMRequest, schema: type[T], *, use_cache: bool = True
    ) -> tuple[T, LLMResult]:
        """Un nouvel essai (sans lecture du cache) si la sortie ne valide pas `schema`.
        `use_cache=False` : ne lit pas le Cache (passes de calibration, story 5.2)."""
        try:
            valeur, resultat = self._run(request, schema, use_cache=use_cache)
        except NonConformantOutput as fautive:
            valeur, resultat = self._run(request, schema, use_cache=False)
            resultat = resultat.model_copy(update={"retry_cost_uncached": fautive.cost_uncached})
        assert valeur is not None
        return valeur, resultat

    # --- Pipeline ----------------------------------------------------------------------------

    @staticmethod
    def _marquer(request: LLMRequest) -> LLMRequest:
        if "[[wl:role=" in request.system:
            raise WlError("le marqueur `[[wl:role=…]]` est posé par la passerelle seule (AD-4)")
        return request.model_copy(update={"system": role_marker(request.role) + request.system})

    def _estimation(
        self, request: LLMRequest, provider: Provider, schema_json: dict[str, Any] | None
    ) -> Usage:
        """Tokens d'entrée × `token_factor` + `max_tokens`, palier compris (via le Catalogue).

        Majorant : un prompt qui peut être mis en cache est compté au tarif d'écriture. Le schéma
        de sortie compte comme entrée quand le provider l'envoie dans le prompt (outil), pas quand
        il part dans `format` (grammaire d'Ollama).
        """
        entry = self._catalog.get(request.model_id)
        morceaux = [request.system, *(m.content for m in request.messages)]
        surcout = 0
        if schema_json is not None and getattr(provider, "schema_in_prompt", False):
            morceaux.append(json.dumps(schema_json, ensure_ascii=False, sort_keys=True))
            surcout = int(getattr(provider, "schema_prompt_overhead", 0))
        n = self._tokenizer_for(request.model_id).count("\n".join(morceaux))
        if entry.tokenizer == "reference":  # `tokenizer_for` n'a pas appliqué le facteur
            n = ceil(Decimal(n) * entry.token_factor)
        n += surcout
        marque = request.cache_system or any(m.cache for m in request.messages)
        if entry.prompt_cache and marque:
            return Usage(cache_write_tokens=n, output_tokens=request.max_tokens)
        return Usage(input_tokens=n, output_tokens=request.max_tokens)

    def _appeler(
        self, provider: Provider, request: LLMRequest, schema_json: dict[str, Any] | None
    ) -> ProviderResponse:
        timeout = request.timeout_s if request.timeout_s is not None else self._timeout
        for tentative in Retrying(
            stop=stop_after_attempt(self._retries.max_attempts),
            wait=wait_exponential(
                multiplier=self._retries.backoff_s, max=self._retries.max_backoff_s
            ),
            # Un essai `sent` (parti sans réponse) a pu être facturé : jamais relancé (AD-9).
            retry=retry_if_exception(
                lambda e: isinstance(e, ProviderError) and e.retryable and not e.sent
            ),
            sleep=self._sleep,
            reraise=True,
        ):
            with tentative:
                return provider.complete(request, timeout_s=timeout, output_schema=schema_json)
        raise AssertionError("inatteignable")  # pragma: no cover

    def _trace(
        self,
        request: LLMRequest,
        provider: str,
        currency: str,
        statut: _Statut,
        *,
        usage: Usage | None = None,
        cost: Decimal = Decimal(0),
        cost_uncached: Decimal = Decimal(0),
        latency_s: float = 0.0,
        from_cache: bool = False,
        energie: bool = False,
        energy_kwh: float | None = None,
        raw_output: str | None = None,
    ) -> None:
        usage = usage or Usage()
        extra: dict[str, str | int | float | bool] = {}
        if request.temperature is None:
            extra["wl.temperature_omitted"] = True
        if provider == "ollama" and request.think is None:
            extra["wl.think_omitted"] = True
        if raw_output is not None:  # sortie non conforme : son début, pour le diagnostic
            extra["wl.raw_output"] = raw_output[: NonConformantOutput.RAW_OUTPUT_MAX]
        if energie:
            kwh = None
            if self._catalog.get(request.model_id).kind == "api":
                kwh = energy_kwh  # lue par le provider dans la réponse (EcoLogits)
                if kwh is None:
                    kwh = self._estimator.estimate(request.model_id, usage, latency_s)
            # Local : énergie mesurée par phase et répartie par le runner (AD-17), inconnue ici.
            extra["wl.energy_method"] = "estimated" if kwh is not None else "unknown"
            if kwh is not None:
                extra["wl.energy_kwh"] = kwh
        self._tracer.record(
            request.step,
            "llm",
            model_id=request.model_id,
            provider=provider,
            usage=usage,
            cost=cost,
            cost_uncached=cost_uncached,
            currency=currency,
            latency_s=latency_s,
            from_cache=from_cache,
            status=statut,
            extra=extra,
        )

    def _run(
        self, request: LLMRequest, schema: type[T] | None, *, use_cache: bool
    ) -> tuple[T | None, LLMResult]:
        check_inputs(request)  # clé d'`inputs` manquante : refus avant tout appel (AD-4)
        entry = self._catalog.get(request.model_id)
        nom = entry.provider
        provider = self._providers.get(nom)
        if provider is None:
            raise WlError(f"aucun provider `{nom}` branché pour le modèle {request.model_id!r}")
        devise = entry.pricing.currency if entry.pricing else _DEVISE_LOCALE
        marquee = self._marquer(request)
        if not entry.accepts_temperature and marquee.temperature is not None:
            # AD-20 : `temperature` ne part que si le modèle l'accepte ; la clé de cache reflète
            # la requête effective, et le span porte `wl.temperature_omitted`.
            marquee = marquee.model_copy(update={"temperature": None})
        if nom == "ollama" and marquee.think != entry.think:
            # Story 8.4 : `think` effectif du Catalogue, repris dans la clé de cache.
            marquee = marquee.model_copy(update={"think": entry.think})
        schema_json = schema.model_json_schema() if schema is not None else None
        # Après le marquage : le rôle entre dans la clé ; le schéma aussi (il change la requête).
        # Story 8.7 : options Ollama du profil (`repeat_penalty`…) dans la clé, comme `think`.
        options = getattr(provider, "cache_options", None) if nom == "ollama" else None
        cle = cache_key(marquee, nom, schema_json, options(marquee) if options else None)

        cached = self._cache.get(cle) if use_cache else None
        if cached is not None:
            return self._finir(
                marquee, schema, nom, devise, cached.text, cached.usage,
                cost=Decimal(0),
                cost_uncached=self._catalog.cost(request.model_id, cached.usage),
                latency_s=cached.latency_s, from_cache=True, stocker=None,
            )  # fmt: skip

        estimation = self._catalog.cost(
            request.model_id, self._estimation(marquee, provider, schema_json)
        )
        try:
            reservation = self._ledger.reserve(nom, estimation, devise)
        except BudgetExceeded:
            self._trace(marquee, nom, devise, "budget_refused")
            raise

        debut = self._timer()
        try:
            reponse = self._appeler(provider, marquee, schema_json)
        except BaseException as exc:
            latence = self._timer() - debut
            if isinstance(exc, ProviderError) and exc.sent:
                # Requête partie sans réponse (délai dépassé) : le fournisseur a pu facturer.
                try:
                    self._ledger.settle(reservation, estimation)
                finally:
                    self._trace_paye_en_erreur(marquee, nom, devise, Usage(), estimation, latence)
                raise
            self._ledger.release(reservation)
            self._trace(marquee, nom, devise, "error", latency_s=latence)
            raise
        latence = self._timer() - debut
        if reponse.latency_s is not None:  # latence déclarée (Faux LLM : 0, contracts.md §3)
            latence = reponse.latency_s
        # Appel payé : un span porte son coût quoi qu'il arrive (traces.jsonl, source des coûts).
        cout, panne = estimation, None
        try:
            cout = self._catalog.cost(request.model_id, reponse.usage)
        except Exception as e:  # au moins l'estimation
            panne = e
        try:
            self._ledger.settle(reservation, cout)
        except BaseException:
            self._trace_paye_en_erreur(marquee, nom, devise, reponse.usage, cout, latence)
            # Arrêt pendant le règlement : la réponse est payée (réservation réglée à l'estimé à
            # la reprise) ; conforme, elle va au cache pour que la reprise ne la repaie pas.
            self._cacher_si_conforme(schema, cle, reponse.text, reponse.usage, latence, use_cache)
            raise
        if panne is not None:
            self._trace_paye_en_erreur(marquee, nom, devise, reponse.usage, cout, latence)
            raise panne
        return self._finir(
            marquee, schema, nom, devise, reponse.text, reponse.usage,
            cost=cout, cost_uncached=cout, latency_s=latence, from_cache=False, stocker=cle,
            remplacer=not use_cache, energy_kwh=reponse.energy_kwh,
        )  # fmt: skip

    def _cacher_si_conforme(
        self,
        schema: type[BaseModel] | None,
        cle: str,
        texte: str,
        usage: Usage,
        latence: float,
        use_cache: bool,
    ) -> None:
        """Mise en cache au mieux d'une réponse payée dont le règlement a échoué : seulement un
        succès de schéma, et sans jamais masquer l'exception en cours."""
        try:
            if schema is not None:
                schema.model_validate_json(texte)
            self._cache.put(cle, texte, usage, replace=not use_cache, latency_s=latence)
        except Exception:
            log.warning("réponse payée non mise en cache après un règlement interrompu")

    def _trace_paye_en_erreur(
        self, request: LLMRequest, nom: str, devise: str, usage: Usage, cout: Decimal, lat: float
    ) -> None:
        self._trace(
            request, nom, devise, "error", usage=usage, cost=cout, cost_uncached=cout, latency_s=lat
        )

    def _finir(
        self,
        request: LLMRequest,
        schema: type[T] | None,
        nom: str,
        devise: str,
        texte: str,
        usage: Usage,
        *,
        cost: Decimal,
        cost_uncached: Decimal,
        latency_s: float,
        from_cache: bool,
        stocker: str | None,
        remplacer: bool = False,
        energy_kwh: float | None = None,
    ) -> tuple[T | None, LLMResult]:
        """Valide la sortie structurée, trace, puis ne met en cache que les succès.

        Le span part avant `put` : un échec du cache ne fait pas perdre le coût payé.
        `remplacer` : essai qui a contourné le cache, sa réponse conforme remplace l'entrée.
        """
        valeur: T | None = None
        statut: _Statut = "ok"
        if schema is not None:
            try:
                valeur = schema.model_validate_json(texte)
            except ValidationError:
                statut = "non_conformant"
        self._trace(
            request, nom, devise, statut, usage=usage, cost=cost, cost_uncached=cost_uncached,
            latency_s=latency_s, from_cache=from_cache, energie=not from_cache,
            energy_kwh=energy_kwh, raw_output=texte if statut == "non_conformant" else None,
        )  # fmt: skip
        if statut == "ok" and stocker is not None:
            self._cache.put(stocker, texte, usage, replace=remplacer, latency_s=latency_s)
        if statut == "non_conformant":
            raise NonConformantOutput(
                f"sortie de {request.model_id!r} non conforme au schéma "
                f"{schema.__name__ if schema else '?'}",
                cost_uncached=cost_uncached,
                raw_output=texte,
            )
        resultat = LLMResult(
            text=texte, usage=usage, cost=cost, cost_uncached=cost_uncached, currency=devise,
            latency_s=latency_s, from_cache=from_cache,
        )  # fmt: skip
        return valeur, resultat
