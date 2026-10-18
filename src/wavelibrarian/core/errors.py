"""Exceptions du banc ; `WlError` est la racine."""

from decimal import Decimal


class WlError(Exception):
    """Erreur de base du banc."""


class ConfigError(WlError):
    """Erreur de configuration, localisée par un chemin en notation pointée."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path} : {message}")


class ValidationFailed(WlError):
    """Regroupe toutes les erreurs de validation statique d'une Expérience."""

    def __init__(self, errors: list[ConfigError]) -> None:
        self.errors = errors
        super().__init__("\n".join(str(e) for e in errors))


class BudgetExceeded(WlError):
    """Le Plafond de dépense serait dépassé."""


class Inapplicable(WlError):
    """La configuration ne s'applique pas ; `reason` en donne la raison."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ProviderError(WlError):
    """Échec d'un fournisseur de modèle ; `retryable` indique si un nouvel essai a un sens.

    `sent` : la requête est partie sans réponse exploitable (délai dépassé après envoi) ; le
    fournisseur a pu facturer, la passerelle règle alors la réservation à l'estimation.
    """

    def __init__(self, message: str, retryable: bool = False, *, sent: bool = False) -> None:
        self.retryable = retryable
        self.sent = sent
        super().__init__(message)


class NonConformantOutput(WlError):
    """La sortie structurée d'un modèle ne respecte pas le schéma attendu.

    `cost_uncached` : coût hors cache de la tentative fautive (déjà tracée), pour que
    `complete_structured` le rende à l'appelant avec le nouvel essai.
    """

    def __init__(self, message: str, *, cost_uncached: Decimal = Decimal(0)) -> None:
        self.cost_uncached = cost_uncached
        super().__init__(message)
