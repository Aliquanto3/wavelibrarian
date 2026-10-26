"""Story 8.9 : paquet d'annotation (export, aller-retour) et section de calibration du Rapport."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.report.generer import generer_rapport
from wavelibrarian.report.paquet import exporter_paquet, graine_de_tirage
from wavelibrarian.scoring.calibration import charger_dossier, kappa_inter_annotateurs

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
DONNEES: dict[str, Any] = {
    "experiment_id": "exp-8-9",
    "seed": 42,
    "profile": "test",
    "corpus": str(RACINE / "corpus.yaml"),
    "questions": str(RACINE / "questions.yaml"),
    "split": "dev",
    "max_questions": 4,
    "tier": "all",
    "conditions": ["standard"],
    "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
    "configurations": [
        {"id": "sans-contexte", "architecture": "no_context"},
        {"id": "bm25", "architecture": "bm25_only"},
    ],
}


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("run-8-9")
    home = base / "wl_home"
    home.mkdir()
    chemin = base / "exp.yaml"
    chemin.write_text(yaml.safe_dump(DONNEES, allow_unicode=True), encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setenv("WL_HOME", str(home))
    try:
        res = CliRunner().invoke(app, ["run", str(chemin)])
        assert res.exit_code == 0, res.output
        (dossier,) = [d for d in (home / "runs").iterdir() if d.is_dir()]
    finally:
        mp.undo()
    return dossier


def _lignes(f: Path) -> list[dict[str, Any]]:
    return yaml.safe_load(f.read_text(encoding="utf-8"))["annotations"]


def _ids(f: Path) -> set[str]:
    return {a["answer_id"] for a in _lignes(f)}


def _remplir(dossier: Path) -> None:
    for f in dossier.glob("*.yaml"):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for i, a in enumerate(doc["annotations"]):
            a["verdict"] = "yes" if i % 2 == 0 else "no"
        f.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")


def _copie(run_dir: Path, vers: Path) -> Path:
    vers.mkdir()
    for f in run_dir.iterdir():
        if f.is_file():
            (vers / f.name).write_bytes(f.read_bytes())
    return vers


def test_export_prerempli_format_4_6(run_dir: Path, tmp_path: Path) -> None:
    p = exporter_paquet(run_dir, tmp_path / "p", annotateurs=["anael"], nombre=3)
    assert p.n_reponses == 3 and p.n_doubles == 0
    doc = yaml.safe_load((tmp_path / "p" / "anael.yaml").read_text(encoding="utf-8"))
    assert doc["annotator"] == "anael"
    lignes = doc["annotations"]
    criteres = {"correctness", "completeness", "faithfulness"}
    assert lignes and {a["criterion"] for a in lignes} <= criteres
    assert all(a["verdict"] == "" and a["note"] == "" for a in lignes)
    premieres = {a["answer_id"]: a for a in reversed(lignes)}
    assert all(a["question"] and "answer" in a for a in premieres.values())
    assert all(isinstance(a["cited_anchors"], list) for a in premieres.values())
    assert all(a["answer_id"].startswith(run_dir.name + "/") for a in lignes)
    assert len({a["answer_id"] for a in lignes}) == 3


def test_tirage_stable_a_graine_egale(run_dir: Path, tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    exporter_paquet(run_dir, a, annotateurs=["x"], nombre=3, graine=7)
    exporter_paquet(run_dir, b, annotateurs=["x"], nombre=3, graine=7)
    assert (a / "x.yaml").read_bytes() == (b / "x.yaml").read_bytes()
    tirages = set()
    for g in range(1, 8):
        d = tmp_path / f"g{g}"
        exporter_paquet(run_dir, d, annotateurs=["x"], nombre=3, graine=g)
        tirages.add(frozenset(_ids(d / "x.yaml")))
    assert len(tirages) > 1
    assert graine_de_tirage(7) == graine_de_tirage(7) != graine_de_tirage(8)


def test_aller_retour_passe_la_validation_5_1(run_dir: Path, tmp_path: Path) -> None:
    d = tmp_path / "p"
    exporter_paquet(run_dir, d, annotateurs=["anael"], nombre=4)
    _remplir(d)
    ann = charger_dossier(d)
    assert ann.annotateurs == ["anael"]
    assert len(ann.verdicts) == len(_lignes(d / "anael.yaml"))


def test_part_double_deux_annotateurs(run_dir: Path, tmp_path: Path) -> None:
    d = tmp_path / "p"
    # 5 Réponses, part 0,4 : 2 doublement annotées ; les 3 autres réparties (2 + 1).
    p = exporter_paquet(run_dir, d, annotateurs=["ana", "bob"], nombre=5, part_double=0.4)
    assert (p.n_reponses, p.n_doubles) == (5, 2)
    ids = {n: _ids(d / f"{n}.yaml") for n in ("ana", "bob")}
    assert len(ids["ana"] & ids["bob"]) == 2
    assert len(ids["ana"] | ids["bob"]) == 5
    assert sorted(len(v) for v in ids.values()) == [3, 4]
    _remplir(d)
    inter = kappa_inter_annotateurs(charger_dossier(d))
    assert inter[0]["annotators"] == ["ana", "bob"]
    assert all(f["n_items"] <= 2 for f in inter[0]["criteria"].values())


def test_nombre_superieur_aux_reponses_tout_est_pris(run_dir: Path, tmp_path: Path) -> None:
    p = exporter_paquet(run_dir, tmp_path / "p", annotateurs=["a"], nombre=500)
    assert p.n_reponses == p.n_eligibles


def test_completed_with_errors_exportable_et_running_refuse(run_dir: Path, tmp_path: Path) -> None:
    copie = _copie(run_dir, tmp_path / "run")
    man = json.loads((copie / "manifest.json").read_text(encoding="utf-8"))
    man["status"] = "completed_with_errors"
    (copie / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    assert exporter_paquet(copie, tmp_path / "p", annotateurs=["a"], nombre=2).n_reponses == 2
    man["status"] = "running"
    (copie / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    with pytest.raises(ConfigError):
        exporter_paquet(copie, tmp_path / "q", annotateurs=["a"], nombre=2)


def test_cli_codes_de_sortie(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WL_HOME", str(run_dir.parents[1]))
    vers = str(tmp_path / "p")
    base = ["annotations", "exporter", run_dir.name, "--vers", vers]
    ok = CliRunner().invoke(app, [*base, "--nombre", "3", "--graine", "1"])
    assert ok.exit_code == 0, ok.output
    assert (tmp_path / "p" / "anael.yaml").is_file()
    for args in (
        ["--part-double", "1.5"],
        ["--nombre", "0"],
        ["--annotateurs", "a,a"],
        ["--annotateurs", "../x"],
    ):
        r = CliRunner().invoke(app, [*base, *args])
        assert r.exit_code == 2, (args, r.output)
    r = CliRunner().invoke(app, ["annotations", "exporter", "inconnu", "--vers", vers])
    assert r.exit_code == 2


def _calibration(run: Path, inter: list[dict[str, Any]]) -> None:
    fiche = {"kappa": 0.5, "instability": 0.25, "n_items": 8}
    indefinie = {"kappa": None, "instability": None, "n_items": 1}
    donnees = {
        "kappa_threshold": 0.6,
        "judges": {
            "fake-llm-a": {
                "excluded": True,
                "reason": "kappa 0,50 < 0,60",
                "criteria": {"correctness": fiche, "faithfulness": indefinie},
            },
            "fake-llm-b": {
                "excluded": False,
                "criteria": {"correctness": {**fiche, "kappa": 0.8}},
            },
        },
        "inter_annotator": inter,
    }
    (run / "calibration.json").write_text(json.dumps(donnees), encoding="utf-8")


def test_rapport_section_calibration(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WL_HOME", str(run_dir.parents[1]))
    copie = _copie(run_dir, tmp_path / "run")

    def md() -> str:
        generer_rapport(copie)
        return (copie / "report" / "report.md").read_text(encoding="utf-8")

    texte = md()
    assert "## Calibration des Juges" in texte and "Calibration absente" in texte
    _calibration(copie, [])
    texte = md()
    assert (
        "| `fake-llm-a` | correctness | 0,50 | 0,25 | 8 | n/a | oui (kappa 0,50 < 0,60) |" in texte
    )
    assert "| `fake-llm-a` | faithfulness | indéfini | indéfinie | 1 | n/a | oui" in texte
    assert "| `fake-llm-b` | correctness | 0,80 | 0,25 | 8 | n/a | non |" in texte
    assert "Kappa inter-annotateurs : absent (aucune double annotation)." in texte
    paire = {
        "annotators": ["ana", "bob"],
        "criteria": {"correctness": {"kappa": 0.75, "n_items": 4}},
    }
    _calibration(copie, [paire])
    texte = md()
    assert "| ana et bob | correctness | 0,75 | 4 |" in texte
    assert "absent (aucune double" not in texte


def test_dossier_deja_rempli_refuse_sans_ecraser(run_dir: Path, tmp_path: Path) -> None:
    d = tmp_path / "p"
    exporter_paquet(run_dir, d, annotateurs=["anael"], nombre=2)
    _remplir(d)
    saisi = (d / "anael.yaml").read_bytes()
    with pytest.raises(ConfigError, match="--ecraser"):
        exporter_paquet(run_dir, d, annotateurs=["anael"], nombre=2)
    with pytest.raises(ConfigError, match="--ecraser"):
        exporter_paquet(run_dir, d, annotateurs=["bob"], nombre=2)  # charger_dossier lirait tout
    assert (d / "anael.yaml").read_bytes() == saisi
    p = exporter_paquet(run_dir, d, annotateurs=["bob"], nombre=2, ecraser=True)
    assert [f.name for f in p.autres] == ["anael.yaml"]
    p = exporter_paquet(run_dir, d, annotateurs=["anael"], nombre=2, ecraser=True)
    assert [f.name for f in p.autres] == ["bob.yaml"]
    assert (d / "anael.yaml").read_bytes() != saisi


@pytest.mark.parametrize("noms", [["Anael", "anael"], ["CON"], ["nul"], ["com1"]])
def test_annotateurs_casse_et_noms_reserves_refuses(
    run_dir: Path, tmp_path: Path, noms: list[str]
) -> None:
    with pytest.raises(ConfigError):
        exporter_paquet(run_dir, tmp_path / "p", annotateurs=noms, nombre=2)
    assert not (tmp_path / "p").exists()


def test_contexte_des_juges_dans_le_paquet(run_dir: Path, tmp_path: Path) -> None:
    def references(a: Any, q: Any) -> list[str]:
        return [f"passage de référence de {q.id}"]

    d = tmp_path / "p"
    exporter_paquet(run_dir, d, annotateurs=["a"], nombre=500, textes_reference=references)
    lignes = _lignes(d / "a.yaml")
    premieres: dict[str, dict[str, Any]] = {}
    for a in lignes:
        premieres.setdefault(a["answer_id"], a)
    assert all("reference_answer" in a for a in premieres.values())
    for aid, a in premieres.items():
        qid = aid.rsplit("/", 1)[1]
        assert a["reference_passages"] == [f"passage de référence de {qid}"]
        assert "context_passages" in a
    autres = [a for a in lignes if premieres[a["answer_id"]] is not a]
    assert autres and all("context_passages" not in a for a in autres)
    # bm25_only fournit des Passages au Generator, no_context aucun.
    assert any(a["context_passages"] for aid, a in premieres.items() if "/bm25/" in aid)
    assert all(
        not a["context_passages"] for aid, a in premieres.items() if "/sans-contexte/" in aid
    )


def test_bout_en_bout_export_calibrer_rapport(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paquet exporté par la CLI (Corpus relu), rempli, calibré au Faux LLM, lu par le Rapport."""
    home = tmp_path / "home"
    shutil.copytree(run_dir.parents[1], home)
    monkeypatch.setenv("WL_HOME", str(home))
    d = tmp_path / "annotations"
    exp = run_dir.parents[2] / "exp.yaml"
    args = ["annotations", "exporter", run_dir.name, "--vers", str(d), "--nombre", "6"]
    r = CliRunner().invoke(app, [*args, "--annotateurs", "ana,bob", "--part-double", "0.5"])
    assert r.exit_code == 0, r.output
    lignes = _lignes(d / "ana.yaml")
    assert any(a.get("reference_passages") for a in lignes)  # Corpus relu par la CLI
    r = CliRunner().invoke(app, [*args, "--annotateurs", "ana"])
    assert r.exit_code == 2 and "--ecraser" in r.output
    _remplir(d)
    r = CliRunner().invoke(
        app, ["calibrer", str(exp), "--annotations", str(d), "--run", run_dir.name]
    )
    assert r.exit_code == 0, r.output
    run = home / "runs" / run_dir.name
    donnees = json.loads((run / "calibration.json").read_text(encoding="utf-8"))
    assert donnees["judges"] and donnees["inter_annotator"]
    generer_rapport(run)
    texte = (run / "report" / "report.md").read_text(encoding="utf-8")
    section = texte.split("## Calibration des Juges", 1)[1].split("\n## ", 1)[0]
    for juge in donnees["judges"]:
        assert f"| `{juge}` |" in section
    assert "| ana et bob |" in section and "Source :" not in section


def test_paquet_rempli_avec_na_se_recharge(run_dir: Path, tmp_path: Path) -> None:
    """Revue 9.3 : un paquet exporté, rempli avec `na` (nu en YAML) sur les trois Critères, est
    accepté par le chargeur de `wl calibrer`."""
    d = tmp_path / "p"
    exporter_paquet(run_dir, d, annotateurs=["anael"], nombre=2)
    f = d / "anael.yaml"
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    for a in doc["annotations"]:
        a["verdict"] = "na"
    texte = yaml.safe_dump(doc, allow_unicode=True)
    assert "verdict: na\n" in texte  # écrit nu, comme un annotateur le taperait
    f.write_text(texte, encoding="utf-8")
    ann = charger_dossier(d)
    assert ann.verdicts and set(ann.verdicts.values()) == {"na"}
    assert {c for (_, _, c) in ann.verdicts} == {a["criterion"] for a in doc["annotations"]}
