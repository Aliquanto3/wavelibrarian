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
    # `false` : le modèle refuse `temperature` (AD-20 « si le fournisseur l'accepte ») ; la
    # passerelle la retire de la requête et de la clé de cache, et le span le signale.
    accepts_temperature: bool = True
    min_cacheable_tokens: int | None = None
    # Ollama : valeur du champ `think` envoyé ; `None` = champ non envoyé (modèle qui l'ignore
    # mal). Entre dans la clé du Cache de réponses via la requête effective (v0.2.0, P7).
    think: bool | None = False
    # Anthropic : `false` pour un modèle à thinking adaptatif toujours actif (Opus 5.5), qui
    # refuse `tool_choice` imposé (HTTP 400 relevé le 2026-10-26, story 8.11) : l'outil de sortie
    # part en `tool_choice: auto` avec une consigne de l'appeler.
    forced_tool_choice: bool = True
    # Tokens de sortie ajoutés au budget d'un Juge pour le thinking, compté dans `max_tokens`.
    thinking_reserve_tokens: int = Field(default=0, ge=0)
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


def valider[M: BaseModel](modele: type[M], donnees: Any, source: str = "", prefixe: str = "") -> M:
    """Valide `donnees` ; la première erreur devient une `ConfigError` au chemin pointé.

    `prefixe` place le chemin sous un nœud englobant (ex. `configurations[1].params`).
    """
    try:
        return modele.model_validate(donnees)
    except ValidationError as exc:
        raise config_error(exc.errors()[0], source, prefixe) from exc


def config_error(err: ErrorDetails, source: str = "", prefixe: str = "") -> ConfigError:
    """Une erreur pydantic devenue `ConfigError` au chemin pointé, sous `prefixe`."""
    chemin = _chemin(err)
    if prefixe:
        if chemin == "(racine)":
            chemin = prefixe
        else:
            chemin = prefixe + (chemin if chemin.startswith("[") else f".{chemin}")
    msg = _message(err)
    return ConfigError(chemin, f"{msg} ({source})" if source else msg)


_MESSAGES = {
    "missing": "champ obligatoire",
    "extra_forbidden": "champ inconnu",
    "string_type": "chaîne attendue",
    "int_type": "entier attendu",
    "int_parsing": "entier attendu",
    "int_from_float": "entier attendu",
    "float_type": "nombre attendu",
    "float_parsing": "nombre attendu",
    "decimal_type": "nombre attendu",
    "decimal_parsing": "nombre attendu",
    "bool_type": "booléen attendu (true ou false)",
    "bool_parsing": "booléen attendu (true ou false)",
    "dict_type": "dictionnaire attendu",
    "model_type": "dictionnaire attendu",
    "model_attributes_type": "dictionnaire attendu",
    "list_type": "liste attendue",
    "tuple_type": "liste attendue",
    "date_type": "date attendue (AAAA-MM-JJ)",
    "date_parsing": "date attendue (AAAA-MM-JJ)",
    "date_from_datetime_parsing": "date attendue (AAAA-MM-JJ)",
    "greater_than": "doit être strictement supérieur à {gt}",
    "greater_than_equal": "doit être supérieur ou égal à {ge}",
    "less_than": "doit être strictement inférieur à {lt}",
    "less_than_equal": "doit être inférieur ou égal à {le}",
    "too_short": "trop court : au moins {min_length} élément(s)",
    "too_long": "trop long : au plus {max_length} élément(s)",
    "literal_error": "valeur {input!r} non admise ; valeurs possibles : {expected}",
    "enum": "valeur {input!r} non admise ; valeurs possibles : {expected}",
}


def _message(err: ErrorDetails) -> str:
    """Message en français des types d'erreur pydantic courants (contracts.md, en-tête)."""
    modele = _MESSAGES.get(err["type"])
    if modele is None:
        return str(err["msg"]).removeprefix("Value error, ")
    ctx = {k: str(v).replace(" or ", " ou ") for k, v in (err.get("ctx") or {}).items()}
    try:
        return modele.format(input=err.get("input"), **ctx)
    except (KeyError, IndexError, ValueError):
        return str(err["msg"])
