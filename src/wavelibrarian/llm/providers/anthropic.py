"""Provider Anthropic (AD-3, AD-17, AD-19) : traduit un `LLMRequest` en appel du SDK.

`cache_control` sur le system (`cache_system`) et sur les messages `cache=True`. Sortie
structurée par un outil imposé (`tool_choice`) dont l'`input_schema` est le schéma JSON : le texte
renvoyé est l'entrée de l'outil sérialisée. Le SDK ne réessaie pas (`max_retries=0`) : les essais
appartiennent à la passerelle. L'énergie est lue sur `response.impacts` (EcoLogits, si
`EcoLogits.init` a patché le SDK) ; absente, `ProviderResponse.energy_kwh` reste `None`.
"""

import json
from typing import Any

import anthropic
import httpx2
from pydantic import SecretStr

from wavelibrarian.core.errors import ProviderError
from wavelibrarian.core.types import Usage
from wavelibrarian.llm.providers.base import ProviderResponse
from wavelibrarian.llm.providers.secrets import load_secret
from wavelibrarian.ports.gateway import LLMRequest

CLE_ENV = "ANTHROPIC_API_KEY"
OUTIL_SORTIE = "emit_output"
_CACHE = {"type": "ephemeral"}


def _energie_kwh(response: object) -> float | None:
    """`response.impacts.energy.value` (kWh), milieu de la fourchette ; `None` si absent."""
    valeur = getattr(getattr(getattr(response, "impacts", None), "energy", None), "value", None)
    if valeur is None:
        return None
    if hasattr(valeur, "min") and hasattr(valeur, "max"):
        return (float(valeur.min) + float(valeur.max)) / 2
    return float(valeur)


def _traduire(exc: anthropic.AnthropicError) -> ProviderError:
    """429, 5xx (529 compris) et réseau : réessayables ; 4xx : non. Jamais d'en-tête ni de clé."""
    if isinstance(exc, anthropic.APITimeoutError):
        # Parti sans réponse, peut-être facturé : réglé à l'estimation, jamais relancé (AD-9).
        return ProviderError("Anthropic : délai dépassé", retryable=False, sent=True)
    if isinstance(exc, anthropic.APIConnectionError):
        return ProviderError("Anthropic : connexion impossible", retryable=True)
    if isinstance(exc, anthropic.APIStatusError):
        code = exc.status_code
        detail = str(exc.message)[:200]
        return ProviderError(
            f"Anthropic HTTP {code} : {detail}", retryable=code in (408, 409, 429) or code >= 500
        )
    return ProviderError(f"Anthropic : {type(exc).__name__}", retryable=False)


class AnthropicProvider:
    # Le schéma part dans un outil : il est compté en entrée, plus la consigne d'outil imposé.
    schema_in_prompt = True
    schema_prompt_overhead = 400

    def __init__(
        self,
        api_key: SecretStr | None = None,
        *,
        client: anthropic.Anthropic | None = None,
        http_client: httpx2.Client | None = None,
        base_url: str | None = None,
    ) -> None:
        """`client` (ou `http_client`, `httpx2.Client` sur un `MockTransport`) sert aux tests.

        Sans `api_key`, la clé est cherchée au premier appel (`.env` puis environnement).
        """
        self._key = api_key
        self._client = client
        self._http_client = http_client
        self._base_url = base_url

    def _sdk(self) -> anthropic.Anthropic:
        if self._client is None:
            cle = self._key or load_secret(CLE_ENV)
            if cle is None:
                raise ProviderError(f"clé {CLE_ENV} absente (.env ou environnement)")
            self._client = anthropic.Anthropic(
                api_key=cle.get_secret_value(),
                http_client=self._http_client,
                base_url=self._base_url,
                max_retries=0,
            )
        return self._client

    @staticmethod
    def native_request(request: LLMRequest, output_schema: dict[str, Any] | None) -> dict[str, Any]:
        """Corps natif de `messages.create` (exposé pour les tests)."""
        corps: dict[str, Any] = {
            "model": request.model_id,
            "max_tokens": request.max_tokens,
            "messages": [
                {
                    "role": m.role,
                    "content": [{"type": "text", "text": m.content, "cache_control": _CACHE}]
                    if m.cache
                    else m.content,
                }
                for m in request.messages
            ],
        }
        if request.cache_system and request.system:  # bloc `text` vide : refusé par l'API
            corps["system"] = [{"type": "text", "text": request.system, "cache_control": _CACHE}]
        elif request.system:
            corps["system"] = request.system
        if output_schema is not None:
            corps["tools"] = [
                {
                    "name": OUTIL_SORTIE,
                    "description": "Renvoie la réponse structurée.",
                    "input_schema": output_schema,
                }
            ]
            corps["tool_choice"] = {"type": "tool", "name": OUTIL_SORTIE}
        return corps

    def complete(
        self,
        request: LLMRequest,
        *,
        timeout_s: float,
        output_schema: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        corps = self.native_request(request, output_schema)
        try:
            # `temperature` n'est plus un paramètre typé du SDK 1.15 : corps additionnel.
            reponse = self._sdk().messages.create(
                timeout=timeout_s, extra_body={"temperature": request.temperature}, **corps
            )
        except anthropic.AnthropicError as exc:
            raise _traduire(exc) from None
        if output_schema is not None:
            sortie = [b.input for b in reponse.content if b.type == "tool_use"]
            if not sortie:
                raise ProviderError("Anthropic : aucune sortie d'outil dans la réponse")
            texte = json.dumps(sortie[0], ensure_ascii=False)
        else:
            texte = "".join(b.text for b in reponse.content if b.type == "text")
        u = reponse.usage
        usage = Usage(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", None) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", None) or 0,
        )
        return ProviderResponse(text=texte, usage=usage, energy_kwh=_energie_kwh(reponse))
