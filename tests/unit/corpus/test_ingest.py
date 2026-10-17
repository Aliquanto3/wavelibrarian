"""Tests des Parsers markdown, text, html et de l'ingestion (story 2.2)."""

import json
from pathlib import Path

import pytest
import yaml

from wavelibrarian import registry
from wavelibrarian.components.parsers.html import HtmlParser
from wavelibrarian.components.parsers.markdown import MarkdownParser
from wavelibrarian.components.parsers.text import TextParser
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16_bytes
from wavelibrarian.core.types import DocMeta, ParsedCorpus
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest, nom_parser_resolu, parsers_par_format

MD = b"""Intro avant titre.

# Histoire

Texte de l'histoire.

## Fondation

Paragraphe fondateur.

| Annee | Fait |
| ----- | ---- |
| 1900  | Debut |

![Plan du site](plan.png)
"""


def _parse(cls, nom: str, raw: bytes):
    return cls().parse(nom, raw, "fr", DocMeta())


def test_enregistrement_au_registre():
    registry.discover()
    assert {"markdown", "text", "html"} <= set(registry.names("parser"))
    assert registry.get("parser", "markdown").formats == frozenset({"markdown"})
    assert registry.get("parser", "text").formats == frozenset({"text"})
    assert registry.get("parser", "html").formats == frozenset({"html"})


def test_markdown_blocks_et_ancrages():
    doc = _parse(MarkdownParser, "a.md", MD)
    d = sha16_bytes(MD)
    assert doc.doc_id == d
    assert all(b.text for b in doc.blocks)
    kinds = [(b.kind, b.anchor_id) for b in doc.blocks]
    assert kinds[0] == ("text", f"{d}#h/")  # texte avant le premier titre
    assert ("heading", f"{d}#h/histoire") in kinds
    assert ("heading", f"{d}#h/histoire/fondation") in kinds
    sous = [b for b in doc.blocks if b.anchor_id == f"{d}#h/histoire/fondation"]
    assert {b.kind for b in sous} == {"heading", "text", "table", "image"}
    table = next(b for b in sous if b.kind == "table")
    assert table.text == "Annee | Fait\n1900 | Debut"
    assert next(b for b in sous if b.kind == "image").text == "Plan du site"
    assert list(doc.anchors) == [f"{d}#h/", f"{d}#h/histoire", f"{d}#h/histoire/fondation"]
    assert doc.anchors[f"{d}#h/histoire/fondation"].heading_path == ("Histoire", "Fondation")
    assert doc.anchors[f"{d}#h/"].heading_path == ()


def test_texte_sans_titre_sous_ancrage_vide():
    raw = b"Premier paragraphe.\n\nSecond\nparagraphe.\n"
    doc = _parse(TextParser, "n.txt", raw)
    d = sha16_bytes(raw)
    assert [b.anchor_id for b in doc.blocks] == [f"{d}#h/", f"{d}#h/"]
    assert [b.kind for b in doc.blocks] == ["text", "text"]
    assert list(doc.anchors) == [f"{d}#h/"]
    assert doc.format == "text"


def test_markdown_sans_titre_rattache_a_h_vide():
    raw = b"Juste un paragraphe.\n"
    doc = _parse(MarkdownParser, "n.md", raw)
    assert list(doc.anchors) == [f"{sha16_bytes(raw)}#h/"]


def test_html_hierarchie_et_tableau():
    raw = (
        b"<html><head><title>T</title><style>p{}</style></head><body>"
        b"<p>Avant.</p><h1>Guide</h1><p>Intro</p><h2>Etape A</h2>"
        b"<div><p>Texte A</p><table><tr><th>X</th><th>Y</th></tr><tr><td>1</td><td>2</td></tr>"
        b"</table></div><h3>Detail</h3><p>Fin <b>grasse</b>.</p><h2>Etape B</h2><p>B</p>"
        b"</body></html>"
    )
    doc = _parse(HtmlParser, "g.html", raw)
    d = sha16_bytes(raw)
    assert list(doc.anchors) == [
        f"{d}#h/",
        f"{d}#h/guide",
        f"{d}#h/guide/etape-a",
        f"{d}#h/guide/etape-a/detail",
        f"{d}#h/guide/etape-b",
    ]
    table = next(b for b in doc.blocks if b.kind == "table")
    assert table.anchor_id == f"{d}#h/guide/etape-a"
    assert table.text == "X | Y\n1 | 2"
    assert doc.blocks[0].text == "Avant."
    assert doc.blocks[-3].text == "Fin grasse."  # balise en ligne fondue sans espace parasite
    assert all("p{}" not in b.text and b.text != "T" for b in doc.blocks)


def test_html_script_style_dans_body_ignores():
    raw = b"<body><script>var x=1</script><h1>A</h1><style>a{}</style><p>x</p></body>"
    doc = _parse(HtmlParser, "s.html", raw)
    assert [(b.kind, b.text) for b in doc.blocks] == [("heading", "A"), ("text", "x")]


def test_encodage_utf8_et_repli_cp1252(caplog: pytest.LogCaptureFixture):
    # UTF-8 avec BOM : accents conservés, slug ASCII
    raw = "﻿<h1>Été</h1><p>déjà</p>".encode()
    doc = _parse(HtmlParser, "u.html", raw)
    d = sha16_bytes(raw)
    assert list(doc.anchors) == [f"{d}#h/ete"]
    assert doc.anchors[f"{d}#h/ete"].heading_path == ("Été",)
    # cp1252 : repli explicite signalé au journal, pas de caractère de remplacement
    raw = "# Été\n\ndéjà\n".encode("cp1252")
    doc = _parse(MarkdownParser, "c.md", raw)
    assert list(doc.anchors) == [f"{sha16_bytes(raw)}#h/ete"]
    assert [b.text for b in doc.blocks] == ["Été", "déjà"]
    assert "UTF-8" in caplog.text


def test_crlf_meme_ancrage_que_lf():
    lf = b"# Histoire\n\n## Fondation\n\nTexte.\n"
    crlf = lf.replace(b"\n", b"\r\n")
    a, b = _parse(MarkdownParser, "a.md", lf), _parse(MarkdownParser, "a.md", crlf)
    suffixes = [k.split("#", 1)[1] for k in a.anchors]
    assert suffixes == ["h/histoire", "h/histoire/fondation"]
    assert [k.split("#", 1)[1] for k in b.anchors] == suffixes
    assert [x.text for x in a.blocks] == [x.text for x in b.blocks]


def test_titre_dans_citation_ou_liste_ouvre_une_section():
    raw = b"> # Cit\n> txt\n\n- ## Li\n  t\n"
    doc = _parse(MarkdownParser, "q.md", raw)
    d = sha16_bytes(raw)
    assert [(b.kind, b.text, b.anchor_id) for b in doc.blocks] == [
        ("heading", "Cit", f"{d}#h/cit"),
        ("text", "txt", f"{d}#h/cit"),
        ("heading", "Li", f"{d}#h/cit/li"),
        ("text", "t", f"{d}#h/cit/li"),
    ]


def test_freres_identiques_ordinal_deterministe():
    raw = b"# Doc\n\n## Note\n\na\n\n## Note\n\nb\n\n## Note\n\nc\n\n## Note 2\n\nd\n"
    doc1 = _parse(MarkdownParser, "d.md", raw)
    doc2 = _parse(MarkdownParser, "d.md", raw)
    d = sha16_bytes(raw)
    attendu = [
        f"{d}#h/doc",
        f"{d}#h/doc/note",
        f"{d}#h/doc/note-2",
        f"{d}#h/doc/note-3",
        f"{d}#h/doc/note-2-2",  # « Note 2 » ne peut pas reprendre « note-2 » déjà pris
    ]
    assert list(doc1.anchors) == attendu
    assert list(doc2.anchors) == attendu
    assert doc1.anchors[attendu[2]].heading_path == ("Doc", "Note")
    # resolve suit les titres bruts : « Note 2 » est le vrai titre, pas le doublon `note-2`
    corpus = ParsedCorpus(corpus_id="c", fingerprint="f", documents=(doc1,))
    assert corpus.resolve("d.md", None, ("Doc", "Note 2")) == attendu[4]
    assert corpus.anchor_text(attendu[4]) == "Note 2\n\nd"
    assert corpus.resolve("d.md", None, ("Doc", "Note")) == attendu[1]  # premier des doublons
    assert corpus.resolve("d.md", None, ("Doc", "  Note ")) == attendu[1]  # espaces normalisés
    assert corpus.resolve("d.md", None, ("doc", "note")) == attendu[1]  # repli sur les slugs


def test_niveaux_sautes_et_remontee():
    raw = b"# A\n\n### C\n\nc\n\n## B\n\nb\n\n# A2\n\nz\n"
    doc = _parse(MarkdownParser, "d.md", raw)
    d = sha16_bytes(raw)
    assert list(doc.anchors) == [f"{d}#h/a", f"{d}#h/a/c", f"{d}#h/a/b", f"{d}#h/a2"]


def _corpus(racine: Path, fichiers: dict[str, bytes]) -> Path:
    docs = racine / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for nom, contenu in fichiers.items():
        cible = docs / nom
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(contenu)
    spec = {
        "corpus_id": "demo",
        "path": "docs",
        "lang": "fr",
        "license": "CC-BY-4.0",
        "publishable": True,
        "volatility": "low",
    }
    fichier = racine / "corpus.yaml"
    fichier.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return fichier


def test_parsers_par_format_auto():
    assert parsers_par_format(["markdown", "text", "html"]) == {
        "html": "html",
        "markdown": "markdown",
        "text": "text",
    }
    assert nom_parser_resolu({"markdown": "markdown", "text": "text"}) == "markdown+text"
    assert parsers_par_format(["markdown"], "markdown") == {"markdown": "markdown"}
    with pytest.raises(ConfigError):
        parsers_par_format(["html"], "markdown")  # le Parser ne couvre pas le format
    with pytest.raises(ConfigError):
        parsers_par_format(["markdown"], "inconnu")
    with pytest.raises(ConfigError, match="pdf_text » non encore disponible"):
        parsers_par_format(["pdf"])  # pdf_text arrive avec la story 2.3


def test_ingest_trie_fingerprint_et_resolve(tmp_path: Path, wl_home: Path):
    fichier = _corpus(
        tmp_path,
        {"z.txt": b"zzz", "b/a.md": MD, "a.html": b"<h1>H</h1><p>x</p>"},
    )
    corpus = declare(fichier)
    parse = ingest(corpus)
    assert [d.source_path for d in parse.documents] == ["a.html", "b/a.md", "z.txt"]
    assert [d.format for d in parse.documents] == ["html", "markdown", "text"]
    # le fingerprint ne dépend que des couples triés (source_path, doc_id)
    assert parse.fingerprint == ingest(corpus).fingerprint
    autre = declare(
        _corpus(tmp_path / "bis", {"z.txt": b"zzz", "b/a.md": MD, "a.html": b"<h1>H</h1>y"})
    )
    assert ingest(autre, wl_home=wl_home).fingerprint != parse.fingerprint
    # resolve / anchor_text sur une section
    ancre = parse.resolve("b/a.md", None, ("Histoire", "Fondation"))
    assert ancre == f"{sha16_bytes(MD)}#h/histoire/fondation"
    assert ancre is not None
    texte = parse.anchor_text(ancre)
    assert "Paragraphe fondateur." in texte and "Debut" in texte
    assert parse.resolve("b/a.md", None, ("Absent",)) is None
    assert parse.resolve("z.txt", None, ()) is None


def test_cache_relu_sans_appeler_le_parser(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
):
    corpus = declare(_corpus(tmp_path, {"a.md": MD, "b.txt": b"bb"}))
    appels: list[str] = []
    original = MarkdownParser.parse

    def compte(self, source_path, raw, lang, meta):
        appels.append(source_path)
        return original(self, source_path, raw, lang, meta)

    monkeypatch.setattr(MarkdownParser, "parse", compte)
    premier = ingest(corpus)
    assert appels == ["a.md"]
    fichier = wl_home / "parse_cache" / "markdown" / f"{sha16_bytes(MD)}.json"
    assert fichier.is_file()
    assert (wl_home / "parse_cache" / "text" / f"{sha16_bytes(b'bb')}.json").is_file()
    second = ingest(corpus)
    assert appels == ["a.md"]  # relu du cache
    assert second == premier


def test_cache_corrompu_reparse_et_renommage(tmp_path: Path, wl_home: Path):
    corpus = declare(_corpus(tmp_path, {"a.md": MD}))
    ingest(corpus)
    (wl_home / "parse_cache" / "markdown" / f"{sha16_bytes(MD)}.json").write_text("{pas du json")
    assert len(ingest(corpus).documents) == 1  # reparsé sans erreur
    # une autre version du Parser invalide le cache
    fichier = wl_home / "parse_cache" / "markdown" / f"{sha16_bytes(MD)}.json"
    assert json.loads(fichier.read_text(encoding="utf-8"))["parser_version"] == "1"
    appels: list[str] = []
    original = MarkdownParser.parse

    def compte(self, source_path, raw, lang, meta):
        appels.append(source_path)
        return original(self, source_path, raw, lang, meta)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MarkdownParser, "parse", compte)
        ingest(corpus)
        assert appels == []
        mp.setattr(MarkdownParser, "version", "2")
        ingest(corpus)
        assert appels == ["a.md"]
    # même contenu sous un autre nom : le cache par contenu est réancré sur le nouveau chemin
    renomme = declare(_corpus(tmp_path / "r", {"autre.md": MD}))
    doc = ingest(renomme).documents[0]
    assert doc.source_path == "autre.md"
    assert {a.source_path for a in doc.anchors.values()} == {"autre.md"}


def test_corpus_vide(tmp_path: Path, wl_home: Path):
    parse = ingest(declare(_corpus(tmp_path, {"x.docx": b"x"})))
    assert parse.documents == ()
