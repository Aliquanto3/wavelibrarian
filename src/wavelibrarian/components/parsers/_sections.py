"""Construction commune des Blocks et des Ancrages à partir d'une suite de titres et de blocs.

Règle d'ancrage (AD-5) : un Block est rattaché au titre le plus profond ouvert, soit
`<doc_id>#h/<slug>/<slug>`. Le texte avant le premier titre, ou d'un fichier sans titre, est
rattaché à `<doc_id>#h/`. Deux titres frères de même slug reçoivent un suffixe ordinal : le
premier garde le slug, le deuxième prend `-2`, le troisième `-3`, etc. (déterministe, par ordre
dans le Document ; si `-2` est déjà le slug d'un vrai titre frère, on passe à `-3`).
`ParsedCorpus.resolve` cherche d'abord le chemin de titres bruts : il retrouve un vrai titre
« Note 2 » et, pour des doublons exacts, le premier ; les suivants s'adressent par leur
`anchor_id`. Un titre sans lettre ni chiffre prend le slug `section`.

Encodage : UTF-8 (BOM toléré) ; à défaut, repli explicite sur cp1252 avec un avertissement au
journal, plutôt que des caractères de remplacement qui fausseraient titres et slugs.
"""

import logging
from collections import defaultdict
from typing import Literal

from wavelibrarian.core.ids import slug
from wavelibrarian.core.types import Anchor, Block

Kind = Literal["text", "table", "heading", "image"]

log = logging.getLogger(__name__)


def decoder(raw: bytes, source_path: str) -> str:
    """Texte du Document : UTF-8 strict, sinon cp1252 signalé au journal."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        log.warning("%s n'est pas en UTF-8 : décodé en cp1252", source_path)
        return raw.decode("cp1252", errors="replace")


class SectionBuilder:
    """Accumule des titres et des blocs, puis expose `blocks` et `anchors` dans l'ordre."""

    def __init__(self, doc_id: str, source_path: str) -> None:
        self._doc_id = doc_id
        self._source_path = source_path
        self._pile: list[tuple[int, str, str]] = []  # (niveau, titre brut, slug final)
        self._freres: dict[tuple[str, ...], dict[str, int]] = defaultdict(dict)
        self._utilises: set[str] = set()
        self.blocks: list[Block] = []
        self.anchors: dict[str, Anchor] = {}

    def _ancre_courante(self) -> str:
        chemin = "/".join(s for _, _, s in self._pile)
        return f"{self._doc_id}#h/{chemin}"

    def _declarer(self, anchor_id: str) -> None:
        if anchor_id not in self.anchors:
            self.anchors[anchor_id] = Anchor(
                anchor_id=anchor_id,
                doc_id=self._doc_id,
                source_path=self._source_path,
                heading_path=tuple(t for _, t, _ in self._pile),
            )

    def heading(self, level: int, raw: str) -> None:
        raw = " ".join(raw.split())
        if not raw:
            return
        while self._pile and self._pile[-1][0] >= level:
            self._pile.pop()
        parent = tuple(s for _, _, s in self._pile)
        base = slug(raw) or "section"
        compteurs = self._freres[parent]
        rang = compteurs.get(base, 0) + 1
        final = base if rang == 1 else f"{base}-{rang}"
        while "/".join((*parent, final)) in self._utilises:  # « a-2 » déjà pris par un autre titre
            rang += 1
            final = f"{base}-{rang}"
        compteurs[base] = rang
        self._utilises.add("/".join((*parent, final)))
        self._pile.append((level, raw, final))
        self.block("heading", raw)

    def block(self, kind: Kind, text: str) -> None:
        text = text.strip()
        if not text:
            return
        anchor_id = self._ancre_courante()
        self._declarer(anchor_id)
        self.blocks.append(Block(text=text, anchor_id=anchor_id, kind=kind))
