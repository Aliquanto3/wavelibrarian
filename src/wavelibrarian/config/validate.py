"""Validation statique d'une Expérience : tous les refus en un seul `ValidationFailed` (AD-13).

Aucun accès réseau ni appel de modèle. Les contrôles qui dépendent du Corpus (fenêtre, palier
tarifaire) relèvent de `Architecture.check(profile)`, après profilage.
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from wavelibrarian import registry
from wavelibrarian.config.catalog import ModelCatalog, load_catalog
from wavelibrarian.config.experiment import Experiment, ResolvedExperiment
from wavelibrarian.config.load import load_experiment
from wavelibrarian.config.panel import excluded_judges, form_panel
from wavelibrarian.config.resolve import Collecte, resolve_experiment
from wavelibrarian.core.errors import ConfigError, ValidationFailed
from wavelibrarian.ports.architecture import ArchCapabilities
from wavelibrarian.ports.components import StoreCapabilities

_CLE_INDEX = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class ValidationResult:
    """Expérience résolue et validée, avec le Panel de chaque Configuration."""

    resolved: ResolvedExperiment
    catalog: ModelCatalog
    panels: dict[str, tuple[str, ...]]  # config_id -> Juges, dans l'ordre du réservoir


def _wl_home(wl_home: Path | None) -> Path:
    return wl_home or Path(os.environ.get("WL_HOME") or ".wl")


def _verifier_modeles(col: Collecte, catalog: ModelCatalog, erreurs: list[ConfigError]) -> set[str]:
    """Signale les modèles absents du Catalogue ; renvoie les modèles connus."""
    connus: set[str] = set()
    for modele in col.models:
        try:
            catalog.get(modele)
            connus.add(modele)
        except ConfigError as exc:
            chemin = col.chemins_modeles.get(modele, col.chemin)
            erreurs.append(ConfigError(chemin, exc.message))
    return connus


def _verifier_capacites(
    col: Collecte, catalog: ModelCatalog, connus: set[str], erreurs: list[ConfigError]
) -> None:
    caps: ArchCapabilities = getattr(col.architecture, "capabilities", None) or ArchCapabilities()
    nom_arch = getattr(col.architecture, "__name__", "")
    if caps.requires_hybrid_store:
        for kind, nom, chemin in col.composants:
            if kind != "vector_store":
                continue
            store: StoreCapabilities = (
                getattr(registry.get(kind, nom), "capabilities", None) or StoreCapabilities()
            )
            if not store.hybrid:
                erreurs.append(
                    ConfigError(
                        chemin,
                        f"l'Architecture {nom_arch} exige un store hybride, mais le "
                        f"vector_store « {nom} » déclare hybrid: false",
                    )
                )
    if caps.requires_prompt_cache:
        for modele in col.producers:
            if modele in connus and not catalog.get(modele).prompt_cache:
                erreurs.append(
                    ConfigError(
                        col.chemins_modeles.get(modele, col.chemin),
                        f"l'Architecture {nom_arch} exige le cache de prompt, mais le modèle "
                        f"{modele!r} déclare prompt_cache: false au Catalogue",
                    )
                )


def _verifier_index_reutilise(
    col: Collecte, cle: str, wl_home: Path, catalog: ModelCatalog, erreurs: list[ConfigError]
) -> None:
    chemin = f"{col.chemin}.reuse_index"
    if not _CLE_INDEX.fullmatch(cle):
        erreurs.append(ConfigError(chemin, f"clé d'index invalide : {cle!r}"))
        return
    manifeste = wl_home / "index" / cle / "manifest.json"
    try:
        donnees = json.loads(manifeste.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        erreurs.append(
            ConfigError(chemin, f"index à réutiliser illisible : {manifeste.as_posix()} ({exc})")
        )
        return
    dim_index = donnees.get("embedder_dim") if isinstance(donnees, dict) else None
    if dim_index is None:
        return  # index sans embedder : rien à comparer
    for chem_embedder, modele in col.embedders:
        try:
            dim = catalog.get(modele).dim
        except ConfigError:
            continue  # déjà signalé : modèle absent du Catalogue
        if dim is not None and dim != dim_index:
            erreurs.append(
                ConfigError(
                    chemin,
                    f"dimension incompatible : l'index {cle} a embedder_dim {dim_index}, "
                    f"l'embedder {modele!r} ({chem_embedder}) produit des vecteurs de dimension "
                    f"{dim}",
                )
            )


def _verifier_juges(
    col: Collecte,
    resolved: ResolvedExperiment,
    catalog: ModelCatalog,
    connus: set[str],
    excluded: frozenset[str],
    pool_connu: bool,
    erreurs: list[ConfigError],
    panels: dict[str, tuple[str, ...]],
) -> None:
    producteurs = [m for m in col.producers if m in connus]
    familles = {catalog.get(m).family: m for m in reversed(producteurs)}
    for chemin, modele in col.juges_explicites:
        if modele in connus and (famille := catalog.get(modele).family) in familles:
            erreurs.append(
                ConfigError(
                    chemin,
                    f"le Juge {modele!r} est de la Famille « {famille} » du Generator "
                    f"{familles[famille]!r} (FR-37)",
                )
            )
    if not pool_connu:
        return
    j = resolved.judges
    try:
        panels[col.config_id] = form_panel(
            j.pool or (), j.panel_size or 0, producteurs, catalog, excluded
        )
    except ConfigError as exc:
        erreurs.append(ConfigError(exc.path, f"Configuration {col.config_id!r} : {exc.message}"))


def validate_experiment(
    experience: Experiment, source: Path, wl_home: Path | None = None
) -> ValidationResult:
    """Valide `experience` sans réseau ; lève un seul `ValidationFailed` regroupant les refus.

    Contrôles : noms au registre, paramètres, modèles du Catalogue, `requires_hybrid_store`
    contre `StoreCapabilities.hybrid`, `requires_prompt_cache` contre `prompt_cache`, dimension
    d'un index réutilisé, Juges explicites et Panel admissible (AD-13, AD-14). Les prix des
    modèles d'API sont exigés au chargement du Catalogue (story 1.4).
    """
    erreurs: list[ConfigError] = []
    releves: list[Collecte] = []
    home = _wl_home(wl_home)
    try:
        resolved = resolve_experiment(experience, source, home, erreurs=erreurs, releves=releves)
        catalog = load_catalog(Path(resolved.catalog) if resolved.catalog else None)
    except ConfigError as exc:  # profil, Catalogue ou coûts illisibles : rien d'autre à vérifier
        raise ValidationFailed([*erreurs, exc]) from exc

    pool = resolved.judges.pool or ()
    pool_connu = True
    for i, modele in enumerate(pool):
        try:
            catalog.get(modele)
        except ConfigError as exc:
            pool_connu = False
            erreurs.append(ConfigError(f"judges.pool[{i}]", exc.message))
    excluded: frozenset[str] = frozenset()
    if resolved.judges.excluded_from:
        try:
            excluded = excluded_judges(Path(resolved.judges.excluded_from))
        except ConfigError as exc:
            erreurs.append(exc)

    reuse = {c.id: c.reuse_index for c in experience.configurations}
    panels: dict[str, tuple[str, ...]] = {}
    for col in releves:
        connus = _verifier_modeles(col, catalog, erreurs)
        _verifier_capacites(col, catalog, connus, erreurs)
        if (cle := reuse.get(col.config_id)) is not None:
            _verifier_index_reutilise(col, cle, home, catalog, erreurs)
        _verifier_juges(col, resolved, catalog, connus, excluded, pool_connu, erreurs, panels)

    uniques = list({(e.path, e.message): e for e in erreurs}.values())
    if uniques:
        raise ValidationFailed(uniques)
    return ValidationResult(resolved=resolved, catalog=catalog, panels=panels)


def validate_file(chemin: Path, wl_home: Path | None = None) -> ValidationResult:
    """Charge puis valide `chemin` ; toute erreur (schéma compris) devient `ValidationFailed`."""
    try:
        experience = load_experiment(chemin, verifier_params=False)
    except ConfigError as exc:
        raise ValidationFailed([exc]) from exc
    return validate_experiment(experience, chemin, wl_home)
