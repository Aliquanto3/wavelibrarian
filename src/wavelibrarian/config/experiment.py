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
    pool: tuple[str, ...] | None = None  # None : `profil.defaults.judge_pool`
    panel_size: int | None = None  # None : `profil.defaults.panel_size`
    passes: int = 1
    calibration_passes: int = 5
    kappa_threshold: float = 0.6
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
    seed: int
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
    max_questions: int | None = None
    budget: Budget = Budget()
    judges: JudgesSettings = JudgesSettings()
    stats: StatsSettings = StatsSettings()
    retries: RetrySettings = RetrySettings()
    configurations: tuple[Configuration, ...] = Field(min_length=1)


class ResolvedConfiguration(_Schema):
    id: str
    architecture: str
    parser: ComponentSpec  # `auto` n'est remplacé que par le runner, qui connaît le Corpus
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
    budget: Budget
    judges: JudgesSettings
    stats: StatsSettings
    retries: RetrySettings
    configurations: tuple[ResolvedConfiguration, ...]
