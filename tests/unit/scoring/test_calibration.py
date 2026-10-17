"""Tests du chargement des annotations (story 5.1)."""

from pathlib import Path

import pytest

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.scoring.calibration import (
    answer_ids_de_answers_jsonl,
    charger_dossier,
    rapprocher,
)

RUN = "20261018-031500-a1b2c3"
ID1 = f"{RUN}/naive-haiku/standard/all/base/q-001"
ID2 = f"{RUN}/naive-haiku/standard/all/base/q-002"


def _ecrire(dossier: Path, nom: str, annotateur: str, lignes: list[str]) -> None:
    corps = "\n".join(lignes)
    (dossier / f"{nom}.yaml").write_text(
        f"annotator: {annotateur}\nannotations:\n{corps}\n", encoding="utf-8"
    )


def _ligne(aid: str, critere: str = "correctness", verdict: str = "yes") -> str:
    return f'  - answer_id: "{aid}"\n    criterion: {critere}\n    verdict: {verdict}\n    note: ""'


def test_chargement_deux_annotateurs(tmp_path: Path) -> None:
    _ecrire(tmp_path, "anael", "anael", [_ligne(ID1), _ligne(ID1, "faithfulness", "no")])
    _ecrire(tmp_path, "collegue", "collegue", [_ligne(ID1, verdict="no")])
    ann = charger_dossier(tmp_path)
    assert ann.verdicts == {
        ("anael", ID1, "correctness"): True,
        ("anael", ID1, "faithfulness"): False,
        ("collegue", ID1, "correctness"): False,
    }
    assert ann.annotateurs == ["anael", "collegue"]


@pytest.mark.parametrize(
    ("lignes", "chemin"),
    [
        ([_ligne(ID1), _ligne(ID1, "style")], "annotations[1].criterion"),
        ([_ligne(ID1), _ligne(ID2), _ligne(ID1, verdict="maybe")], "annotations[2].verdict"),
        ([_ligne(ID1), _ligne(ID1)], "annotations[1]"),
        (["  - criterion: correctness\n    verdict: yes"], "annotations[0].answer_id"),
    ],
)
def test_erreurs_au_chemin(tmp_path: Path, lignes: list[str], chemin: str) -> None:
    _ecrire(tmp_path, "a", "anael", lignes)
    with pytest.raises(ConfigError) as exc:
        charger_dossier(tmp_path)
    assert exc.value.path == chemin


def test_verdict_yes_no_non_guillemete_et_autre_type(tmp_path: Path) -> None:
    # `yes` / `no` nus (comme dans le contrat §4.6) sont lus en booléens par YAML : acceptés.
    entete = "annotator: a@annotations:@  - answer_id: x@    criterion: correctness@".replace(
        "@", "\n"
    )
    (tmp_path / "a.yaml").write_text(entete + "    verdict: no\n", encoding="utf-8")
    assert charger_dossier(tmp_path).verdicts == {("a", "x", "correctness"): False}
    (tmp_path / "a.yaml").write_text(entete + "    verdict: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        charger_dossier(tmp_path)
    assert exc.value.path == "annotations[0].verdict"


def test_dossier_vide_ou_absent(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        charger_dossier(tmp_path)
    with pytest.raises(ConfigError):
        charger_dossier(tmp_path / "absent")


def test_rapprochement_ignore_et_signale(tmp_path: Path) -> None:
    autre = f"{RUN}/naive-haiku/standard/all/update/q-001"  # même Question, autre phase
    _ecrire(tmp_path, "a", "anael", [_ligne(ID1), _ligne(autre), _ligne(autre, "faithfulness")])
    jsonl = tmp_path / "answers.jsonl"
    jsonl.write_text(f'{{"answer_id": "{ID1}"}}\n\n', encoding="utf-8")
    ids = answer_ids_de_answers_jsonl(jsonl)
    r = rapprocher(charger_dossier(tmp_path), ids)
    assert list(r.annotations.verdicts) == [("anael", ID1, "correctness")]
    assert r.ignorees == [autre]


def test_answers_jsonl_illisible(tmp_path: Path) -> None:
    f = tmp_path / "answers.jsonl"
    f.write_text("pas du json\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        answer_ids_de_answers_jsonl(f)
