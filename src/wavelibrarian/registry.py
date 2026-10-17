"""Registre de Composants et d'Architectures (AD-2)."""

import importlib
import inspect
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic_core import PydanticUndefined

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.ports.components import KINDS

T = TypeVar("T", bound=type)

_REGISTRE: dict[tuple[str, str], type] = {}
_PAQUETS_DECOUVERTS = ("wavelibrarian.components", "wavelibrarian.architectures")
_decouvert = False


@dataclass(frozen=True)
class ParamInfo:
    """Un paramètre d'un Composant : nom, type affiché et défaut."""

    name: str
    type: str
    default: str


@dataclass(frozen=True)
class ComponentInfo:
    """Entrée du registre telle que la liste `list_components`."""

    kind: str
    name: str
    description: str
    params: tuple[ParamInfo, ...]


def _verifier_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ConfigError("kind", f"kind inconnu « {kind} » ; kinds valides : {', '.join(KINDS)}")


def register(kind: str, name: str) -> Callable[[T], T]:
    """Décorateur qui enregistre une classe sous `(kind, name)`."""
    _verifier_kind(kind)

    def decorateur(cls: T) -> T:
        if (kind, name) in _REGISTRE:
            raise ConfigError(f"{kind}.{name}", "déjà enregistré")
        _REGISTRE[(kind, name)] = cls
        return cls

    return decorateur


def names(kind: str) -> list[str]:
    """Noms enregistrés pour un `kind`, triés."""
    return sorted(n for k, n in _REGISTRE if k == kind)


def get(kind: str, name: str) -> type:
    """Classe enregistrée ; `ConfigError` listant les noms du même `kind` si inconnue."""
    _verifier_kind(kind)
    try:
        return _REGISTRE[(kind, name)]
    except KeyError:
        disponibles = ", ".join(names(kind)) or "aucun"
        raise ConfigError(
            f"{kind}.{name}", f"{kind} inconnu « {name} » ; disponibles : {disponibles}"
        ) from None


def _nom_type(annotation: Any) -> str:
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _params(cls: type) -> tuple[ParamInfo, ...]:
    params = getattr(cls, "Params", None)
    champs = getattr(params, "model_fields", {})
    infos = []
    for nom, champ in champs.items():
        if champ.default is not PydanticUndefined:
            defaut = repr(champ.default)
        elif champ.default_factory is not None:
            defaut = repr(champ.default_factory())  # type: ignore[call-arg]
        else:
            defaut = "obligatoire"
        infos.append(ParamInfo(nom, _nom_type(champ.annotation), defaut))
    return tuple(infos)


def list_components(kind: str | None = None) -> list[ComponentInfo]:
    """Entrées du registre, triées par `kind` puis par nom ; filtrées par `kind` si donné."""
    if kind is not None:
        _verifier_kind(kind)
    return [
        ComponentInfo(k, n, inspect.getdoc(cls) or "", _params(cls))
        for (k, n), cls in sorted(_REGISTRE.items())
        if kind is None or k == kind
    ]


def discover() -> None:
    """Importe récursivement les paquets de Composants et d'Architectures ; idempotent."""
    global _decouvert
    if _decouvert:
        return
    for racine in _PAQUETS_DECOUVERTS:
        paquet = importlib.import_module(racine)
        for info in pkgutil.walk_packages(paquet.__path__, prefix=f"{racine}."):
            importlib.import_module(info.name)
    _decouvert = True
