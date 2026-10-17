"""Application d'un Scénario de mise à jour à un Corpus (story 2.6)."""

import hashlib
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import ParsedCorpus, ParsedDocument
from wavelibrarian.corpus import scenario as sc

RACINE = Path(__file__).resolve().parents[3]
MINI = RACINE / "corpora" / "minicorpus"
SCENARIO = MINI / "scenario" / "scenario.yaml"


def _doc(corpus: ParsedCorpus, chemin: str) -> ParsedDocument:
    return next(d for d in corpus.documents if d.source_path == chemin)


def _empreintes(dossier: Path) -> dict[str, str]:
    return {
        p.relative_to(dossier).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(dossier.rglob("*"))
        if p.is_file()
    }


def _ecrire(tmp_path: Path, operations: list[dict], **kw) -> Path:
    (tmp_path / "up").mkdir(exist_ok=True)
    (tmp_path / "up" / "x.md").write_text("# Nouveau\n\nTexte neuf.\n", encoding="utf-8")
    doc = {"scenario_id": "s", "corpus_id": "minicorpus", "operations": operations, **kw}
    chemin = tmp_path / "scenario.yaml"
    chemin.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return chemin


def test_chargement_ordre_et_cibles(minicorpus):
    charge = sc.charger(SCENARIO, minicorpus)
    ops = charge.scenario.operations
    assert [(o.id, o.op, o.target) for o in ops] == [
        ("op-1", "add", "chronique-1415.md"),
        ("op-2", "modify", "bulletin-maree.md"),
        ("op-3", "delete", "note-obsolete.md"),
    ]
    assert charge.dossier == SCENARIO.parent.resolve()
    assert (charge.dossier / str(ops[0].source)).is_file()


@pytest.mark.parametrize(
    ("operations", "chemin"),
    [
        (
            [{"id": "a", "op": "modify", "source": "up/x.md", "target": "absent.md"}],
            "operations[0]",
        ),
        (
            [
                {"id": "a", "op": "delete", "target": "note-obsolete.md"},
                {"id": "b", "op": "delete", "target": "inconnu.md"},
            ],
            "operations[1]",
        ),
        ([{"id": "a", "op": "add", "source": "up/manque.md", "target": "z.md"}], "operations[0]"),
        (
            [{"id": "a", "op": "add", "source": "up/x.md", "target": "bulletin-maree.md"}],
            "operations[0]",
        ),
        ([{"id": "a", "op": "add", "source": "up/x.md", "target": "z.txt"}], "operations[0]"),
        ([{"id": "a", "op": "add", "target": "z.md"}], "operations[0]"),
        (
            [{"id": "a", "op": "delete", "source": "up/x.md", "target": "note-obsolete.md"}],
            "operations[0]",
        ),
    ],
)
def test_erreurs_au_chemin_de_l_operation(tmp_path, minicorpus, operations, chemin):
    with pytest.raises(ConfigError) as e:
        sc.charger(_ecrire(tmp_path, operations), minicorpus)
    assert e.value.path.startswith(chemin)


def test_corpus_id_et_identifiants(tmp_path, minicorpus):
    with pytest.raises(ConfigError) as e:
        sc.charger(
            _ecrire(tmp_path, [{"id": "a", "op": "delete", "target": "x"}], corpus_id="autre"),
            minicorpus,
        )
    assert e.value.path == "corpus_id"
    doubles = [
        {"id": "a", "op": "delete", "target": "note-obsolete.md"},
        {"id": "a", "op": "add", "source": "up/x.md", "target": "z.md"},
    ]
    with pytest.raises(ConfigError) as e:
        sc.charger(_ecrire(tmp_path, doubles), minicorpus)
    assert e.value.path == "operations[1].id"


def test_application_au_minicorpus(minicorpus):
    avant = minicorpus.model_dump()
    ancien_bulletin = _doc(minicorpus, "bulletin-maree.md")
    supprime = _doc(minicorpus, "note-obsolete.md")
    changement, apres = sc.appliquer_fichier(minicorpus, SCENARIO)

    assert [d.source_path for d in changement.added] == ["chronique-1415.md"]
    assert changement.removed == (supprime.doc_id,)
    assert len(changement.modified) == 1
    ancien_id, nouveau = changement.modified[0]
    assert ancien_id == ancien_bulletin.doc_id
    assert nouveau.source_path == "bulletin-maree.md" and nouveau.doc_id != ancien_id

    assert "note-obsolete.md" not in {d.source_path for d in apres.documents}
    assert "chronique-1415.md" in {d.source_path for d in apres.documents}
    modifie = _doc(apres, "bulletin-maree.md")
    assert modifie.doc_id == nouveau.doc_id
    assert (modifie.lang, modifie.meta) == (ancien_bulletin.lang, ancien_bulletin.meta)
    assert _doc(apres, "chronique-1415.md").lang == "fr"
    assert all(a.source_path == "bulletin-maree.md" for a in modifie.anchors.values())
    assert len(apres.documents) == len(minicorpus.documents)
    assert [d.source_path for d in apres.documents] == sorted(
        d.source_path for d in apres.documents
    )

    assert apres.fingerprint != minicorpus.fingerprint
    assert minicorpus.model_dump() == avant  # l'original est inchangé


def test_deterministe_et_docs_intacts(minicorpus):
    docs = MINI / "docs"
    scen = MINI / "scenario"
    avant_docs, avant_scen = _empreintes(docs), _empreintes(scen)
    un = sc.appliquer_fichier(minicorpus, SCENARIO)
    deux = sc.appliquer_fichier(minicorpus, SCENARIO)
    assert un[0] == deux[0] and un[1] == deux[1]
    assert un[1].fingerprint == deux[1].fingerprint
    assert _empreintes(docs) == avant_docs and _empreintes(scen) == avant_scen


def test_changement_net_ajout_puis_suppression(tmp_path, minicorpus):
    ops = [
        {"id": "a", "op": "add", "source": "up/x.md", "target": "z.md"},
        {"id": "b", "op": "delete", "target": "z.md"},
    ]
    changement, apres = sc.appliquer_fichier(minicorpus, _ecrire(tmp_path, ops))
    assert (changement.added, changement.removed, changement.modified) == ((), (), ())
    assert apres.fingerprint == minicorpus.fingerprint


def test_contenu_identique_a_un_document_existant_refuse(tmp_path, minicorpus):
    copie = MINI / "docs" / "note-obsolete.md"
    (tmp_path / "up").mkdir()
    (tmp_path / "up" / "x.md").write_bytes(copie.read_bytes())
    doc = {
        "scenario_id": "s",
        "corpus_id": "minicorpus",
        "operations": [{"id": "a", "op": "add", "source": "up/x.md", "target": "z.md"}],
    }
    chemin = tmp_path / "scenario.yaml"
    chemin.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        sc.appliquer_fichier(minicorpus, chemin)
    assert e.value.path == "operations[0].source"


def test_commande_controler_scenario_de_bout_en_bout(tmp_path, monkeypatch):
    monkeypatch.setenv("WL_HOME", str(tmp_path / ".wl"))
    ancre = {"doc": "chronique-1415.md", "headings": ["Chronique de l'an 1415"]}
    question = {
        "id": "q-001",
        "type": "factual",
        "follow_up": False,
        "cross_lingual": False,
        "text": "Que raconte la chronique ?",
        "lang": "fr",
        "reference_answer": "Le nouveau phare",
        "answer_form": "short",
        "reference_anchors": [ancre],
        "status": "validated",
        "split": None,
        "contaminated_by": [],
        "history": [],
        "origin": {"kind": "human", "name": "test"},
        "scenario_target": {"operation": "op-1", "state": "after"},
    }
    modele = tmp_path / "q.yaml"
    modele.write_text(
        yaml.safe_dump(
            {"corpus_id": "minicorpus", "target_count": 1, "questions": [question]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    cmd = ["questions", "controler", str(modele), "--corpus", str(MINI / "corpus.yaml")]
    sans = CliRunner().invoke(app, cmd)
    assert "Ancrages non vérifiables sans --scenario" in sans.output
    avec = CliRunner().invoke(app, [*cmd, "--scenario", str(SCENARIO)])
    assert avec.exit_code == 0, avec.output
    assert "introuvable" not in avec.output and "non vérifiables" not in avec.output
    assert "Contrôle réussi" in avec.output
