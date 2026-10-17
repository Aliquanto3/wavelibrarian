"""Parser HTML (beautifulsoup4, analyseur de la bibliothèque standard) : titres h1 à h6."""

from typing import Any

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag
from pydantic import BaseModel, ConfigDict

from wavelibrarian.components.parsers._sections import SectionBuilder
from wavelibrarian.core.ids import sha16_bytes
from wavelibrarian.core.types import DocMeta, ParsedDocument
from wavelibrarian.registry import register

_TITRES = {f"h{n}": n for n in range(1, 7)}
_IGNORES = {"script", "style", "head", "template", "noscript", "title"}
# Balises qui forment un bloc : toute autre balise est en ligne et se fond dans le texte voisin.
_BLOCS = [
    "p", "div", "section", "article", "aside", "main", "header", "footer", "nav", "ul", "ol",
    "li", "dl", "dt", "dd", "blockquote", "pre", "figure", "figcaption", "form", "fieldset",
    "details", "summary", "address", "hr", "br",
]  # fmt: skip
_STRUCTURE = ["table", "img", *_BLOCS, *_TITRES]


def _texte(noeud: Tag) -> str:
    return " ".join(noeud.get_text(" ").split())


def _tableau(table: Tag) -> str:
    lignes = []
    for tr in table.find_all("tr"):
        cellules = [_texte(c) for c in tr.find_all(["th", "td"])]
        if any(cellules):
            lignes.append(" | ".join(cellules))
    return "\n".join(lignes)


def _structurel(tag: Tag) -> bool:
    return tag.name in _STRUCTURE or tag.find(_STRUCTURE) is not None


@register("parser", "html")
class HtmlParser:
    """HTML : un Block par titre, bloc de texte, tableau ou image, dans l'ordre du Document."""

    formats = frozenset({"html"})

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, params: Any = None, ctx: Any = None) -> None:
        pass

    def parse(self, source_path: str, raw: bytes, lang: str, meta: DocMeta) -> ParsedDocument:
        doc_id = sha16_bytes(raw)
        soupe = BeautifulSoup(raw.decode("utf-8-sig", errors="replace"), "html.parser")
        sections = SectionBuilder(doc_id, source_path)
        self._parcourir(soupe.body or soupe, sections)
        return ParsedDocument(
            doc_id=doc_id,
            source_path=source_path,
            format="html",
            lang=lang,
            blocks=tuple(sections.blocks),
            anchors=sections.anchors,
            meta=meta,
        )

    def _parcourir(self, parent: Tag, sections: SectionBuilder) -> None:
        tampon: list[str] = []

        def vider() -> None:
            sections.block("text", " ".join(" ".join(tampon).split()))
            tampon.clear()

        enfant: PageElement
        for enfant in parent.children:
            if isinstance(enfant, NavigableString):
                if type(enfant) is NavigableString:  # ni commentaire ni CDATA
                    tampon.append(str(enfant))
                continue
            if not isinstance(enfant, Tag) or enfant.name in _IGNORES:
                continue
            if enfant.name in _TITRES:
                vider()
                sections.heading(_TITRES[enfant.name], _texte(enfant))
            elif enfant.name == "table":
                vider()
                sections.block("table", _tableau(enfant))
            elif enfant.name == "img":
                vider()
                sections.block("image", str(enfant.get("alt") or enfant.get("src") or ""))
            elif enfant.name == "pre":
                vider()
                sections.block("text", enfant.get_text())
            elif _structurel(enfant):
                vider()
                self._parcourir(enfant, sections)
            else:
                tampon.append(enfant.get_text(" "))
        vider()
