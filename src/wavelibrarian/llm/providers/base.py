"""Contrat des providers (AD-3) : ils traduisent un `LLMRequest` en appel natif, rien de plus.

Ni plafond, ni cache, ni trace, ni coût : tout cela appartient à la passerelle.
"""

from dataclasses import dataclass
from typing import Protocol

from wavelibrarian.core.types import Usage
from wavelibrarian.ports.gateway import LLMRequest


@dataclass(frozen=True)
class ProviderResponse:
    """Texte et consommation déclarée par le fournisseur.

    `latency_s` : latence déclarée par le provider (le Faux LLM déclare 0) ; `None`, la
    passerelle mesure le temps de l'appel.
    """

    text: str
    usage: Usage
    latency_s: float | None = None


class Provider(Protocol):
    def complete(self, request: LLMRequest, *, timeout_s: float) -> ProviderResponse:
        """Lève `ProviderError(retryable=...)` en cas d'échec du fournisseur."""
        ...
