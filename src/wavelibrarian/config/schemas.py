"""Schémas des fichiers de configuration livrés (contracts.md §2.3, §4.2 à §4.3)."""

from datetime import date as Date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import ErrorDetails

from wavelibrarian.core.errors import ConfigError


class _Schema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PriceTier(_Schema):
    """Palier de prix : au-delà de `above_prompt_tokens`, tous les postes sont multipliés."""

    above_prompt_tokens: int
    multiplier: Decimal


class Pricing(_Schema):
    date: Date
    currency: str
    per_mtok: dict[
        Literal["input", "output", "cache_read", "cache_write", "cache_write_1h"], Decimal
    ]
    batch_per_mtok: dict[str, Decimal] | None = None
    tiers: tuple[PriceTier, ...] = ()


class ModelEntry(_Schema):
    """Une entrée de `models.yaml`."""

    id: str
    provider: Literal["anthropic", "ollama", "sentence_transformers", "fake"]
    family: str
    kind: Literal["api", "local"]
    modality: Literal["llm", "embedding", "reranker"]
    context_window: int | None = None
    max_output_tokens: int | None = None
    tokenizer: Literal["reference", "approx"] = "reference"
    token_factor: Decimal = Decimal("1.2")
    prompt_cache: bool = False
    min_cacheable_tokens: int | None = None
    # `validate_default` : l'absence de `pricing` d'un modèle d'API est signalée à `...pricing`.
    pricing: Pricing | None = Field(default=None, validate_default=True)
    dim: int | None = None
    hf_repo: str | None = None
    query_prefix: str = ""
    passage_prefix: str = ""

    @field_validator("pricing")
    @classmethod
    def _api_sans_prix(cls, v: Pricing | None, info: Any) -> Pricing | None:
        kind = info.data.get("kind")
        if v is None:
            if kind == "api":
                raise ValueError("un modèle d'API doit déclarer son prix (`pricing`)")
            return v
        if kind == "local":
            raise ValueError("un modèle local n'a pas de `pricing` (coût de possession, FR-31)")
        requis = {"input", "output"}
        if info.data.get("prompt_cache"):
            requis |= {"cache_read", "cache_write"}
        manquants = sorted(requis - v.per_mtok.keys())
        if manquants:
            raise ValueError(f"tarif manquant dans `per_mtok` : {', '.join(manquants)}")
        return v


class FxRates(_Schema):
    date: Date
    source: str
    rates_to_eur: dict[str, Decimal]


class OwnedCosts(_Schema):
    date: Date
    kwh_price_eur: Decimal
    hardware_name: str
    hardware_price_eur: Decimal
    hardware_life_hours: int
    storage_eur_per_gb_month: Decimal


class CarbonIntensity(_Schema):
    region: str
    date: Date
    gco2e_per_kwh: Decimal
    note: str = ""


class CostSettings(_Schema):
    """`costs.yaml` (§4.2 bis) : tout ce qui dépend de la machine, du pays ou de la date."""

    fx: FxRates
    owned_costs: OwnedCosts
    carbon: CarbonIntensity


class OllamaSettings(_Schema):
    base_url: str
    keep_alive: str
    options: dict[str, Any] = {}


class EnergySettings(_Schema):
    local: Literal["codecarbon", "fake"]
    api: Literal["ecologits", "fake"]
    country_iso_code: str = "FRA"


class RoleDefaults(_Schema):
    generator_models: tuple[str, ...]
    embedder: str
    judge_pool: tuple[str, ...]
    panel_size: int
    closed_book_models: tuple[str, ...]
    question_gen_model: str
    call_timeout_s: int


class ProfileSettings(_Schema):
    """Profil d'exécution `defaults/profiles/<nom>.yaml` (§4.3)."""

    profile: Literal["cpu", "gpu", "test"]
    ollama: OllamaSettings
    embedder_device: str
    tokenizer: Literal["reference", "approx"]
    energy: EnergySettings
    defaults: RoleDefaults

    def model_ids(self) -> set[str]:
        """Tous les modèles cités par le profil."""
        d = self.defaults
        return {
            *d.generator_models,
            d.embedder,
            *d.judge_pool,
            *d.closed_book_models,
            d.question_gen_model,
        }


def _chemin(err: ErrorDetails) -> str:
    chemin = ""
    for part in err["loc"]:
        chemin += f"[{part}]" if isinstance(part, int) else (f".{part}" if chemin else str(part))
    return chemin or "(racine)"


def valider[M: BaseModel](modele: type[M], donnees: Any, source: str = "") -> M:
    """Valide `donnees` ; la première erreur devient une `ConfigError` au chemin pointé."""
    try:
        return modele.model_validate(donnees)
    except ValidationError as exc:
        err = exc.errors()[0]
        chemin = _chemin(err)
        msg = str(err["msg"]).removeprefix("Value error, ")
        raise ConfigError(chemin, f"{msg} ({source})" if source else msg) from exc
