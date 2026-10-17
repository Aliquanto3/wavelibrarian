"""Préflight (AD-11) : vérifie les dépendances d'une Exécution avant toute dépense.

Ollama (joignable, modèle présent dans `/api/tags`), clé Anthropic, embedder dans le cache
local. Les modèles `fake-*` ne demandent rien. Seul `/api/tags` est lu, aucun modèle n'est chargé.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wavelibrarian.config.catalog import ModelCatalog
from wavelibrarian.config.schemas import ProfileSettings
from wavelibrarian.core.errors import ProviderError
from wavelibrarian.llm.local_models import embedder_installe
from wavelibrarian.llm.providers.ollama import list_models
from wavelibrarian.llm.providers.secrets import load_secret

CLE_ANTHROPIC = "ANTHROPIC_API_KEY"


@dataclass(frozen=True)
class PreflightResult:
    """Échecs du préflight, un message en français par dépendance manquante."""

    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def _present(modele: str, tags: set[str]) -> bool:
    return modele in tags or (":" not in modele and f"{modele}:latest" in tags)


def preflight(
    models: Iterable[str],
    catalog: ModelCatalog,
    profile: ProfileSettings,
    *,
    http_client: Any = None,
    env_file: Path | str | None = None,
) -> PreflightResult:
    """Contrôle les `models` (identifiants du Catalogue).

    `http_client` : `httpx.Client` à transport factice en test (httpx reste dans les providers).
    """
    erreurs: list[str] = []
    ollama: list[str] = []
    for modele in sorted(set(models)):
        entree = catalog.get(modele)
        if entree.provider == "fake":
            continue
        if entree.provider == "ollama":
            ollama.append(modele)
        elif entree.provider == "anthropic":
            if load_secret(CLE_ANTHROPIC, env_file) is None:
                erreurs.append(f"clé {CLE_ANTHROPIC} manquante (modèle {modele})")
        elif entree.provider == "sentence_transformers" and (
            not entree.hf_repo or not embedder_installe(entree.hf_repo)
        ):
            erreurs.append(
                f"embedder {modele} absent du cache local (`wl installer --profil "
                f"{profile.profile}`)"
            )
    if ollama:
        url = profile.ollama.base_url
        try:
            tags = list_models(url, http_client=http_client)
        except ProviderError:
            erreurs.append(f"Ollama injoignable à {url} (modèles attendus : {', '.join(ollama)})")
        else:
            erreurs.extend(
                f"modèle Ollama {m} absent de {url}/api/tags (`ollama pull {m}`)"
                for m in ollama
                if not _present(m, tags)
            )
    return PreflightResult(tuple(erreurs))
