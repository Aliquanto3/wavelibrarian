"""Architecture `cag` : tout le Corpus préchargé dans le cache de prompt (FR-22).

Même prompt que `long_context` (un bloc étiqueté par Ancrage dans le system, `cache_system`
forcé à vrai, Réponse `cited`, `check` de fenêtre et de palier). La différence : `load` émet un
appel de préchargement au Poste courant (`indexing` sous le runner, AD-8), de sorte que l'index
construit et l'index servi par le cache préchargent à l'identique et que la première Question
lit déjà le cache.
"""

from pathlib import Path
from typing import Any

from wavelibrarian.architectures.long_context import LongContext
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.ports.architecture import ArchCapabilities
from wavelibrarian.registry import register


@register("architecture", "cag")
class Cag(LongContext):
    """CAG : `LongContext` plus préchargement du system dans le cache de prompt par `load`."""

    name = "cag"
    capabilities = ArchCapabilities(
        retrieval_method="cited", full_corpus_in_prompt=True, requires_prompt_cache=True
    )

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        if not callable(getattr(self.generator, "preload", None)):
            raise ConfigError(
                "architecture.generator",
                "`cag` exige un Generator capable de précharger le cache de prompt (`llm`)",
            )

    def load(self, directory: Path) -> None:
        super().load(directory)
        contexte = self._contexte
        if contexte is not None and contexte.blocks:
            self.generator.preload(contexte)  # type: ignore[attr-defined]
