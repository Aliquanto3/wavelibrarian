"""Gel, `verify_frozen`, `select_questions` et `wl questions geler` (story 3.6)."""

import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError, ValidationFailed
from wavelibrarian.core.ids import canonical_json
from wavelibrarian.evalset import freeze, io

TYPES = ("factual", "multi_hop", "comparison", "temporal", "unanswerable")


def _q(i: int, type_: str = "factual", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": f"q-{i:03d}",
        "type": type_,
        "follow_up": False,
        "cross_lingual": False,
        "text": f"Question numéro {i} ?",
        "lang": "fr",
        "reference_answer": "Orvane",
        "answer_form": "short",
        "reference_anchors": [{"doc": "a.md", "headings": ["Guide", "Alpha"]}],
        "status": "validated",
        "split": None,
        "contaminated_by": [],
        "history": [],
        "origin": {"kind": "human", "name": "anael"},
        "scenario_target": None,
    }
    if type_ == "unanswerable":
        base["reference_anchors"] = []
    base.update(kw)
    return base


def _jeu(questions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"corpus_id": "demo", "target_count": 50, "freeze": None, "questions": questions}


def _ecrire(chemin: Path, questions: list[dict[str, Any]]) -> Path:
    texte = yaml.safe_dump(_jeu(questions), sort_keys=False, allow_unicode=True)
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def _cinquante() -> list[dict[str, Any]]:
    return [_q(i, TYPES[i % 5]) for i in range(50)]


def _doc(questions: list[dict[str, Any]]) -> io.QuestionsFile:
    return io.QuestionsFile.model_validate(_jeu(questions))


def _splits(doc: io.QuestionsFile) -> dict[str, str | None]:
    return {q.id: q.split for q in doc.questions}


def test_gel_stratifie_40_pour_cent_par_type() -> None:
    gele = freeze.geler(_doc(_cinquante()), 0.4, 42)
    for t in TYPES:
        parts = [q.split for q in gele.questions if q.type == t]
        assert parts.count("dev") == 4 and parts.count("test") == 6
    assert gele.freeze is not None
    assert (gele.freeze.seed, gele.freeze.dev_ratio) == (42, 0.4)
    assert gele.freeze.at.endswith("Z") and len(gele.freeze.sha256) == 64


def test_arrondi_documente() -> None:
    assert [freeze.nb_dev(n, 0.4) for n in (1, 2, 3, 5, 10)] == [0, 1, 1, 2, 4]
    assert freeze.nb_dev(3, 0.5) == 2  # la moitié vers le haut
    assert freeze.nb_dev(7, 0.0) == 0 and freeze.nb_dev(7, 1.0) == 7


def test_meme_graine_meme_repartition_quel_que_soit_l_ordre() -> None:
    qs = _cinquante()
    a = freeze.geler(_doc(qs), 0.4, 42)
    b = freeze.geler(_doc(list(reversed(qs))), 0.4, 42)
    c = freeze.geler(a, 0.4, 42)  # second Gel du jeu déjà gelé
    assert _splits(a) == _splits(b) == _splits(c)
    assert a.freeze is not None and c.freeze is not None
    assert a.freeze.sha256 == c.freeze.sha256
    assert _splits(freeze.geler(_doc(qs), 0.4, 7)) != _splits(a)


def test_les_questions_non_participantes_n_ont_pas_de_split() -> None:
    qs = [_q(0), _q(1, status="rejected", split="dev"), _q(2, status="corrected")]
    gele = freeze.geler(_doc(qs), 0.5, 1)
    assert gele.questions[1].split is None
    assert gele.questions[0].split is not None and gele.questions[2].split is not None


def test_empreinte_est_le_sha_du_json_canonique_sans_freeze_ni_contaminated_by() -> None:
    gele = freeze.geler(_doc(_cinquante()), 0.4, 42)
    brut = gele.model_dump(mode="json")
    del brut["freeze"]
    for q in brut["questions"]:
        del q["contaminated_by"]
    attendu = hashlib.sha256(canonical_json(brut).encode("utf-8")).hexdigest()
    assert gele.freeze is not None and gele.freeze.sha256 == attendu


def test_verify_frozen_accepte_un_jeu_intact_et_relu_du_disque(tmp_path: Path) -> None:
    chemin = tmp_path / "q.yaml"
    io.save(chemin, freeze.geler(_doc(_cinquante()), 0.4, 42))
    freeze.verify_frozen(io.load(chemin))


def test_verify_frozen_refuse_un_texte_modifie() -> None:
    gele = freeze.geler(_doc(_cinquante()), 0.4, 42)
    qs = list(gele.questions)
    qs[3] = qs[3].model_copy(update={"text": "Texte changé en douce ?"})
    with pytest.raises(ConfigError, match="empreinte différente") as exc:
        freeze.verify_frozen(gele.model_copy(update={"questions": tuple(qs)}))
    assert exc.value.path == "freeze.sha256"


def test_verify_frozen_refuse_un_split_ou_un_statut_modifie() -> None:
    gele = freeze.geler(_doc(_cinquante()), 0.4, 42)
    q0 = gele.questions[0]
    autre = "test" if q0.split == "dev" else "dev"
    for maj in ({"split": autre}, {"status": "rejected"}):
        qs = (q0.model_copy(update=maj), *gele.questions[1:])
        with pytest.raises(ConfigError, match="empreinte différente"):
            freeze.verify_frozen(gele.model_copy(update={"questions": qs}))


def test_verify_frozen_refuse_un_jeu_non_gele() -> None:
    with pytest.raises(ConfigError, match="non gelé"):
        freeze.verify_frozen(_doc(_cinquante()))


def test_contaminated_by_ne_casse_pas_l_empreinte() -> None:
    gele = freeze.geler(_doc(_cinquante()), 0.4, 42)
    q0 = gele.questions[0].model_copy(update={"contaminated_by": ("fake-llm-a",)})
    freeze.verify_frozen(gele.model_copy(update={"questions": (q0, *gele.questions[1:])}))


def test_select_questions_dev_et_test_explicite() -> None:
    qs = [_q(i, split="dev" if i % 2 else "test") for i in range(6)]
    qs += [_q(10, status="corrected", split="dev"), _q(11, status="rejected", split="dev")]
    qs += [_q(12, status="generated", split="dev"), _q(13, split=None)]
    doc = _doc(qs)
    dev = freeze.select_questions(doc, split="dev")
    assert {q.id for q in dev} == {"q-001", "q-003", "q-005", "q-010"}
    test = freeze.select_questions(doc.questions, split="test")
    assert {q.id for q in test} == {"q-000", "q-002", "q-004"}
    with pytest.raises(ConfigError, match="split"):
        freeze.select_questions(doc, split="tout")  # type: ignore[arg-type]


def test_gel_refuse_les_questions_generated_et_les_liste() -> None:
    qs = [_q(0), _q(1, status="generated"), _q(2, status="generated")]
    with pytest.raises(ConfigError, match=r"2 Question\(s\) `generated`.*q-001, q-002"):
        freeze.geler(_doc(qs))


def test_dev_ratio_hors_bornes() -> None:
    with pytest.raises(ConfigError, match="dev-ratio"):
        freeze.geler(_doc([_q(0)]), 1.5)


def test_load_agrege_rapporte_toutes_les_erreurs(tmp_path: Path) -> None:
    qs = [_q(0), _q(1, type="inconnu"), _q(2, status="nimporte"), _q(3)]
    with pytest.raises(ValidationFailed) as exc:
        io.load_agrege(_ecrire(tmp_path / "q.yaml", qs))
    chemins = [e.path for e in exc.value.errors]
    assert "questions[1].type" in chemins and "questions[2].status" in chemins
    qs = [_q(0), _q(0, text="b ?"), _q(1), _q(1, text="c ?")]
    with pytest.raises(ValidationFailed) as exc:
        io.load_agrege(_ecrire(tmp_path / "d.yaml", qs))
    assert [e.path for e in exc.value.errors] == ["questions[1].id", "questions[3].id"]


def test_load_agrege_fichier_valide(tmp_path: Path) -> None:
    chemin = _ecrire(tmp_path / "q.yaml", _cinquante())
    assert io.load_agrege(chemin) == io.load(chemin)


def test_cli_geler_ecrit_le_gel_et_est_reproductible(tmp_path: Path) -> None:
    a = _ecrire(tmp_path / "a.yaml", _cinquante())
    b = _ecrire(tmp_path / "b.yaml", _cinquante())
    r = CliRunner()
    res = r.invoke(app, ["questions", "geler", str(a), "--dev-ratio", "0.4", "--graine", "42"])
    assert res.exit_code == 0, res.output
    assert "dev 4, test 6" in res.output and "Empreinte" in res.output
    assert r.invoke(app, ["questions", "geler", str(b), "--graine", "42"]).exit_code == 0
    ja, jb = io.load(a), io.load(b)
    assert _splits(ja) == _splits(jb)
    assert ja.freeze is not None and ja.freeze.seed == 42
    freeze.verify_frozen(ja)
    assert yaml.safe_load(a.read_text(encoding="utf-8"))["freeze"]["dev_ratio"] == 0.4


def test_cli_geler_refuse_les_generated_sans_ecrire(tmp_path: Path) -> None:
    chemin = _ecrire(tmp_path / "q.yaml", [_q(0), _q(1, status="generated")])
    avant = chemin.read_text(encoding="utf-8")
    res = CliRunner().invoke(app, ["questions", "geler", str(chemin)])
    assert res.exit_code == 2
    assert "generated" in res.output and "q-001" in res.output
    assert chemin.read_text(encoding="utf-8") == avant


def test_cli_geler_agrege_les_erreurs_du_fichier(tmp_path: Path) -> None:
    qs = [_q(0), _q(1, type="inconnu"), _q(2, status="zzz")]
    chemin = _ecrire(tmp_path / "q.yaml", qs)
    res = CliRunner().invoke(app, ["questions", "geler", str(chemin)])
    assert res.exit_code == 2
    assert "questions[1].type" in res.output and "questions[2].status" in res.output
    assert "2 erreur(s)" in res.output
