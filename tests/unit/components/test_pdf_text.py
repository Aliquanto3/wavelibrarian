"""Tests du Parser `pdf_text` et de l'ingestion de PDF (story 2.3)."""

import logging
from pathlib import Path

import pytest
import yaml
from fpdf import FPDF

from wavelibrarian import registry
from wavelibrarian.components.parsers.pdf_text import PdfTextParser, normaliser
from wavelibrarian.core.ids import sha16_bytes
from wavelibrarian.core.types import DocMeta
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest, parsers_par_format


def _pdf(textes: list[str]) -> bytes:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for texte in textes:
        pdf.add_page()
        if texte:
            pdf.cell(text=texte)
    return bytes(pdf.output())


def _corpus(tmp_path: Path, fichiers: dict[str, bytes]) -> Path:
    for nom, octets in fichiers.items():
        chemin = tmp_path / "docs" / nom
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(octets)
    fichier = tmp_path / "corpus.yaml"
    fichier.write_text(
        yaml.safe_dump(
            {
                "corpus_id": "c-pdf",
                "path": "docs",
                "lang": "fr",
                "volatility": "low",
                "license": "CC-BY-4.0",
                "publishable": True,
            }
        ),
        encoding="utf-8",
    )
    return fichier


def test_enregistre_avec_formats_et_version():
    registry.discover()
    cls = registry.get("parser", "pdf_text")
    assert cls is PdfTextParser
    assert cls.formats == {"pdf"}
    assert isinstance(cls.version, str)


def test_trois_pages_ancrees_dans_l_ordre():
    raw = _pdf(["Alpha un", "Beta deux", "Gamma trois"])
    doc = PdfTextParser().parse("docs/r.pdf", raw, "fr", DocMeta())
    did = sha16_bytes(raw)
    assert doc.doc_id == did and doc.format == "pdf"
    assert [b.anchor_id for b in doc.blocks] == [f"{did}#p1", f"{did}#p2", f"{did}#p3"]
    assert [b.text for b in doc.blocks] == ["Alpha un", "Beta deux", "Gamma trois"]
    assert list(doc.anchors) == [f"{did}#p{n}" for n in (1, 2, 3)]
    assert [a.page for a in doc.anchors.values()] == [1, 2, 3]


def test_page_sans_texte_garde_son_ancrage():
    raw = _pdf(["Alpha", "", "Gamma"])
    doc = PdfTextParser().parse("docs/r.pdf", raw, "fr", DocMeta())
    ancre = f"{doc.doc_id}#p2"
    assert ancre in doc.anchors and doc.anchors[ancre].page == 2
    assert all(b.anchor_id != ancre for b in doc.blocks)


def test_pdf_tronque_leve_value_error():
    with pytest.raises(ValueError):
        PdfTextParser().parse("docs/x.pdf", _pdf(["Alpha"])[:40], "fr", DocMeta())


def test_ingestion_ignore_le_pdf_illisible_et_resout_les_pages(
    tmp_path: Path, wl_home: Path, caplog: pytest.LogCaptureFixture
):
    fichier = _corpus(
        tmp_path,
        {
            "registre.pdf": _pdf(["Un", "Deux", "Trois"]),
            "casse.pdf": _pdf(["Alpha"])[:40],
            "note.md": b"# Titre\n\nTexte.\n",
        },
    )
    with caplog.at_level(logging.WARNING):
        parse = ingest(declare(fichier))
    assert [d.source_path for d in parse.documents] == ["note.md", "registre.pdf"]
    assert "casse.pdf" in caplog.text
    pdf = parse.documents[1]
    assert parse.resolve("registre.pdf", 2, ()) == f"{pdf.doc_id}#p2"
    assert parse.resolve("registre.pdf", 9, ()) is None
    assert parse.anchor_text(f"{pdf.doc_id}#p2") == "Deux"


def test_cache_versionne_pour_le_pdf(tmp_path: Path, wl_home: Path, monkeypatch):
    fichier = _corpus(tmp_path, {"r.pdf": _pdf(["Un"])})
    ingest(declare(fichier))
    appels: list[str] = []
    origine = PdfTextParser.parse

    def espion(self, *a, **k):
        appels.append("x")
        return origine(self, *a, **k)

    monkeypatch.setattr(PdfTextParser, "parse", espion)
    ingest(declare(fichier))
    assert appels == []  # servi par le cache
    monkeypatch.setattr(PdfTextParser, "version", "2")
    ingest(declare(fichier))
    assert appels == ["x"]  # version changée : reparsé


def test_auto_accepte_un_corpus_avec_pdf():
    assert parsers_par_format(["pdf", "markdown"]) == {"pdf": "pdf_text", "markdown": "markdown"}


def test_normalise_cesure_ligatures_et_controles():
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    pdf.add_page()
    pdf.multi_cell(w=80, text="Le regle-\nment de la salle\nreste en vigueur.")
    raw = bytes(pdf.output())
    doc = PdfTextParser().parse("docs/r.pdf", raw, "fr", DocMeta())
    assert [b.text for b in doc.blocks] == ["Le reglement de la salle\nreste en vigueur."]
    assert normaliser("eﬃcace ﬂeur bleue\x00\x07 régle\x02ment\r\n  fin  ") == (
        "efficace fleur bleue réglement\nfin"
    )


def test_pdf_chiffre_leve_value_error():
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    pdf.add_page()
    pdf.cell(text="Secret")
    pdf.set_encryption(owner_password="o", user_password="u")
    with pytest.raises(ValueError, match="illisible"):
        PdfTextParser().parse("docs/s.pdf", bytes(pdf.output()), "fr", DocMeta())


def test_document_ferme_meme_en_cas_d_erreur(monkeypatch):
    import pypdfium2 as pdfium

    fermes: list[int] = []
    origine = pdfium.PdfDocument.close

    def espion(self):
        fermes.append(1)
        return origine(self)

    monkeypatch.setattr(pdfium.PdfDocument, "close", espion)
    PdfTextParser().parse("docs/r.pdf", _pdf(["Un", "Deux"]), "fr", DocMeta())
    assert fermes == [1]

    def casse(self, index):
        raise pdfium.PdfiumError("page illisible")

    monkeypatch.setattr(pdfium.PdfDocument, "get_page", casse)
    with pytest.raises(ValueError, match="page 1"):
        PdfTextParser().parse("docs/r.pdf", _pdf(["Un"]), "fr", DocMeta())
    assert fermes == [1, 1]


def test_resolve_avec_le_chemin_de_l_ac(tmp_path: Path, wl_home: Path):
    """AC : `resolve("docs/registre.pdf", …)` quand `docs/` est sous la racine du Corpus."""
    racine = tmp_path / "racine"
    fichier = _corpus(racine, {"registre.pdf": _pdf(["Un", "Deux", "Trois"])})
    contenu = yaml.safe_load(fichier.read_text(encoding="utf-8"))
    contenu["path"] = "."
    fichier.write_text(yaml.safe_dump(contenu), encoding="utf-8")
    parse = ingest(declare(fichier))
    pdf = next(d for d in parse.documents if d.format == "pdf")
    assert pdf.source_path == "docs/registre.pdf"
    assert parse.resolve("docs/registre.pdf", 2, ()) == f"{pdf.doc_id}#p2"
    assert parse.resolve("docs/registre.pdf", 9, ()) is None
