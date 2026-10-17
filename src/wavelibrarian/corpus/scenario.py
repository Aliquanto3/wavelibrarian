"""Scénario de mise à jour : chargement et application à un `ParsedCorpus` (FR-53, contracts §4.7).

Le Scénario ne modifie jamais le dossier `docs/` : les Documents ajoutés ou modifiés sont lus
dans les `source` du Scénario et parsés en mémoire (sans cache de parsing).
"""

from collections import Counter
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavelibrarian import registry
from wavelibrarian.config.defaults import charger_yaml
from wavelibrarian.config.schemas import valider
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import DocMeta, ParsedCorpus, ParsedDocument
from wavelibrarian.corpus.declare import EXTENSIONS
from wavelibrarian.corpus.ingest import empreinte, parsers_par_format
from wavelibrarian.ports.architecture import CorpusChange


class _Schema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Operation(_Schema):
    id: str = Field(min_length=1)
    op: Literal["add", "modify", "delete"]
    source: str | None = None  # relatif au fichier du Scénario
    target: str = Field(min_length=1)  # `source_path` du Corpus

    @model_validator(mode="after")
    def _source(self) -> Self:
        if self.op == "delete" and self.source is not None:
            raise ValueError("`source` interdit pour une opération delete")
        if self.op != "delete" and not self.source:
            raise ValueError(f"`source` obligatoire pour une opération {self.op}")
        return self


class Scenario(_Schema):
    scenario_id: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    operations: tuple[Operation, ...] = Field(min_length=1)


class ScenarioCharge(BaseModel):
    """Scénario validé ; `dossier` sert à résoudre les `source`."""

    model_config = ConfigDict(frozen=True)

    scenario: Scenario
    dossier: Path


def _format(chemin: str) -> str | None:
    return EXTENSIONS.get(Path(chemin).suffix.lower())


def charger(chemin: Path, parsed: ParsedCorpus) -> ScenarioCharge:
    """Lit le Scénario et le valide contre `parsed` (opérations simulées dans l'ordre).

    `ConfigError` au chemin `operations[i]` : `add` sur un `target` présent, `modify` ou `delete`
    sur un `target` absent, `source` introuvable ou d'un autre format que le `target`.
    """
    scenario = valider(Scenario, charger_yaml(chemin), str(chemin))
    if scenario.corpus_id != parsed.corpus_id:
        raise ConfigError(
            "corpus_id",
            f"le Scénario vise le Corpus {scenario.corpus_id!r}, pas {parsed.corpus_id!r}",
        )
    dossier = chemin.resolve().parent
    presents = {d.source_path for d in parsed.documents}
    vus: set[str] = set()
    for i, op in enumerate(scenario.operations):
        pos = f"operations[{i}]"
        if op.id in vus:
            raise ConfigError(f"{pos}.id", f"identifiant {op.id!r} en double")
        vus.add(op.id)
        if op.op == "add" and op.target in presents:
            raise ConfigError(f"{pos}.target", f"{op.target!r} est déjà dans le Corpus")
        if op.op != "add" and op.target not in presents:
            raise ConfigError(f"{pos}.target", f"{op.target!r} n'est pas dans le Corpus")
        if op.source is not None:
            if not (dossier / op.source).is_file():
                raise ConfigError(f"{pos}.source", f"{op.source!r} introuvable")
            if _format(op.source) is None or _format(op.source) != _format(op.target):
                raise ConfigError(
                    f"{pos}.source", f"{op.source!r} n'a pas le format de {op.target!r}"
                )
        if op.op == "delete":
            presents.discard(op.target)
        else:
            presents.add(op.target)
    return ScenarioCharge(scenario=scenario, dossier=dossier)


def _parser(fmt: str, cache: dict[str, Any]) -> Any:
    if fmt not in cache:
        cls = registry.get("parser", parsers_par_format([fmt])[fmt])
        cache[fmt] = cls(cls.Params(), None)
    return cache[fmt]


def _langue_majoritaire(parsed: ParsedCorpus) -> str:
    comptes = Counter(d.lang for d in parsed.documents)
    return min(comptes, key=lambda lang: (-comptes[lang], lang)) if comptes else "en"


def appliquer(parsed: ParsedCorpus, charge: ScenarioCharge) -> tuple[CorpusChange, ParsedCorpus]:
    """Applique les opérations dans l'ordre ; `parsed` n'est pas modifié.

    `CorpusChange` est le changement net, trié par `source_path`. Un Document ajouté prend la
    langue majoritaire du Corpus ; un Document modifié garde sa langue et ses métadonnées.
    """
    avant = {d.source_path: d for d in parsed.documents}
    courant = dict(avant)
    parsers: dict[str, Any] = {}
    langue = _langue_majoritaire(parsed)
    for i, op in enumerate(charge.scenario.operations):
        if op.op == "delete":
            del courant[op.target]
            continue
        assert op.source is not None  # garanti par le schéma
        fmt = _format(op.target)
        assert fmt is not None  # vérifié par `charger`
        brut = (charge.dossier / op.source).read_bytes()
        ancien = courant.get(op.target)
        lang = ancien.lang if ancien else langue
        meta = ancien.meta if ancien else DocMeta()
        try:
            doc = _parser(fmt, parsers).parse(op.target, brut, lang, meta)
        except (OSError, ValueError) as exc:
            raise ConfigError(
                f"operations[{i}].source", f"{op.source!r} illisible : {exc}"
            ) from exc
        if doc.doc_id in {d.doc_id for p, d in courant.items() if p != op.target}:
            raise ConfigError(
                f"operations[{i}].source", f"{op.source!r} a le contenu d'un Document existant"
            )
        courant[op.target] = doc
    documents: tuple[ParsedDocument, ...] = tuple(courant[p] for p in sorted(courant))
    changement = CorpusChange(
        added=tuple(courant[p] for p in sorted(courant) if p not in avant),
        removed=tuple(avant[p].doc_id for p in sorted(avant) if p not in courant),
        modified=tuple(
            (avant[p].doc_id, courant[p])
            for p in sorted(avant)
            if p in courant and courant[p].doc_id != avant[p].doc_id
        ),
    )
    apres = ParsedCorpus(
        corpus_id=parsed.corpus_id, fingerprint=empreinte(documents), documents=documents
    )
    return changement, apres


def appliquer_fichier(parsed: ParsedCorpus, chemin: Path) -> tuple[CorpusChange, ParsedCorpus]:
    """`charger` puis `appliquer`."""
    return appliquer(parsed, charger(chemin, parsed))


def corpus_apres(parsed: ParsedCorpus, chemin: Path) -> ParsedCorpus:
    """Corpus après application du Scénario `chemin` (utilisé par `wl questions controler`)."""
    return appliquer_fichier(parsed, chemin)[1]
