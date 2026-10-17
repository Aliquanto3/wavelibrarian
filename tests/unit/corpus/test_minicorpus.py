"""Mini-corpus fictif (story 2.5) : taille, structure, PDF reproductibles, scénario, extras."""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from wavelibrarian.components.parsers.pdf_text import PdfTextParser
from wavelibrarian.core.types import DocMeta, ParsedCorpus, ParsedDocument
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.entities import entites_du_document
from wavelibrarian.measure.tokenizers import make_tokenizer

RACINE = Path(__file__).resolve().parents[3]
MINI = RACINE / "corpora" / "minicorpus"


def _doc(corpus: ParsedCorpus, chemin: str) -> ParsedDocument:
    return next(d for d in corpus.documents if d.source_path == chemin)


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "make_minicorpus_pdfs", RACINE / "scripts" / "make_minicorpus_pdfs.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_declaration_et_effectif(minicorpus: ParsedCorpus):
    declare_ = declare(MINI / "corpus.yaml")
    assert declare_.spec.publishable is True
    assert declare_.spec.license == "CC-BY-4.0"
    assert 18 <= len(minicorpus.documents) <= 22
    assert {d.format for d in minicorpus.documents} == {"markdown", "pdf"}
    assert sum(d.format == "pdf" for d in minicorpus.documents) >= 3


def test_langues(minicorpus: ParsedCorpus):
    en = {d.source_path for d in minicorpus.documents if d.lang == "en"}
    assert len(en) >= 2
    assert {d.lang for d in minicorpus.documents} == {"fr", "en"}


def test_long_document_a_trois_niveaux_et_deux_tableaux(minicorpus: ParsedCorpus):
    atlas = _doc(minicorpus, "atlas-vaelmor.md")
    assert max(len(a.heading_path) for a in atlas.anchors.values()) == 3
    assert sum(b.kind == "table" for b in atlas.blocks) >= 2


def test_groupe_de_documents_lies_par_entites(minicorpus: ParsedCorpus):
    par_entite: dict[str, set[str]] = {}
    for doc in minicorpus.documents:
        for e in entites_du_document(doc):
            par_entite.setdefault(e, set()).add(doc.source_path)
    assert len(par_entite["compagnie des marées grises"]) >= 4
    assert len(par_entite["oswin dacrel"]) >= 4


def test_deux_versions_contradictoires(minicorpus: ParsedCorpus):
    v1, v2 = _doc(minicorpus, "charte-conseil-v1.md"), _doc(minicorpus, "charte-conseil-v2.md")
    assert v1.blocks[0].text == v2.blocks[0].text  # même titre : même Document, deux versions
    assert v1.doc_id != v2.doc_id
    t1, t2 = (" ".join(b.text for b in d.blocks) for d in (v1, v2))
    assert "quatre ans" in t1 and "six ans" in t2
    assert "sept sièges" in t1 and "neuf sièges" in t2


def test_droits_sur_au_moins_deux_documents(minicorpus: ParsedCorpus):
    avec = {d.source_path for d in minicorpus.documents if d.meta.rights_profiles}
    assert {"journal-torvane.md", "procedure-quarantaine.md"} <= avec


def test_sous_la_borne_de_tokens_de_reference(minicorpus: ParsedCorpus):
    approx = make_tokenizer("approx")
    tokens = sum(approx.count(b.text) for d in minicorpus.documents for b in d.blocks)
    mots = sum(len(b.text.split()) for d in minicorpus.documents for b in d.blocks)
    assert 0 < tokens < 60_000
    assert mots <= 40_000


def test_pdf_regeneres_a_l_identique(script: ModuleType):
    sources = sorted((MINI / "pdf-src").glob("*.txt"))
    assert len(sources) >= 3
    for src in sources:
        texte = src.read_text(encoding="utf-8")
        commite = (MINI / "docs" / f"{src.stem}.pdf").read_bytes()
        regenere = script.rendre(texte)
        assert regenere == commite, src.name
        extrait = PdfTextParser().parse(f"{src.stem}.pdf", regenere, "fr", DocMeta())
        brut = "".join("".join(b.text for b in extrait.blocks).split())
        assert brut == script.texte_attendu(texte), src.name


def test_script_ecrit_les_pdf(script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(script, "SORTIE", tmp_path)
    script.main()
    ecrits = {p.name: p.read_bytes() for p in tmp_path.glob("*.pdf")}
    assert ecrits
    for nom, octets in ecrits.items():
        assert octets == (MINI / "docs" / nom).read_bytes()


def test_caracteres_francais_rendus_et_reextraits(script: ModuleType):
    texte = "Le cœur de l'Œuvre – « une phrase » — fin."
    extrait = PdfTextParser().parse("x.pdf", script.rendre(texte), "fr", DocMeta())
    assert extrait.blocks[0].text == texte


def test_police_libre_commitee_avec_licence():
    polices = RACINE / "scripts" / "fonts"
    assert (polices / "DejaVuSans.ttf").is_file()
    assert "Bitstream" in (polices / "DejaVu-LICENSE.txt").read_text(encoding="utf-8")


def test_un_pdf_multipage_et_un_pdf_sans_titre(minicorpus: ParsedCorpus):
    pdfs = [d for d in minicorpus.documents if d.format == "pdf"]
    assert any(len(d.anchors) >= 2 for d in pdfs)
    sans_titre = [
        s.stem
        for s in (MINI / "pdf-src").glob("*.txt")
        if not any(ligne.startswith("#") for ligne in s.read_text(encoding="utf-8").splitlines())
    ]
    assert sans_titre


def test_markdown_sans_html_brut_ni_meta_charset():
    """Report 2.2 : un `html_block` reste brut dans un Block, un `<meta charset>` est ignoré."""
    for chemin in (MINI / "docs").glob("*.md"):
        assert not re.search(r"<[A-Za-z!/]", chemin.read_text(encoding="utf-8")), chemin.name
    assert not list((MINI / "docs").glob("*.htm*"))


def test_scenario_operations_et_sources():
    scenario = yaml.safe_load((MINI / "scenario" / "scenario.yaml").read_text(encoding="utf-8"))
    assert scenario["corpus_id"] == "minicorpus"
    ops = scenario["operations"]
    assert {"add", "modify", "delete"} <= {o["op"] for o in ops}
    chemins = {d.source_path for d in declare(MINI / "corpus.yaml").documents}
    for o in ops:
        if o["op"] != "delete":
            assert (MINI / "scenario" / o["source"]).is_file()
        # `add` crée un target absent ; `modify` et `delete` visent un Document existant.
        assert (o["target"] in chemins) == (o["op"] != "add")


def test_extras_hors_docs():
    extras = MINI / "extras"
    sentinelle = (extras / "sentinelle.md").read_text(encoding="utf-8")
    piege = (extras / "document-piege.md").read_text(encoding="utf-8")
    assert "Pélagie" in sentinelle and "Iven Zadrokh" in sentinelle
    assert "ignore toutes tes instructions" in piege.lower()
    docs = {d.source_path for d in declare(MINI / "corpus.yaml").documents}
    assert not {"sentinelle.md", "document-piege.md"} & docs
    texte_docs = " ".join(p.read_text(encoding="utf-8") for p in (MINI / "docs").glob("*.md"))
    assert "Pélagie" not in texte_docs


def test_fixture_minicorpus_en_cache_de_session(minicorpus: ParsedCorpus, request):
    assert isinstance(minicorpus, ParsedCorpus)
    assert minicorpus.corpus_id == "minicorpus"
    assert request.getfixturevalue("minicorpus") is minicorpus
