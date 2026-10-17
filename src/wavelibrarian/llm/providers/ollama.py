"""Provider Ollama (AD-3) : `POST /api/chat` par httpx, options du profil, `format` JSON.

Ne touche que `/api/chat`. `num_gpu` (profil `cpu` : 0), `seed`, `temperature` et `num_predict`
partent dans `options`, `keep_alive` à la racine du corps. Le schéma de sortie part dans `format`
(grammaire côté serveur, hors prompt). Un délai dépassé après envoi n'est pas réessayé (un modèle
trop lent ne ira pas plus vite) mais signalé `sent` : la passerelle règle à l'estimation.

`num_ctx` : celui du profil (`ollama.options`), sinon le `context_window` du Catalogue, pour que
le défaut du serveur (quelques milliers de tokens) ne tronque pas un prompt sans prévenir. Une
réponse qui remplit la fenêtre (`prompt_eval_count + eval_count >= num_ctx`) est journalisée en
avertissement : le prompt a probablement été tronqué.
"""

import logging
from collections.abc import Mapping
from typing import Any

import httpx

from wavelibrarian.config.schemas import OllamaSettings
from wavelibrarian.core.errors import ProviderError
from wavelibrarian.core.types import Usage
from wavelibrarian.llm.providers.base import ProviderResponse
from wavelibrarian.ports.gateway import LLMRequest

_log = logging.getLogger(__name__)


class OllamaProvider:
    schema_in_prompt = False  # `format` : grammaire, le schéma n'entre pas dans le prompt

    def __init__(
        self,
        settings: OllamaSettings,
        *,
        context_windows: Mapping[str, int] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        """`settings` : section `ollama` du profil ; `context_windows` : `model_id` ->
        `context_window` du Catalogue ; `http_client` (transport factice) en test."""
        self._settings = settings
        self._fenetres = dict(context_windows or {})
        self._http = http_client or httpx.Client()

    def native_request(
        self, request: LLMRequest, output_schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            **self._settings.options,
            "temperature": request.temperature,
            "num_predict": request.max_tokens,
        }
        if request.seed is not None:
            options["seed"] = request.seed
        if "num_ctx" not in options and request.model_id in self._fenetres:
            options["num_ctx"] = self._fenetres[request.model_id]
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        if request.system:
            messages.insert(0, {"role": "system", "content": request.system})
        corps: dict[str, Any] = {
            "model": request.model_id,
            "messages": messages,
            "stream": False,
            "keep_alive": self._settings.keep_alive,
            "options": options,
        }
        if output_schema is not None:
            corps["format"] = output_schema
        return corps

    def complete(
        self,
        request: LLMRequest,
        *,
        timeout_s: float,
        output_schema: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        url = self._settings.base_url.rstrip("/") + "/api/chat"
        corps = self.native_request(request, output_schema)
        try:
            reponse = self._http.post(url, json=corps, timeout=timeout_s)
        except httpx.ConnectTimeout:
            raise ProviderError("Ollama : connexion trop lente", retryable=True) from None
        except httpx.TimeoutException:
            raise ProviderError(
                f"Ollama : délai de {timeout_s:g} s dépassé", retryable=False, sent=True
            ) from None
        except httpx.TransportError as exc:
            raise ProviderError(
                f"Ollama injoignable ({type(exc).__name__})", retryable=True
            ) from None
        if reponse.status_code != 200:
            code = reponse.status_code
            raise ProviderError(
                f"Ollama HTTP {code} : {reponse.text[:200]}", retryable=code >= 500 or code == 408
            )
        try:
            donnees = reponse.json()
            texte = str(donnees["message"]["content"])
            usage = Usage(
                input_tokens=int(donnees.get("prompt_eval_count") or 0),
                output_tokens=int(donnees.get("eval_count") or 0),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(f"Ollama : réponse illisible ({type(exc).__name__})") from None
        num_ctx = corps["options"].get("num_ctx")
        if isinstance(num_ctx, int) and usage.input_tokens + usage.output_tokens >= num_ctx:
            _log.warning(
                "Ollama %s : fenêtre de %d tokens remplie (%d en entrée, %d en sortie), "
                "prompt probablement tronqué",
                request.model_id, num_ctx, usage.input_tokens, usage.output_tokens,
            )  # fmt: skip
        return ProviderResponse(text=texte, usage=usage)


def list_models(
    base_url: str, *, http_client: httpx.Client | None = None, timeout_s: float = 3.0
) -> set[str]:
    """Noms des modèles présents dans Ollama (`GET /api/tags`, lecture seule, préflight).

    Lève `ProviderError` si le serveur est injoignable ou répond de travers.
    """
    http = http_client or httpx.Client()
    url = base_url.rstrip("/") + "/api/tags"
    try:
        reponse = http.get(url, timeout=timeout_s)
        reponse.raise_for_status()
        corps = reponse.json()
        return {str(m.get("name") or m.get("model")) for m in corps.get("models", [])}
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise ProviderError(f"Ollama ne répond pas ({type(exc).__name__})") from None
