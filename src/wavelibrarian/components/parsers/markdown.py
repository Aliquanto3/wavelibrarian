"""Parser Markdown (markdown-it-py) : titres, paragraphes, listes, tableaux, images."""

from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token
from pydantic import BaseModel, ConfigDict

from wavelibrarian.components.parsers._sections import SectionBuilder
from wavelibrarian.core.ids import sha16_bytes
from wavelibrarian.core.types import DocMeta, ParsedDocument
from wavelibrarian.registry import register


def _texte_inline(tok: Token, images: list[str] | None = None) -> str:
    """Texte brut d'un jeton `inline` ; les images sont sorties dans `images` si fourni."""
    morceaux: list[str] = []
    for enfant in tok.children or []:
        if enfant.type == "image":
            alt = enfant.content or str(enfant.attrs.get("src", ""))
            if images is not None:
                images.append(alt)
            else:
                morceaux.append(alt)
        elif enfant.type in ("softbreak", "hardbreak"):
            morceaux.append("\n")
        elif enfant.type in ("text", "code_inline"):
            morceaux.append(enfant.content)
    return "".join(morceaux)


def _fermeture(jetons: list[Token], i: int) -> int:
    """Indice du jeton fermant qui correspond au jeton ouvrant `i`."""
    niveau = jetons[i].level
    j = i + 1
    while not (jetons[j].level == niveau and jetons[j].nesting == -1):
        j += 1
    return j


@register("parser", "markdown")
class MarkdownParser:
    """Markdown : un Block par titre, paragraphe, liste, bloc de code, tableau ou image."""

    formats = frozenset({"markdown"})

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, params: Any = None, ctx: Any = None) -> None:
        self._md = MarkdownIt("commonmark").enable("table")

    def parse(self, source_path: str, raw: bytes, lang: str, meta: DocMeta) -> ParsedDocument:
        doc_id = sha16_bytes(raw)
        texte = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        jetons = self._md.parse(texte)
        sections = SectionBuilder(doc_id, source_path)
        i = 0
        while i < len(jetons):
            tok = jetons[i]
            if tok.type == "heading_open":
                sections.heading(int(tok.tag[1]), _texte_inline(jetons[i + 1]))
                i += 3
            elif tok.type == "table_open":
                fin = _fermeture(jetons, i)
                sections.block("table", self._tableau(jetons[i:fin]))
                i = fin + 1
            elif tok.nesting == 1:
                fin = _fermeture(jetons, i)
                self._bloc(sections, jetons[i + 1 : fin])
                i = fin + 1
            else:  # fence, code_block, html_block, hr
                if tok.type in ("fence", "code_block", "html_block"):
                    sections.block("text", tok.content)
                i += 1
        return ParsedDocument(
            doc_id=doc_id,
            source_path=source_path,
            format="markdown",
            lang=lang,
            blocks=tuple(sections.blocks),
            anchors=sections.anchors,
            meta=meta,
        )

    @staticmethod
    def _tableau(jetons: list[Token]) -> str:
        lignes: list[str] = []
        cellules: list[str] = []
        for tok in jetons:
            if tok.type == "inline":
                cellules.append(_texte_inline(tok).strip())
            elif tok.type == "tr_close":
                lignes.append(" | ".join(cellules))
                cellules = []
        return "\n".join(lignes)

    @staticmethod
    def _bloc(sections: SectionBuilder, jetons: list[Token]) -> None:
        """Paragraphe, liste ou citation : images en Blocks `image`, le reste en un Block `text`."""
        lignes: list[str] = []
        images: list[str] = []
        for tok in jetons:
            if tok.type == "inline":
                lignes.append(_texte_inline(tok, images))
            elif tok.type in ("fence", "code_block"):
                lignes.append(tok.content)
        sections.block("text", "\n".join(ligne for ligne in lignes if ligne.strip()))
        for alt in images:
            sections.block("image", alt)
