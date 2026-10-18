"""Contrat des providers (AD-3) : ils traduisent un `LLMRequest` en appel natif, rien de plus.

Ni plafond, ni cache, ni trace, ni coût : tout cela appartient à la passerelle.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from wavelibrarian.core.types import Usage
from wavelibrarian.ports.gateway import LLMRequest


@dataclass(frozen=True)
class ProviderResponse:
    """Texte et consommation déclarée par le fournisseur.

    `latency_s` : latence déclarée par le provider (le Faux LLM déclare 0) ; `None`, la
    passerelle mesure le temps de l'appel. `energy_kwh` : énergie estimée lue par le provider
    dans la réponse (EcoLogits), `None` si absente ; la passerelle retombe alors sur l'estimateur.
    """

    text: str
    usage: Usage
    latency_s: float | None = None
    energy_kwh: float | None = None


class Provider(Protocol):
    """Attributs facultatifs lus par la passerelle (défaut : faux, 0) :

    - `schema_in_prompt` : vrai si le schéma de sortie compte comme tokens d'entrée (envoi par
      outil). Faux quand il part dans `format` (Ollama : grammaire, hors prompt).
    - `schema_prompt_overhead` : tokens fixes ajoutés au prompt par cet envoi, en plus du schéma.
    - `cache_options(request)` : options natives hors `LLMRequest` (Ollama : profil, `num_ctx`),
      reprises dans la clé de cache.
    """

    def complete(
        self,
        request: LLMRequest,
        *,
        timeout_s: float,
        output_schema: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Lève `ProviderError(retryable=...)` en cas d'échec du fournisseur.

        `output_schema` : schéma JSON de la sortie structurée, `None` pour du texte libre.
        """
        ...
