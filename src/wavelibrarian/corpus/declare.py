"""Déclaration d'un Corpus : lecture de `corpus.yaml`, identité des Documents (FR-5, AD-5)."""

import logging
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wavelibrarian.config.defaults import charger_yaml
from wavelibrarian.config.schemas import valider
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16_bytes
from wavelibrarian.core.types import DocMeta

log = logging.getLogger(__name__)

DocFormat = Literal["markdown", "text", "html", "pdf"]

# Format du Document selon son extension (insensible à la casse).
EXTENSIONS: dict[str, DocFormat] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".html": "html",
    ".htm": "html",
    ".pdf": "pdf",
}


class _Schema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DocOverride(_Schema):
    """Métadonnées déclarées pour un Document (clé `documents:`, sans effet au MVP)."""

    lang: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    sensitivity: str | None = None
    rights_profiles: tuple[str, ...] = ()


class TiersSpec(_Schema):
    """Paliers de volume (FR-54) ; le tirage est fait par la story 2.7."""

    seed: int
    sizes: tuple[int, ...]

    @field_validator("sizes")
    @classmethod
    def _tailles(cls, v: tuple[int, ...]) -> tuple[int, ...]:
        if not v or any(t < 1 for t in v) or any(a >= b for a, b in zip(v, v[1:], strict=False)):
            raise ValueError("`sizes` doit être une liste strictement croissante d'entiers > 0")
        return v


class CorpusSpec(_Schema):
    """Schéma de `corpus.yaml` (contracts.md §4.1)."""

    corpus_id: str = Field(pattern=r"^[a-z0-9-]+$")
    path: str = Field(min_length=1)
    lang: str = Field(pattern=r"^[a-z]{2}$")
    license: str = Field(min_length=1)
    publishable: bool
    volatility: Literal["low", "medium", "high"]
    documents: dict[str, DocOverride] = {}
    tiers: TiersSpec | None = None


class Document(BaseModel):
    """Document retenu : identité de contenu, format, langue et métadonnées déclarées."""

    model_config = ConfigDict(frozen=True)

    source_path: str  # POSIX, relatif à la racine du Corpus (identité logique)
    doc_id: str  # sha256(octets)[:16] (identité de la version)
    format: DocFormat
    lang: str
    meta: DocMeta = DocMeta()


class DeclaredCorpus(BaseModel):
    """Corpus déclaré : spécification, racine absolue et Documents triés par `source_path`."""

    model_config = ConfigDict(frozen=True)

    spec: CorpusSpec
    root: Path
    documents: tuple[Document, ...]

    @property
    def corpus_id(self) -> str:
        return self.spec.corpus_id

    @property
    def formats(self) -> tuple[str, ...]:
        """Formats présents dans le Corpus, triés : de quoi remplacer `parser: auto` (story 2.2)."""
        return tuple(sorted({d.format for d in self.documents}))

    def read(self, doc: Document) -> bytes:
        """Octets bruts d'un Document."""
        return (self.root / doc.source_path).read_bytes()


def _git(racine: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # noqa: S603
            ["git", "-C", str(racine), *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None


def _verifier_droits(spec: CorpusSpec, racine: Path) -> None:
    """AD-19 : un Corpus non publiable dans le dépôt doit être dans un dossier ignoré par git."""
    if spec.publishable:
        return
    dans_depot = _git(racine, "rev-parse", "--is-inside-work-tree")
    if dans_depot is None or dans_depot.returncode != 0 or dans_depot.stdout.strip() != "true":
        log.warning(
            "Corpus %s non publiable hors d'un dépôt git : vérification des droits sautée.",
            spec.corpus_id,
        )
        return
    ignore = _git(racine, "check-ignore", "-q", str(racine))
    if ignore is not None and ignore.returncode == 0:
        return
    raise ConfigError(
        "path",
        f"le Corpus {spec.corpus_id!r} est publishable: false mais {racine} est dans un dépôt git "
        "sans être ignoré : placez le corpus hors du dépôt ou dans un dossier ignoré "
        "(.gitignore), sinon il risque d'être publié.",
    )


def _surcharges(spec: CorpusSpec, sources: set[str]) -> dict[str, DocOverride]:
    """Associe chaque clé de `documents:` à un `source_path` retenu.

    Le contrat définit la clé comme le `source_path` (relatif à la racine) ; son exemple la
    préfixe pourtant par `path` (`docs/charte.md`). On accepte les deux écritures.
    """
    prefixe = Path(spec.path).as_posix().strip("/") + "/"
    res: dict[str, DocOverride] = {}
    for cle, meta in spec.documents.items():
        norm = cle.replace("\\", "/").removeprefix("./")
        cible = norm if norm in sources else norm.removeprefix(prefixe)
        if cible not in sources:
            raise ConfigError(
                f"documents.{cle}", "aucun Document retenu ne porte ce source_path dans le Corpus"
            )
        if cible in res:
            raise ConfigError(f"documents.{cle}", f"Document {cible!r} déclaré deux fois")
        res[cible] = meta
    return res


def declare(chemin: Path) -> DeclaredCorpus:
    """Déclare le Corpus décrit par `chemin` (`corpus.yaml`).

    `path` est relatif au dossier du fichier. Les Documents au format non pris en charge sont
    signalés au journal et ignorés. Erreurs : `ConfigError` au chemin pointé.
    """
    donnees: Any = charger_yaml(chemin)
    if not isinstance(donnees, dict):
        raise ConfigError(str(chemin), "un Corpus doit être un dictionnaire YAML")
    spec = valider(CorpusSpec, donnees, str(chemin))
    racine = (chemin.parent / spec.path).resolve()
    if not racine.is_dir():
        raise ConfigError("path", f"dossier introuvable : {racine}")
    _verifier_droits(spec, racine)

    retenus: list[tuple[str, DocFormat, str]] = []
    vus: dict[str, str] = {}
    fichiers = sorted(
        (p for p in racine.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(racine).as_posix(),
    )
    for fichier in fichiers:
        rel = fichier.relative_to(racine).as_posix()
        fmt = EXTENSIONS.get(fichier.suffix.lower())
        if fmt is None:
            log.warning("Document %s ignoré : format non pris en charge (%s).", rel, fichier.suffix)
            continue
        doc_id = sha16_bytes(fichier.read_bytes())
        if doc_id in vus:
            raise ConfigError(
                "path",
                f"{rel} et {vus[doc_id]} ont un contenu identique (doc_id {doc_id}) : "
                "retirez le doublon, les Ancrages seraient ambigus.",
            )
        vus[doc_id] = rel
        retenus.append((rel, fmt, doc_id))

    surcharges = _surcharges(spec, {r for r, _, _ in retenus})
    documents = []
    for rel, fmt, doc_id in retenus:
        sur = surcharges.get(rel)
        meta = (
            DocMeta(sensitivity=sur.sensitivity, rights_profiles=sur.rights_profiles)
            if sur
            else DocMeta()
        )
        documents.append(
            Document(
                source_path=rel,
                doc_id=doc_id,
                format=fmt,
                lang=sur.lang if sur and sur.lang else spec.lang,
                meta=meta,
            )
        )
    return DeclaredCorpus(spec=spec, root=racine, documents=tuple(documents))
