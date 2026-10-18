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

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

import httpx

from wavelibrarian.config.schemas import OllamaSettings
from wavelibrarian.core.errors import ProviderError
from wavelibrarian.core.types import Usage
from wavelibrarian.llm.providers.base import ProviderResponse
from wavelibrarian.ports.gateway import LLMRequest

_log = logging.getLogger(__name__)


_FENCE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)
_FENCE_JSON = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_OUVRE, _FERME = "<think>", "</think>"


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Schéma JSON où chaque `$ref` vers `#/$defs/…` est remplacé par sa définition.

    La grammaire d'Ollama (`format`) ne résout pas les `$ref` : un schéma imbriqué (Pydantic en
    génère dès qu'un modèle en contient un autre) contraignait mal ou pas la sortie. Sans
    récursion, `$defs` disparaît. Une définition récursive ne peut pas être dépliée : son `$ref`
    reste, et `$defs` est alors conservé pour que la référence reste résoluble.
    """
    defs: dict[str, Any] = schema.get("$defs", {})
    garde = False

    def resoudre(noeud: Any, pile: tuple[str, ...]) -> Any:
        nonlocal garde
        if isinstance(noeud, list):
            return [resoudre(x, pile) for x in noeud]
        if not isinstance(noeud, dict):
            return noeud
        ref = noeud.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            nom = ref.removeprefix("#/$defs/")
            if nom in defs and nom not in pile:
                reste = {k: v for k, v in noeud.items() if k != "$ref"}
                return {**resoudre(defs[nom], (*pile, nom)), **resoudre(reste, pile)}
            garde = True  # récursive (ou inconnue) : la référence reste
        return {k: resoudre(v, pile) for k, v in noeud.items() if k != "$defs"}

    resolu: dict[str, Any] = resoudre(schema, ())
    if garde and defs:
        resolu["$defs"] = defs
    return resolu


def _sans_think_de_tete(texte: str, *, structure: bool) -> str:
    """Retire un bloc `<think>…</think>` placé en tête (après des blancs), jamais ailleurs.

    Sortie structurée : un `</think>` orphelin (ouverture absorbée par le gabarit du modèle)
    placé avant le premier `{` ou `[` est aussi traité comme la fin d'une réflexion de tête.
    """
    tete = texte.lstrip()
    if tete.startswith(_OUVRE):
        fin = tete.find(_FERME)
        return tete[fin + len(_FERME) :].lstrip() if fin >= 0 else texte
    if structure:
        fin = tete.find(_FERME)
        debuts = [i for i in (tete.find("{"), tete.find("[")) if i >= 0]
        if fin >= 0 and (not debuts or fin < min(debuts)):
            return tete[fin + len(_FERME) :].lstrip()
    return texte


def _est_json(texte: str) -> bool:
    try:
        json.loads(texte)
    except ValueError:
        return False
    return True


def clean_content(texte: str, *, structure: bool = False) -> str:
    """Nettoie la sortie d'un petit modèle local.

    Toujours : retire un bloc `<think>…</think>` de tête. Sortie structurée seulement : retire
    une clôture markdown qui entoure tout le texte, sinon extrait le premier bloc ```json d'un
    texte qui l'entoure de prose (« Voici : ```json … ``` »). Un texte déjà JSON valide n'est
    jamais retouché ; un texte libre garde ses clôtures (une Réponse peut contenir du code).
    """
    texte = _sans_think_de_tete(texte, structure=structure)
    if not structure:
        return texte
    texte = texte.strip()
    if _est_json(texte):
        return texte
    m = _FENCE.match(texte) or _FENCE_JSON.search(texte)
    return m.group(1) if m else texte


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

    def cache_options(self, request: LLMRequest) -> dict[str, Any]:
        """Options envoyées hors des champs de `LLMRequest` (profil, `num_ctx`) : la passerelle
        les fait entrer dans la clé de cache (story 8.7, `repeat_penalty` change la sortie)."""
        options: dict[str, Any] = dict(self._settings.options)
        if "num_ctx" not in options and request.model_id in self._fenetres:
            options["num_ctx"] = self._fenetres[request.model_id]
        return options

    def native_request(
        self, request: LLMRequest, output_schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            **self.cache_options(request),
            "num_predict": request.max_tokens,
        }
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.seed is not None:
            options["seed"] = request.seed
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
        # `think` (Catalogue, story 8.4) : `false` par défaut, car un modèle à raisonnement
        # (qwen3.5) dépenserait `num_predict` en réflexion, hors de `message.content` ; validé en
        # réel sur granite4.2 et minicpm (3e série du 2026-10-18). `None` : champ omis, pour un
        # modèle qui le refuserait (HTTP 400).
        if request.think is not None:
            corps["think"] = request.think
        if output_schema is not None:
            corps["format"] = inline_refs(output_schema)
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
            brut = str(donnees["message"]["content"])
            texte = clean_content(brut, structure=output_schema is not None)
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
        return {str(m.get("name") or m.get("model")) for m in corps.get("models") or []}
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, AttributeError, TypeError) as exc:
        raise ProviderError(f"Ollama ne répond pas ({type(exc).__name__})") from None
    finally:
        if http_client is None:
            http.close()
