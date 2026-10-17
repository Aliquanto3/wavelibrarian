"""Parser de texte brut : paragraphes séparés par une ligne vide, rattachés à `<doc_id>#h/`."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from wavelibrarian.components.parsers._sections import SectionBuilder, decoder
from wavelibrarian.core.ids import sha16_bytes
from wavelibrarian.core.types import DocMeta, ParsedDocument
from wavelibrarian.registry import register


@register("parser", "text")
class TextParser:
    """Texte brut sans titre : un Block `text` par paragraphe, tous sous l'Ancrage `#h/`."""

    formats = frozenset({"text"})
    version = "1"  # à incrémenter quand la sortie change : invalide le cache de parsing

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, params: Any = None, ctx: Any = None) -> None:
        pass

    def parse(self, source_path: str, raw: bytes, lang: str, meta: DocMeta) -> ParsedDocument:
        doc_id = sha16_bytes(raw)
        texte = decoder(raw, source_path).replace("\r\n", "\n").replace("\r", "\n")
        sections = SectionBuilder(doc_id, source_path)
        for paragraphe in re.split(r"\n\s*\n", texte):
            sections.block("text", paragraphe)
        return ParsedDocument(
            doc_id=doc_id,
            source_path=source_path,
            format="text",
            lang=lang,
            blocks=tuple(sections.blocks),
            anchors=sections.anchors,
            meta=meta,
        )
