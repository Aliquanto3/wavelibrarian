"""Catalogue de modèles (FR-55) : seul endroit où un prix est calculé (AD-12)."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from wavelibrarian.config.defaults import charger_yaml, defaults_dir
from wavelibrarian.config.schemas import ModelEntry, _Schema, valider
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import Usage

_MTOK = Decimal(1_000_000)
_Poste = Literal["input", "output", "cache_read", "cache_write"]


class ModelCatalog(_Schema):
    """`models.yaml` entier."""

    catalog_date: date
    models: tuple[ModelEntry, ...]

    @model_validator(mode="after")
    def _ids_uniques(self) -> "ModelCatalog":
        vus: set[str] = set()
        for m in self.models:
            if m.id in vus:
                raise ValueError(f"identifiant de modèle en double : {m.id}")
            vus.add(m.id)
        return self

    def get(self, model_id: str) -> ModelEntry:
        for m in self.models:
            if m.id == model_id:
                return m
        dispo = ", ".join(m.id for m in self.models)
        raise ConfigError(
            "models", f"modèle inconnu du Catalogue : {model_id!r} (connus : {dispo})"
        )

    def cost(self, model_id: str, usage: Usage) -> Decimal:
        """Coût d'un appel dans la devise du fournisseur ; palier compris, `Decimal` seulement."""
        pricing = self.get(model_id).pricing
        if pricing is None:
            return Decimal(0)  # modèle local : coût de possession (FR-31)
        rates = pricing.per_mtok
        prompt = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
        mult = Decimal(1)
        for tier in pricing.tiers:
            if prompt > tier.above_prompt_tokens:
                mult = max(mult, tier.multiplier)
        postes: tuple[tuple[int, _Poste], ...] = (
            (usage.input_tokens, "input"),
            (usage.output_tokens, "output"),
            (usage.cache_read_tokens, "cache_read"),
            (usage.cache_write_tokens, "cache_write"),
        )
        total = Decimal(0)
        for tokens, poste in postes:
            if tokens:
                total += Decimal(tokens) * rates.get(poste, Decimal(0))
        return total / _MTOK * mult


def load_catalog(path: Path | None = None) -> ModelCatalog:
    """Charge `models.yaml` (celui du paquet par défaut)."""
    chemin = path or defaults_dir() / "models.yaml"
    return valider(ModelCatalog, charger_yaml(chemin), str(chemin))
