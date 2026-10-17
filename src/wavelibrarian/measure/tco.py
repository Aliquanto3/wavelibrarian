"""Coût de possession du calcul local (FR-31, contracts.md §7) : toujours en euros, en `Decimal`."""

from decimal import Decimal

from wavelibrarian.config.schemas import CostSettings

_HEURE = Decimal(3600)


def possession_cost(
    costs: CostSettings,
    *,
    kwh: Decimal | float | str,
    compute_seconds: Decimal | float | str,
    index_gb: Decimal | float | str,
    months: Decimal | float | str = 1,
) -> Decimal:
    """kWh × prix du kWh + matériel ÷ durée de vie × heures + Go × prix du stockage × mois."""
    own = costs.owned_costs
    heures = Decimal(str(compute_seconds)) / _HEURE
    energie = Decimal(str(kwh)) * own.kwh_price_eur
    materiel = own.hardware_price_eur / Decimal(own.hardware_life_hours) * heures
    stockage = Decimal(str(index_gb)) * own.storage_eur_per_gb_month * Decimal(str(months))
    return energie + materiel + stockage
