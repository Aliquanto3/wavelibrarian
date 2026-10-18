"""Résolution d'une Expérience : défauts, profil, `ModelRef`, chemins, empreinte (AD-12)."""

import hashlib
import re
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from wavelibrarian import registry
from wavelibrarian.config.catalog import ModelCatalog, load_catalog
from wavelibrarian.config.defaults import load_costs, load_profile
from wavelibrarian.config.experiment import (
    Configuration,
    Experiment,
    ResolvedConfiguration,
    ResolvedExperiment,
)
from wavelibrarian.config.schemas import ProfileSettings, config_error, valider
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import canonical_json
from wavelibrarian.core.types import ModelRefMeta
from wavelibrarian.ports.components import KINDS, ComponentSpec

# Champ de `Params` -> `kind`, quand le nom du champ n'est pas déjà un `kind`.
_ALIAS_KIND = {"store": "vector_store", "lexical": "lexical_index", "graph": "graph_store"}


@dataclass
class Collecte:
    """État d'un parcours : profil et Catalogue (None = validation seule), relevés.

    `erreurs` non None : mode agrégation (story 1.6), les `ConfigError` y sont ajoutées et le
    parcours continue ; None : la première erreur est levée.
    """

    profile: ProfileSettings | None = None
    catalog: ModelCatalog | None = None
    models: list[str] = field(default_factory=list)
    producers: list[str] = field(default_factory=list)
    erreurs: list[ConfigError] | None = None
    chemins_modeles: dict[str, str] = field(default_factory=dict)  # modèle -> 1er chemin
    composants: list[tuple[str, str, str]] = field(default_factory=list)  # (kind, nom, chemin)
    juges_explicites: list[tuple[str, str]] = field(default_factory=list)  # (chemin, modèle)
    embedders: list[tuple[str, str]] = field(default_factory=list)  # (chemin, modèle)
    pile: list[str] = field(default_factory=list)  # kinds des Composants en cours de parcours
    architecture: type | None = None
    chemin: str = ""  # `configurations[i]`
    config_id: str = ""

    def signaler(self, erreur: ConfigError) -> None:
        """Lève `erreur`, ou la note en mode agrégation."""
        if self.erreurs is None:
            raise erreur
        self.erreurs.append(erreur)


def _classe(kind: str, name: str, chemin: str) -> type:
    try:
        return registry.get(kind, name)
    except ConfigError as exc:
        raise ConfigError(chemin, exc.message) from exc


def _annotation_contient_composant(annotation: Any) -> bool:
    if annotation is ComponentSpec:
        return True
    return any(
        _annotation_contient_composant(a)
        for a in typing.get_args(annotation)
        if a is not types.NoneType
    )


def _kind_du_champ(nom: str, champ: FieldInfo) -> str | None:
    extra = champ.json_schema_extra
    kind = extra.get("kind") if isinstance(extra, dict) else None
    if isinstance(kind, str):
        return kind  # déclaration explicite : `Field(json_schema_extra={"kind": ...})`
    if nom in KINDS:
        return nom
    return _ALIAS_KIND.get(nom)


def _role_default(profile: ProfileSettings, role: str, chemin: str) -> str:
    m = re.fullmatch(r"(\w+)(?:\[(\d+)\])?", role)
    if m is None or not hasattr(profile.defaults, m[1]):
        raise ConfigError(chemin, f"`role_default` inconnu du profil : {role!r}")
    valeur: Any = getattr(profile.defaults, m[1])
    if m[2] is not None:
        if not isinstance(valeur, tuple) or int(m[2]) >= len(valeur):  # pyright: ignore[reportUnknownArgumentType]
            raise ConfigError(chemin, f"`role_default` hors de la liste du profil : {role!r}")
        valeur = valeur[int(m[2])]
    if not isinstance(valeur, str):
        raise ConfigError(chemin, f"`role_default` ne désigne pas un modèle : {role!r}")
    return valeur


def _noter(liste: list[str], valeur: str) -> None:
    if valeur not in liste:
        liste.append(valeur)


def _noter_modele(col: Collecte, valeur: str, chemin: str, producteur: bool) -> None:
    _noter(col.models, valeur)
    col.chemins_modeles.setdefault(valeur, chemin)
    if producteur:
        _noter(col.producers, valeur)
    if "judge" in col.pile:
        col.juges_explicites.append((chemin, valeur))
    if "embedder" in col.pile:
        col.embedders.append((chemin, valeur))


def _embedder_par_defaut(col: Collecte, chemin: str) -> ComponentSpec:
    assert col.profile is not None and col.catalog is not None
    modele = col.profile.defaults.embedder
    nom = "fake" if col.catalog.get(modele).provider == "fake" else "sentence_transformers"
    cls = _classe("embedder", nom, f"{chemin}.name")
    params: dict[str, Any] = {"model": modele} if "model" in cls.Params.model_fields else {}  # pyright: ignore[reportAttributeAccessIssue]
    return ComponentSpec(name=nom, params=params)


def resoudre_composant(
    kind: str, spec: ComponentSpec, chemin: str, col: Collecte
) -> dict[str, Any]:
    """Valide et résout un Composant ; renvoie `{"name": ..., "params": {...}}` complet."""
    try:
        cls = _classe(kind, spec.name, f"{chemin}.name")
    except ConfigError as exc:
        col.signaler(exc)
        return {"name": spec.name, "params": dict(spec.params)}
    col.composants.append((kind, spec.name, chemin))
    col.pile.append(kind)
    try:
        params = resoudre_params(cls.Params, spec.params, f"{chemin}.params", col)  # pyright: ignore[reportAttributeAccessIssue]
    finally:
        col.pile.pop()
    return {"name": spec.name, "params": params}


def resoudre_params(
    modele: type[BaseModel], brut: dict[str, Any], chemin: str, col: Collecte
) -> dict[str, Any]:
    """Valide `brut` contre `modele` (clés inconnues refusées) puis complète les défauts."""
    if col.erreurs is None:
        inst = valider(modele, brut, prefixe=chemin)
    else:
        inst = _valider_en_agregeant(modele, brut, chemin, col.erreurs)
        if inst is None:
            return dict(brut)
    res = inst.model_dump(mode="python")
    for nom, champ in modele.model_fields.items():
        chem = f"{chemin}.{nom}"
        try:
            _resoudre_champ(nom, champ, getattr(inst, nom), chem, res, col)
        except ConfigError as exc:
            col.signaler(exc)
    return res


def _valider_en_agregeant(
    modele: type[BaseModel], brut: dict[str, Any], chemin: str, erreurs: list[ConfigError]
) -> BaseModel | None:
    """Note toutes les erreurs de `brut`, puis revalide sans les clés fautives.

    Le parcours des Composants et modèles imbriqués continue ainsi malgré une clé inconnue ou
    invalide ; None si `brut` reste invalide sans ces clés (champ requis manquant, racine).
    """
    try:
        return modele.model_validate(brut)
    except ValidationError as exc:
        details = exc.errors()
    erreurs.extend(config_error(err, prefixe=chemin) for err in details)
    fautives = {err["loc"][0] for err in details if err["loc"]}
    if not fautives:
        return None
    try:
        return modele.model_validate({k: v for k, v in brut.items() if k not in fautives})
    except ValidationError:
        return None


def _resoudre_champ(
    nom: str, champ: FieldInfo, valeur: Any, chem: str, res: dict[str, Any], col: Collecte
) -> None:
    ref = next((m for m in champ.metadata if isinstance(m, ModelRefMeta)), None)
    if ref is not None:
        if valeur is None and col.profile is not None:
            valeur = _role_default(col.profile, ref.role_default, chem)
            res[nom] = valeur
        if valeur is not None:
            _noter_modele(col, valeur, chem, ref.answer_producer)
    elif _annotation_contient_composant(champ.annotation):
        kind = _kind_du_champ(nom, champ)
        if kind is None:
            raise ConfigError(
                chem, 'kind du Composant indéterminé (`Field(json_schema_extra={"kind": ...})`)'
            )
        if valeur is None:
            if kind == "embedder" and col.profile is not None:
                res[nom] = resoudre_composant(kind, _embedder_par_defaut(col, chem), chem, col)
        elif isinstance(valeur, ComponentSpec):
            res[nom] = resoudre_composant(kind, valeur, chem, col)
        else:  # tuple de ComponentSpec
            res[nom] = [
                resoudre_composant(kind, s, f"{chem}[{i}]", col) for i, s in enumerate(valeur)
            ]


def verifier_configuration(conf: Configuration, chemin: str) -> None:
    """Validation stricte des `params` d'une Configuration, sans profil (utilisée au chargement)."""
    col = Collecte()
    cls = _classe("architecture", conf.architecture, f"{chemin}.architecture")
    resoudre_params(cls.Params, conf.params, f"{chemin}.params", col)  # pyright: ignore[reportAttributeAccessIssue]
    if conf.parser.name != "auto":
        resoudre_composant("parser", conf.parser, f"{chemin}.parser", col)


def _chemin_absolu(base: Path, valeur: str | None) -> str | None:
    if valeur is None:
        return None
    return (base / valeur).resolve().as_posix()


def resolve_experiment(
    experience: Experiment,
    source: Path,
    wl_home: Path | None = None,
    *,
    erreurs: list[ConfigError] | None = None,
    releves: list[Collecte] | None = None,
) -> ResolvedExperiment:
    """Résout `experience` (lue dans `source`) : l'Expérience telle qu'elle sera exécutée.

    Précédence (AD-12) : défauts du code, puis profil, puis Expérience. Les chemins relatifs
    sont pris par rapport au fichier de l'Expérience.

    `erreurs` (mode agrégation de `config/validate.py`) : les `ConfigError` y sont rassemblées
    au lieu d'être levées, et une Configuration à l'Architecture inconnue est omise du résultat.
    `releves` reçoit alors le relevé (modèles, Composants) de chaque Configuration résolue.
    """
    registry.discover()
    base = source.resolve().parent
    profil = load_profile(experience.profile)
    chemin_catalogue = _chemin_absolu(base, experience.catalog)
    catalogue = load_catalog(Path(chemin_catalogue) if chemin_catalogue else None)
    chemin_couts = _chemin_absolu(base, experience.costs)
    couts = load_costs(wl_home, Path(chemin_couts) if chemin_couts else None)

    configurations: list[ResolvedConfiguration] = []
    for i, conf in enumerate(experience.configurations):
        chemin = f"configurations[{i}]"
        col = Collecte(
            profile=profil, catalog=catalogue, erreurs=erreurs, chemin=chemin, config_id=conf.id
        )
        try:
            cls = _classe("architecture", conf.architecture, f"{chemin}.architecture")
        except ConfigError as exc:
            col.signaler(exc)
            continue
        col.architecture = cls
        col.pile.append("architecture")
        params = resoudre_params(cls.Params, conf.params, f"{chemin}.params", col)  # pyright: ignore[reportAttributeAccessIssue]
        col.pile.pop()
        parser = conf.parser
        if parser.name != "auto":
            parser = ComponentSpec.model_validate(
                resoudre_composant("parser", parser, f"{chemin}.parser", col)
            )
        if releves is not None:
            releves.append(col)
        configurations.append(
            ResolvedConfiguration(
                id=conf.id,
                architecture=conf.architecture,
                parser=parser,
                reuse_index=conf.reuse_index,
                params=params,
                models=tuple(col.models),
                answer_producers=tuple(col.producers),
            )
        )

    juges = experience.judges.model_copy(
        update={
            "pool": profil.defaults.judge_pool
            if experience.judges.pool is None
            else experience.judges.pool,
            "panel_size": profil.defaults.panel_size
            if experience.judges.panel_size is None
            else experience.judges.panel_size,
            "excluded_from": _chemin_absolu(base, experience.judges.excluded_from),
        }
    )
    return ResolvedExperiment(
        experiment_id=experience.experiment_id,
        seed=experience.seed,
        profile=experience.profile,
        profile_settings=profil,
        corpus=_chemin_absolu(base, experience.corpus) or "",
        questions=_chemin_absolu(base, experience.questions) or "",
        split=experience.split,
        tier=experience.tier,
        scenario=_chemin_absolu(base, experience.scenario),
        conditions=experience.conditions,
        catalog=chemin_catalogue,
        catalog_date=catalogue.catalog_date,
        costs=couts,
        models_frozen_at=experience.models_frozen_at or catalogue.catalog_date,
        max_questions=experience.max_questions,
        max_error_rate=experience.max_error_rate,
        budget=experience.budget,
        judges=juges,
        stats=experience.stats,
        retries=experience.retries,
        configurations=tuple(configurations),
    )


def resolved_dict(resolue: ResolvedExperiment) -> dict[str, Any]:
    """Forme sérialisable (JSON) de l'Expérience résolue : `Decimal` et dates en chaînes."""
    return resolue.model_dump(mode="json")


def to_yaml(resolue: ResolvedExperiment) -> str:
    """Contenu de `experiment.resolved.yaml`."""
    return yaml.safe_dump(resolved_dict(resolue), sort_keys=False, allow_unicode=True)


def fingerprint(resolue: ResolvedExperiment) -> str:
    """Empreinte sha256 (64 hex) du JSON canonique : insensible à l'ordre des clés."""
    return hashlib.sha256(canonical_json(resolved_dict(resolue)).encode("utf-8")).hexdigest()


def write_resolved(resolue: ResolvedExperiment, dossier: Path) -> str:
    """Écrit les deux fichiers de l'Expérience résolue dans `dossier` ; renvoie l'empreinte.

    L'appelant (runner) remplace d'abord chaque `parser: auto` par les noms concrets lus
    sur le Corpus (contracts.md §4.4) : ce module ne charge pas le Corpus.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    empreinte = fingerprint(resolue)
    (dossier / "experiment.resolved.yaml").write_text(to_yaml(resolue), encoding="utf-8")
    (dossier / "experiment.sha256").write_text(empreinte + "\n", encoding="utf-8")
    return empreinte
