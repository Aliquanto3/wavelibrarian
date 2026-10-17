"""Tests de la déclaration d'un Corpus (story 2.1)."""

import logging
import subprocess
from pathlib import Path

import pytest
import yaml

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16_bytes
from wavelibrarian.corpus.declare import declare

BASE = {
    "corpus_id": "demo",
    "path": "docs",
    "lang": "fr",
    "license": "CC-BY-4.0",
    "publishable": True,
    "volatility": "low",
}


def _corpus(racine: Path, **extra: object) -> Path:
    docs = racine / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for nom, contenu in {
        "a.md": b"# A\n",
        "b.txt": b"bb",
        "c.html": b"<p>c</p>",
        "d.pdf": b"%PDF-1.4 d",
        "e.docx": b"docx",
    }.items():
        (docs / nom).write_bytes(contenu)
    fichier = racine / "corpus.yaml"
    fichier.write_text(yaml.safe_dump({**BASE, **extra}), encoding="utf-8")
    return fichier


def test_quatre_documents_tries_et_docx_ignore(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    fichier = _corpus(tmp_path)
    with caplog.at_level(logging.WARNING):
        c = declare(fichier)
    assert [d.source_path for d in c.documents] == ["a.md", "b.txt", "c.html", "d.pdf"]
    assert c.documents[0].doc_id == sha16_bytes(b"# A\n")
    assert [d.format for d in c.documents] == ["markdown", "text", "html", "pdf"]
    assert c.formats == ("html", "markdown", "pdf", "text")
    assert any("e.docx" in r.message for r in caplog.records)


def test_renommage_conserve_doc_id(tmp_path: Path):
    fichier = _corpus(tmp_path)
    avant = {d.source_path: d.doc_id for d in declare(fichier).documents}
    (tmp_path / "docs" / "a.md").rename(tmp_path / "docs" / "z.md")
    apres = {d.source_path: d.doc_id for d in declare(fichier).documents}
    assert "a.md" not in apres
    assert apres["z.md"] == avant["a.md"]


def test_metadonnees_par_document(tmp_path: Path):
    meta = {"lang": "en", "sensitivity": "interne", "rights_profiles": ["rh"]}
    fichier = _corpus(tmp_path, documents={"a.md": meta, "docs/b.txt": {"lang": "de"}})
    docs = {d.source_path: d for d in declare(fichier).documents}
    assert docs["a.md"].lang == "en"
    assert docs["a.md"].meta.sensitivity == "interne"
    assert docs["a.md"].meta.rights_profiles == ("rh",)
    assert docs["b.txt"].lang == "de"  # clé préfixée par `path`, écriture de l'exemple du contrat
    assert docs["c.html"].lang == "fr"


def test_cle_inconnue_et_mal_typee(tmp_path: Path):
    with pytest.raises(ConfigError) as e:
        declare(_corpus(tmp_path, couleur="rouge"))
    assert e.value.path == "couleur"
    with pytest.raises(ConfigError) as e:
        declare(_corpus(tmp_path, documents={"a.md": {"langue": "en"}}))
    assert e.value.path == "documents.a.md.langue"
    with pytest.raises(ConfigError) as e:
        declare(_corpus(tmp_path, publishable="peut-être"))
    assert e.value.path == "publishable"
    with pytest.raises(ConfigError) as e:
        declare(_corpus(tmp_path, documents={"absent.md": {"lang": "en"}}))
    assert e.value.path == "documents.absent.md"


@pytest.mark.parametrize("cid", ["Demo", "a_b", "é", "a b", ""])
def test_corpus_id_refuse(tmp_path: Path, cid: str):
    with pytest.raises(ConfigError) as e:
        declare(_corpus(tmp_path, corpus_id=cid))
    assert e.value.path == "corpus_id"


def test_dossier_introuvable_et_doublon(tmp_path: Path):
    with pytest.raises(ConfigError) as e:
        declare(_corpus(tmp_path, path="autre"))
    assert e.value.path == "path"
    fichier = _corpus(tmp_path)
    (tmp_path / "docs" / "copie.md").write_bytes(b"# A\n")
    with pytest.raises(ConfigError, match="contenu identique"):
        declare(fichier)


def _depot(racine: Path) -> None:
    subprocess.run(["git", "init", "-q", str(racine)], check=True)  # noqa: S603, S607


def test_non_publiable_dans_depot_non_ignore_refuse(tmp_path: Path):
    _depot(tmp_path)
    fichier = _corpus(tmp_path, publishable=False)
    with pytest.raises(ConfigError, match="hors du dépôt ou dans un dossier ignoré") as e:
        declare(fichier)
    assert e.value.path == "path"


def test_non_publiable_dossier_ignore_accepte(tmp_path: Path):
    _depot(tmp_path)
    (tmp_path / ".gitignore").write_text("docs/\n", encoding="utf-8")
    assert len(declare(_corpus(tmp_path, publishable=False)).documents) == 4


def test_non_publiable_hors_depot_avertit(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    fichier = _corpus(tmp_path, publishable=False)
    with caplog.at_level(logging.WARNING):
        assert len(declare(fichier).documents) == 4
    assert any("vérification des droits sautée" in r.message for r in caplog.records)


def test_publiable_dans_depot_accepte(tmp_path: Path):
    _depot(tmp_path)
    assert len(declare(_corpus(tmp_path)).documents) == 4
