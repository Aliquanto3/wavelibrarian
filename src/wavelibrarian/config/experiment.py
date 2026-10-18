"""Schéma de l'Expérience `experiments/*.yaml` (contracts.md §4.4)."""

from datetime import date as Date
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from wavelibrarian.config.schemas import CostSettings, ProfileSettings, _Schema
from wavelibrarian.core.types import Condition
from wavelibrarian.ports.components import ComponentSpec

ID_PATTERN = r"^[a-z0-9-]+$"


class Amount(_Schema):
    amount: Decimal
    currency: str


class Budget(_Schema):
    """Plafonds de dépense par fournisseur ; défaut 5 $ Anthropic par Exécution."""

    per_run: dict[str, Amount] = {"anthropic": Amount(amount=Decimal("5.00"), currency="USD")}
    period: dict[str, Amount] = {}  # mois civil UTC


class JudgesSettings(_Schema):
    pool: tuple[str, ...] | None = Field(
        default=None, min_length=1
    )  # None : `profil.defaults.judge_pool`
    panel_size: int | None = Field(default=None, ge=1)  # None : `profil.defaults.panel_size`
    passes: int = 1
    calibration_passes: int = Field(default=5, ge=2)  # instabilité : au moins deux passes
    kappa_threshold: float = Field(default=0.6, ge=-1.0, le=1.0)
    calibration_judge: str | None = None
    excluded_from: str | None = None  # chemin d'un calibration.json


class StatsSettings(_Schema):
    resamples: int = 2000
    confidence: float = 0.95
    alpha: float = 0.05


class RetrySettings(_Schema):
    max_attempts: int = 3
    backoff_s: float = 1.0
    max_backoff_s: float = 30.0


class Configuration(_Schema):
    """Une Configuration : une Architecture et ses paramètres (validés par le registre)."""

    id: str = Field(pattern=ID_PATTERN)
    architecture: str
    parser: ComponentSpec = ComponentSpec(name="auto")
    reuse_index: str | None = None
    params: dict[str, Any] = {}


class Experiment(_Schema):
    experiment_id: str = Field(pattern=ID_PATTERN)
    seed: int = Field(strict=True)  # `"42"` ou `true` refusés (FR-9)
    profile: Literal["cpu", "gpu", "test"] = "cpu"
    corpus: str
    questions: str
    split: Literal["dev", "test"] = "dev"
    tier: int | Literal["all"] | None = None
    scenario: str | None = None
    conditions: tuple[Condition, ...] = ("standard",)
    catalog: str | None = None
    costs: str | None = None
    models_frozen_at: Date | None = None  # None : date du Catalogue
    max_questions: int | None = Field(default=None, ge=1, strict=True)
    # Au-delà (strictement), par Configuration : statut `completed_with_errors` (P9, story 8.3).
    max_error_rate: float = Field(default=0.2, ge=0.0, le=1.0, strict=True)
    budget: Budget = Budget()
    judges: JudgesSettings = JudgesSettings()
    stats: StatsSettings = StatsSettings()
    retries: RetrySettings = RetrySettings()
    configurations: tuple[Configuration, ...] = Field(min_length=1)


class ResolvedConfiguration(_Schema):
    id: str
    architecture: str
    parser: ComponentSpec  # `auto` remplacé avant le hachage par le runner (story 2.2 / 4.4)
    reuse_index: str | None
    params: dict[str, Any]
    models: tuple[str, ...]  # tous les modèles de la Configuration, sans doublon
    answer_producers: tuple[str, ...]  # ceux qui écrivent le texte de la Réponse (AD-14)


class ResolvedExperiment(_Schema):
    """L'Expérience telle qu'exécutée : défauts, profil, coûts et chemins résolus."""

    experiment_id: str
    seed: int
    profile: Literal["cpu", "gpu", "test"]
    profile_settings: ProfileSettings
    corpus: str
    questions: str
    split: Literal["dev", "test"]
    tier: int | Literal["all"] | None
    scenario: str | None
    conditions: tuple[Condition, ...]
    catalog: str | None  # None : Catalogue livré
    catalog_date: Date
    costs: CostSettings
    models_frozen_at: Date
    max_questions: int | None
    max_error_rate: float = 0.2  # défaut : relire une Exécution antérieure à la story 8.3
    budget: Budget
    judges: JudgesSettings
    stats: StatsSettings
    retries: RetrySettings
    configurations: tuple[ResolvedConfiguration, ...]
