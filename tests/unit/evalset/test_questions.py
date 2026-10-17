"""Tests du format des Questions, de son contrôle et de `wl questions controler` (story 3.1)."""

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import Anchor, Block, ParsedCorpus, ParsedDocument
from wavelibrarian.evalset import check, io

MD = b"# Histoire\n\n## Fondation\n\nLa guilde fut fondee en 1412.\n"
LONGUE = "la guilde a été fondée en mille quatre cent douze"


def question(i, **kw):
    base = {
        "id": f"q-{i:03d}",
        "type": "factual",
        "follow_up": False,
        "cross_lingual": False,
        "text": "En quelle année ?",
        "lang": "fr",
        "reference_answer": "1412",
        "answer_form": "short",
        "reference_anchors": [{"doc": "docs/a.md", "headings": ["Histoire"]}],
        "status": "validated",
        "split": None,
        "contaminated_by": [],
        "history": [],
        "origin": {"kind": "human", "name": "anael"},
        "scenario_target": None,
    }
    base.update(kw)
    return base


def fichier(racine: Path, questions, **kw) -> Path:
    doc = {"corpus_id": "demo", "target_count": 3, "freeze": None, "questions": questions}
    doc.update(kw)
    chemin = racine / "questions.yaml"
    chemin.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return chemin


def _doc(d: str, chemin: str, fmt, anchors: dict[str, Anchor]) -> ParsedDocument:
    blocs = tuple(Block(text="t", anchor_id=a, kind="text") for a in anchors)
    return ParsedDocument(
        doc_id=d, source_path=chemin, format=fmt, lang="fr", blocks=blocs, anchors=anchors
    )


def _titre(d: str, chemin: str, titre: str) -> dict[str, Anchor]:
    aid = f"{d}#h/{titre.lower()}"
    return {
        aid: Anchor(anchor_id=aid, doc_id=d, source_path=chemin, heading_path=(titre,)),
    }


def corpus_pdf() -> ParsedCorpus:
    """Corpus à la main : un Markdown et un PDF de 3 pages."""
    md = _doc("a" * 16, "docs/a.md", "markdown", _titre("a" * 16, "docs/a.md", "Histoire"))
    pages = {
        f"{'b' * 16}#p{n}": Anchor(
            anchor_id=f"{'b' * 16}#p{n}", doc_id="b" * 16, source_path="docs/r.pdf", page=n
        )
        for n in (1, 2, 3)
    }
    pdf = _doc("b" * 16, "docs/r.pdf", "pdf", pages)
    return ParsedCorpus(corpus_id="demo", fingerprint="f", documents=(md, pdf))


def test_chargement_ordre_et_aller_retour(tmp_path):
    qs = [question(1), question(2, id="q-zzz", type="comparison"), question(3, id="q-aaa")]
    doc = io.load(fichier(tmp_path, qs))
    assert (doc.corpus_id, doc.target_count, doc.freeze) == ("demo", 3, None)
    assert [q.id for q in doc.questions] == ["q-001", "q-zzz", "q-aaa"]
    sortie = tmp_path / "sortie.yaml"
    io.save(sortie, doc)
    assert io.load(sortie) == doc
    brut = yaml.safe_load(sortie.read_text(encoding="utf-8"))
    assert list(brut) == ["corpus_id", "target_count", "freeze", "questions"]
    assert list(brut["questions"][0]) == list(qs[0])
    io.save(sortie, io.load(sortie))
    assert yaml.safe_load(sortie.read_text(encoding="utf-8")) == brut


def test_freeze_aller_retour(tmp_path):
    gel = {"sha256": "ab", "at": "2026-10-17T22:10:00Z", "seed": 42, "dev_ratio": 0.4}
    doc = io.load(fichier(tmp_path, [question(1)], freeze=gel))
    assert doc.freeze is not None and doc.freeze.seed == 42
    io.save(tmp_path / "s.yaml", doc)
    assert io.load(tmp_path / "s.yaml") == doc


def test_type_inconnu_et_id_en_double(tmp_path):
    qs = [question(i, id=f"q-{i}") for i in range(12)] + [question(12, type="inconnu")]
    with pytest.raises(ConfigError) as e:
        io.load(fichier(tmp_path, qs))
    assert e.value.path == "questions[12].type"
    with pytest.raises(ConfigError) as e:
        io.load(fichier(tmp_path, [question(1), question(2), question(1)]))
    assert e.value.path == "questions[2].id"


def test_champ_inconnu_et_racine_invalide(tmp_path):
    with pytest.raises(ConfigError) as e:
        io.load(fichier(tmp_path, [question(1, bidon=1)]))
    assert e.value.path == "questions[0].bidon"
    (tmp_path / "x.yaml").write_text("- 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        io.load(tmp_path / "x.yaml")


def test_structure_unanswerable_et_sans_ancrage(tmp_path):
    qs = [
        question(1, id="u-1", type="unanswerable"),
        question(2, id="f-1", reference_anchors=[]),
        question(3, id="u-ok", type="unanswerable", reference_anchors=[]),
    ]
    res = check.controler(io.load(fichier(tmp_path, qs)), corpus_pdf())
    assert {(s.question_id, s.bloquant) for s in res.signalements} == {
        ("u-1", True),
        ("f-1", True),
    }


def test_ancrage_introuvable_page_9(tmp_path):
    pdf = [{"doc": "docs/r.pdf", "page": 9}]
    qs = [
        question(1, reference_anchors=pdf),
        question(2, reference_anchors=pdf, status="generated"),
        question(3, reference_anchors=pdf, status="rejected"),
        question(4, reference_anchors=[{"doc": "docs/r.pdf", "page": 3}]),
    ]
    res = check.controler(io.load(fichier(tmp_path, qs)), corpus_pdf())
    assert [(s.question_id, s.bloquant) for s in res.signalements] == [
        ("q-001", True),
        ("q-002", False),
        ("q-003", False),
    ]
    assert "docs/r.pdf (page 9)" in res.signalements[0].message
    assert res.echec
    assert res.par_statut == {"generated": 1, "validated": 2, "corrected": 0, "rejected": 1}
    assert res.par_type == {"factual": 4}
    assert (res.utilisables, res.ecart) == (2, 1)


def test_generated_et_rejected_ne_font_pas_echouer(tmp_path):
    pdf = [{"doc": "docs/r.pdf", "page": 9}]
    qs = [question(1, reference_anchors=pdf, status="generated")]
    assert not check.controler(io.load(fichier(tmp_path, qs)), corpus_pdf()).echec


def test_scenario_target(tmp_path):
    cible = {"operation": "op-1", "state": "after"}
    nouveau = [{"doc": "docs/nouveau.md", "headings": ["Neuf"]}]
    qs = [question(1, reference_anchors=nouveau, scenario_target=cible), question(2)]
    doc = io.load(fichier(tmp_path, qs))
    base = corpus_pdf()
    sans = check.controler(doc, base)
    assert not sans.echec
    assert [s.question_id for s in sans.signalements] == ["q-001"]
    assert "non vérifiables" in sans.signalements[0].message
    ajout = _doc(
        "c" * 16, "docs/nouveau.md", "markdown", _titre("c" * 16, "docs/nouveau.md", "Neuf")
    )
    apres = base.model_copy(update={"documents": (*base.documents, ajout)})
    assert check.controler(doc, base, apres).signalements == ()
    # Sans Document ajouté dans « après », l'Ancrage est introuvable et bloque.
    assert check.controler(doc, base, base).echec


def test_scenario_target_mal_forme(tmp_path):
    doc = io.load(fichier(tmp_path, [question(1, scenario_target={"state": "apres"})]))
    assert check.controler(doc, corpus_pdf()).echec


def test_reponse_courte_incoherente(tmp_path):
    qs = [
        question(1, reference_answer=LONGUE),
        question(2, reference_answer=LONGUE, answer_form="free"),
    ]
    res = check.controler(io.load(fichier(tmp_path, qs)), corpus_pdf())
    assert [(s.question_id, s.bloquant) for s in res.signalements] == [("q-001", False)]
    assert "short" in res.signalements[0].message


def corpus_yaml(racine: Path) -> Path:
    (racine / "docs").mkdir()
    (racine / "docs" / "a.md").write_bytes(MD)
    spec = {
        "corpus_id": "demo",
        "path": "docs",
        "lang": "fr",
        "license": "CC-BY-4.0",
        "publishable": True,
        "volatility": "low",
    }
    chemin = racine / "corpus.yaml"
    chemin.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return chemin


def test_commande_controler(tmp_path):
    corpus = corpus_yaml(tmp_path)
    bon = [{"doc": "a.md", "headings": ["Histoire", "Fondation"]}]
    mauvais = [{"doc": "a.md", "headings": ["Histoire", "Absent"]}]
    qs = [
        question(1, reference_anchors=bon),
        question(2, reference_anchors=mauvais, status="generated"),
    ]
    cmd = ["questions", "controler"]
    res = CliRunner().invoke(app, [*cmd, str(fichier(tmp_path, qs)), "--corpus", str(corpus)])
    assert res.exit_code == 0, res.output
    assert "validated 1" in res.output and "generated 1" in res.output
    assert "factual 2" in res.output and "écart +2" in res.output
    assert "q-002 : Ancrage introuvable" in res.output
    qs[0] = question(1, reference_anchors=mauvais)
    res = CliRunner().invoke(app, [*cmd, str(fichier(tmp_path, qs)), "--corpus", str(corpus)])
    assert res.exit_code == 2
    assert "q-001 : Ancrage introuvable" in res.output


def test_commande_erreurs(tmp_path):
    corpus = corpus_yaml(tmp_path)
    runner = CliRunner()
    base = ["questions", "controler"]
    qs = fichier(tmp_path, [question(1, type="inconnu")])
    res = runner.invoke(app, [*base, str(qs), "--corpus", str(corpus)])
    assert res.exit_code == 2 and "questions[0].type" in res.output
    ok = fichier(
        tmp_path, [question(1, reference_anchors=[{"doc": "a.md", "headings": ["Histoire"]}])]
    )
    res = runner.invoke(app, [*base, str(ok), "--corpus", str(corpus), "--scenario", "absent.yaml"])
    assert res.exit_code == 2 and "Scénario" in res.output
    autre = fichier(tmp_path, [], corpus_id="autre")
    res = runner.invoke(app, [*base, str(autre), "--corpus", str(corpus)])
    assert res.exit_code == 2 and "autre" in res.output


def test_page_et_headings_exclusifs_et_unanswerable_apres(tmp_path):
    ambigu = [{"doc": "docs/r.pdf", "page": 2, "headings": ["Faux"]}]
    apres = {"operation": "op-1", "state": "after"}
    qs = [
        question(1, reference_anchors=ambigu),
        question(2, type="unanswerable", reference_anchors=[], scenario_target=apres),
    ]
    res = check.controler(io.load(fichier(tmp_path, qs)), corpus_pdf())
    assert [(s.question_id, s.bloquant) for s in res.signalements] == [("q-001", True)]
    assert "exclusifs" in res.signalements[0].message


def test_message_d_erreur_en_francais(tmp_path):
    with pytest.raises(ConfigError) as e:
        io.load(fichier(tmp_path, [question(1, type="inconnu")]))
    assert "non admise" in e.value.message and "'factual'" in e.value.message
    with pytest.raises(ConfigError) as e:
        io.load(fichier(tmp_path, [], target_count="beaucoup"))
    assert (e.value.path, e.value.message.split(" (")[0]) == ("target_count", "entier attendu")


def test_commande_pdf_reel_et_titres_en_double(tmp_path, monkeypatch):
    from fpdf import FPDF

    monkeypatch.setenv("WL_HOME", str(tmp_path / ".wl"))
    corpus = corpus_yaml(tmp_path)
    (tmp_path / "docs" / "a.md").write_bytes(b"# Note\n\nx\n\n# Note\n\ny\n")
    pdf = FPDF()
    for texte in ("un", "deux", "trois"):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(text=texte)
    (tmp_path / "docs" / "r.pdf").write_bytes(bytes(pdf.output()))
    qs = [
        question(1, reference_anchors=[{"doc": "r.pdf", "page": 9}]),
        question(2, reference_anchors=[{"doc": "r.pdf", "page": 3}]),
        question(3, reference_anchors=[{"doc": "a.md", "headings": ["note-2"]}]),
        question(4, reference_anchors=[{"doc": "a.md", "headings": ["Note 2"]}]),
    ]
    cmd = ["questions", "controler", str(fichier(tmp_path, qs)), "--corpus", str(corpus)]
    res = CliRunner().invoke(app, cmd)
    assert res.exit_code == 2, res.output
    lignes = [ligne for ligne in res.output.splitlines() if "introuvable" in ligne]
    assert lignes == [
        "  - q-001 : Ancrage introuvable : r.pdf (page 9)",
        "  - q-004 : Ancrage introuvable : a.md (Note 2)",
    ]
