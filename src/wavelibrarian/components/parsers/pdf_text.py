"""Parser PDF (pypdfium2) : un Block `text` et un Ancrage `<doc_id>#p<page>` par page (AD-5)."""

from typing import Any

import pypdfium2 as pdfium
from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.ids import sha16_bytes
from wavelibrarian.core.types import Anchor, Block, DocMeta, ParsedDocument
from wavelibrarian.registry import register


@register("parser", "pdf_text")
class PdfTextParser:
    """Texte extractible de chaque page ; pages numérotées dès 1, sans OCR ni mise en page."""

    formats = frozenset({"pdf"})
    version = "1"  # à incrémenter quand la sortie change : invalide le cache de parsing

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, params: Any = None, ctx: Any = None) -> None:
        pass

    def parse(self, source_path: str, raw: bytes, lang: str, meta: DocMeta) -> ParsedDocument:
        """`ValueError` si le PDF est illisible : l'ingestion signale le Document et l'ignore."""
        doc_id = sha16_bytes(raw)
        try:
            pdf = pdfium.PdfDocument(raw)
        except (pdfium.PdfiumError, RuntimeError, OSError) as exc:
            raise ValueError(f"PDF illisible : {exc}") from exc
        blocks: list[Block] = []
        anchors: dict[str, Anchor] = {}
        try:
            for index in range(len(pdf)):
                numero = index + 1
                anchor_id = f"{doc_id}#p{numero}"
                # L'Ancrage existe même pour une page sans texte (alors sans Block).
                anchors[anchor_id] = Anchor(
                    anchor_id=anchor_id, doc_id=doc_id, source_path=source_path, page=numero
                )
                try:
                    page = pdf[index]
                    try:
                        textpage = page.get_textpage()
                        try:
                            texte = textpage.get_text_bounded()
                        finally:
                            textpage.close()
                    finally:
                        page.close()
                except (pdfium.PdfiumError, RuntimeError) as exc:
                    raise ValueError(f"PDF illisible (page {numero}) : {exc}") from exc
                texte = texte.replace("\r\n", "\n").replace("\r", "\n").strip()
                if texte:
                    blocks.append(Block(text=texte, anchor_id=anchor_id, kind="text"))
        finally:
            pdf.close()
        return ParsedDocument(
            doc_id=doc_id,
            source_path=source_path,
            format="pdf",
            lang=lang,
            blocks=tuple(blocks),
            anchors=anchors,
            meta=meta,
        )
