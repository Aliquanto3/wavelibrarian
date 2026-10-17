"""Cache d'index adressé par contenu (AD-10, contracts.md §2.1 et §5).

L'Architecture écrit dans `index/.tmp-<index_key>/` ; le runner ajoute `manifest.json` puis
renomme par `os.replace` vers `index/<index_key>/` : un dossier final est complet ou absent.
Après `index` (ou sur un cache présent), le runner construit une instance neuve et appelle
`load` : les chemins « cache présent » et « cache absent » sont identiques.
"""

import json
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from wavelibrarian.core.ids import canonical_json, sha16
from wavelibrarian.core.types import CostPost, ParsedCorpus, Usage
from wavelibrarian.ports.architecture import ArchitectureBase

if TYPE_CHECKING:
    from wavelibrarian.runner.context import Context


def index_key(corpus_fingerprint: str, architecture: ArchitectureBase) -> str:
    """`sha16(canonical_json({corpus_fingerprint, architecture, index_key()}))` (AD-10)."""
    return sha16(
        canonical_json(
            {
                "corpus_fingerprint": corpus_fingerprint,
                "architecture": architecture.name,
                "index_key": architecture.index_key(),
            }
        )
    )


def _embedder_dim(architecture: ArchitectureBase) -> int | None:
    dim = getattr(getattr(architecture, "embedder", None), "dim", None)
    return dim if isinstance(dim, int) else None


def _trace_index(ctx: "Context", *, hit: bool, latency_s: float, key: str) -> None:
    ctx.tracer.record(
        "index",
        "local",
        model_id=None,
        provider=None,
        usage=Usage(),
        cost=Decimal(0),
        cost_uncached=Decimal(0),
        currency="",
        latency_s=latency_s,
        from_cache=False,
        extra={"wl.index_cache_hit": hit, "wl.index_key": key},
    )


class IndexCache:
    """Dossier `index/` d'un `WL_HOME`."""

    def __init__(self, wl_home: Path) -> None:
        self.root = wl_home / "index"

    def path(self, key: str) -> Path:
        return self.root / key

    def has(self, key: str) -> bool:
        return (self.path(key) / "manifest.json").is_file()

    def build(
        self,
        ctx: "Context",
        factory: Callable[[], ArchitectureBase],
        corpus: ParsedCorpus,
        *,
        post: CostPost = "indexing",
    ) -> tuple[ArchitectureBase, str]:
        """Rend `(instance chargée, index_key)` ; construit l'index s'il manque.

        `factory` crée une instance neuve de l'Architecture (via `ctx.build`). Les appels faits
        pendant `index` sont comptés au Poste `post`. Une exception dans `index` laisse le dossier
        final absent et supprime le dossier temporaire.
        """
        import time

        arch = factory()
        key = index_key(corpus.fingerprint, arch)
        final = self.path(key)
        debut = time.perf_counter()
        hit = self.has(key)
        if not hit:
            self._construire(ctx, arch, corpus, key, post)
        neuve = factory()
        neuve.load(final)
        with ctx.scope(post=post):
            _trace_index(ctx, hit=hit, latency_s=time.perf_counter() - debut, key=key)
        return neuve, key

    def _construire(
        self, ctx: "Context", arch: ArchitectureBase, corpus: ParsedCorpus, key: str, post: CostPost
    ) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".tmp-{key}"
        if tmp.exists():  # reste d'une construction interrompue
            shutil.rmtree(tmp)
        tmp.mkdir()
        try:
            with ctx.scope(post=post):
                arch.index(corpus, tmp)
            manifest: dict[str, Any] = {
                "index_key": key,
                "architecture": arch.name,
                "corpus_fingerprint": corpus.fingerprint,
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            dim = _embedder_dim(arch)
            if dim is not None:
                manifest["embedder_dim"] = dim
            (tmp / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(tmp, self.path(key))
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
