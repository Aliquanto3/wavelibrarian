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
from wavelibrarian.corpus.ingest import versions_parsers
from wavelibrarian.measure.tracing import temps_propre
from wavelibrarian.ports.architecture import ArchitectureBase, CorpusChange
from wavelibrarian.runner.wiki_fidelity import cle_de_copie, copier_fidelite

if TYPE_CHECKING:
    from wavelibrarian.runner.context import Context


def index_key(corpus_fingerprint: str, architecture: ArchitectureBase) -> str:
    """`sha16(canonical_json({corpus_fingerprint, architecture, index_key(), parser_versions}))`.

    AD-10, plus la `version` de chaque Parser de `ctx.parser` : le `doc_id` hache les octets
    bruts, une nouvelle version d'un Parser ne change donc pas `corpus_fingerprint`. La version
    est ajoutée ici et non dans `index_key()` pour qu'une Architecture qui redéfinit `index_key()`
    ne puisse pas l'omettre. `ConfigError` si le parser est encore `auto`.
    """
    return sha16(
        canonical_json(
            {
                "corpus_fingerprint": corpus_fingerprint,
                "architecture": architecture.name,
                "index_key": architecture.index_key(),
                "parser_versions": versions_parsers(architecture.ctx.parser),
            }
        )
    )


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
        change: CorpusChange | None = None,
        old_dir: Path | None = None,
    ) -> tuple[ArchitectureBase, str]:
        """Rend `(instance chargée, index_key)` ; construit l'index s'il manque.

        `factory` crée une instance neuve de l'Architecture (via `ctx.build`). Les appels faits
        pendant `index` sont comptés au Poste `post`. Une exception dans `index` laisse le dossier
        final absent et supprime le dossier temporaire.

        Mise à jour (story 4.7) : avec `change` et `old_dir` (dossier de l'index de la base, lu
        sans être modifié), un index absent est produit par `update(change, corpus, old_dir,
        tmp_dir)` au lieu de `index` ; un index déjà présent est servi par le cache. Le dossier
        final porte la clé du corpus après mise à jour.
        """
        import time

        arch = factory()
        key = index_key(corpus.fingerprint, arch)
        final = self.path(key)
        debut = time.perf_counter()
        ecoule = ctx.traceur.elapsed_total
        hit = self.has(key)
        if not hit:
            self._construire(ctx, arch, corpus, key, post, change, old_dir)
        neuve = factory()
        with ctx.scope(post=post):  # `load` aussi est imputé à l'indexation (AD-8)
            neuve.load(final)
            # Latence propre au span `index` : celle des spans d'embedding ou d'appels déjà
            # tracés pendant la construction ou le chargement n'est pas comptée deux fois.
            propre = temps_propre(time.perf_counter() - debut, ctx.traceur.elapsed_total - ecoule)
            _trace_index(ctx, hit=hit, latency_s=propre, key=key)
        # Copie générique (story 7.3) : `wiki_fidelity.json` du dossier d'index, s'il existe.
        copier_fidelite(final, ctx.run_dir, cle_de_copie(ctx.config_id, ctx.tier, post))
        return neuve, key

    def _construire(
        self,
        ctx: "Context",
        arch: ArchitectureBase,
        corpus: ParsedCorpus,
        key: str,
        post: CostPost,
        change: CorpusChange | None = None,
        old_dir: Path | None = None,
    ) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".tmp-{key}"
        if tmp.exists():  # reste d'une construction interrompue
            shutil.rmtree(tmp)
        tmp.mkdir()
        try:
            with ctx.scope(post=post):
                if change is not None and old_dir is not None:
                    arch.update(change, corpus, old_dir, tmp)
                else:
                    arch.index(corpus, tmp)
            manifest: dict[str, Any] = {
                "index_key": key,
                "architecture": arch.name,
                "corpus_fingerprint": corpus.fingerprint,
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            dim = arch.embedder_dim()
            if isinstance(dim, int):
                manifest["embedder_dim"] = dim
            (tmp / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(tmp, self.path(key))
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
