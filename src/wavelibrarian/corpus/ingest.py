"""Ingestion d'un Corpus déclaré : Parsers par format, cache de parsing, `ParsedCorpus` (FR-6).

Les Parsers sont obtenus par le registre (`kind: parser`), sans importer `components` (AD-1).
"""

import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from wavelibrarian import registry
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import ParsedCorpus, ParsedDocument
from wavelibrarian.corpus.declare import DeclaredCorpus, Document

log = logging.getLogger(__name__)

# Parser par défaut de chaque format quand `parser: auto` (le PDF arrive avec la story 2.3).
AUTO: dict[str, str] = {"markdown": "markdown", "text": "text", "html": "html", "pdf": "pdf_text"}


def parsers_par_format(formats: Iterable[str], parser: str = "auto") -> dict[str, str]:
    """Nom concret du Parser de chaque format ; remplace `parser: auto` (runner, epic 4).

    `auto` : le Parser par défaut du format, qui doit être enregistré et déclarer ce format.
    Un nom explicite doit couvrir tous les formats demandés. `ConfigError` sinon.
    """
    registry.discover()
    resultat: dict[str, str] = {}
    for fmt in sorted(set(formats)):
        nom = AUTO.get(fmt) if parser == "auto" else parser
        if nom is None or nom not in registry.names("parser"):
            enregistres = ", ".join(registry.names("parser")) or "aucun"
            raise ConfigError(
                "parser",
                f"aucun Parser enregistré pour le format « {fmt} » (parser demandé : {parser}) ;"
                f" Parsers disponibles : {enregistres}",
            )
        if fmt not in getattr(registry.get("parser", nom), "formats", frozenset()):
            raise ConfigError("parser", f"le Parser « {nom} » ne prend pas en charge « {fmt} »")
        resultat[fmt] = nom
    return resultat


def nom_parser_resolu(par_format: dict[str, str]) -> str:
    """Nom unique d'un jeu de Parsers (`markdown`, ou `html+markdown` si plusieurs)."""
    return "+".join(sorted(set(par_format.values())))


def _wl_home(wl_home: Path | None) -> Path:
    return wl_home or Path(os.environ.get("WL_HOME") or ".wl")


def _lire_cache(chemin: Path) -> ParsedDocument | None:
    try:
        return ParsedDocument.model_validate_json(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # absent ou corrompu : on reparse


def _ecrire_cache(chemin: Path, doc: ParsedDocument) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(f"{chemin.name}.{os.getpid()}.tmp")
    tmp.write_text(doc.model_dump_json(), encoding="utf-8")
    tmp.replace(chemin)


def _reancrer(parse: ParsedDocument, doc: Document) -> ParsedDocument:
    """Reprend chemin, langue et métadonnées du Document déclaré (le cache est par contenu)."""
    if (parse.source_path, parse.lang, parse.meta) == (doc.source_path, doc.lang, doc.meta):
        return parse
    ancres = {
        k: a.model_copy(update={"source_path": doc.source_path}) for k, a in parse.anchors.items()
    }
    return parse.model_copy(
        update={
            "source_path": doc.source_path,
            "lang": doc.lang,
            "meta": doc.meta,
            "anchors": ancres,
        }
    )


def ingest(
    corpus: DeclaredCorpus, parser: str = "auto", *, wl_home: Path | None = None
) -> ParsedCorpus:
    """Parse les Documents du Corpus (cache par Document et par Parser) en `ParsedCorpus`.

    Un Document que son Parser ne sait pas lire est signalé au journal et ignoré.
    """
    par_format = parsers_par_format(corpus.formats, parser)
    cache = _wl_home(wl_home) / "parse_cache"
    instances: dict[str, Any] = {}
    documents: list[ParsedDocument] = []
    for doc in corpus.documents:  # déjà triés par source_path
        nom = par_format[doc.format]
        fichier = cache / nom / f"{doc.doc_id}.json"
        parse = _lire_cache(fichier)
        if parse is None:
            if nom not in instances:
                cls = registry.get("parser", nom)
                instances[nom] = cls(cls.Params(), None)
            try:
                parse = instances[nom].parse(doc.source_path, corpus.read(doc), doc.lang, doc.meta)
            except (OSError, ValueError) as exc:
                log.warning("Document illisible ignoré : %s (%s)", doc.source_path, exc)
                continue
            _ecrire_cache(fichier, parse)
        documents.append(_reancrer(parse, doc))
    paires = sorted((d.source_path, d.doc_id) for d in documents)
    fingerprint = sha16(*(f"{p}\x1e{i}" for p, i in paires))
    return ParsedCorpus(
        corpus_id=corpus.corpus_id,
        fingerprint=fingerprint,
        documents=tuple(sorted(documents, key=lambda d: d.source_path)),
    )
