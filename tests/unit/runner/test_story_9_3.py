"""Story 9.3 : modalité « sans objet » (`na`) de bout en bout, profil `test`, Faux LLM, sans réseau.

`sans-contexte` (architecture `no_context`) s'abstient toujours avec le Faux LLM : sa fidélité vaut
`na` sans appel de Juge ; `bm25` répond et voit sa fidélité jugée.
"""

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.components.judges.llm import LLMJudge
from wavelibrarian.core.types import Criterion
from wavelibrarian.ports.components import JudgeInput
from wavelibrarian.runner.rundir import read_answers, read_panel, read_verdicts

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
BM25 = {"id": "bm25", "architecture": "bm25_only"}
SANS_CONTEXTE = {"id": "sans-contexte", "architecture": "no_context"}


def _experience(tmp_path: Path) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-9-3",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "max_questions": 3,
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": [BM25, SANS_CONTEXTE],
    }
    chemin = tmp_path / "exp.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl(*args: str, code: int = 0) -> Any:
    res = CliRunner().invoke(app, list(args))
    assert res.exit_code == code, res.output
    return res


def _espion(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[str, ...]]]:
    """Critères demandés à chaque appel de Juge, par texte de Réponse."""
    appels: list[tuple[str, tuple[str, ...]]] = []
    reel = LLMJudge.judge

    def juge(self: LLMJudge, item: JudgeInput, criteria: Sequence[Criterion], pass_id: int) -> Any:
        appels.append((item.answer_text, tuple(criteria)))
        return reel(self, item, criteria, pass_id)

    monkeypatch.setattr(LLMJudge, "judge", juge)
    return appels


@pytest.fixture
def run(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, list[tuple[str, tuple[str, ...]]]]:
    appels = _espion(monkeypatch)
    exp = _experience(tmp_path)
    _wl("run", str(exp))
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return exp, dossier, appels


def _lignes(chemin: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in chemin.read_text(encoding="utf-8").splitlines() if x.strip()]


def _ecrire(chemin: Path, lignes: list[dict[str, Any]]) -> None:
    corps = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lignes)
    chemin.write_text(corps, encoding="utf-8")


def _scores(dossier: Path) -> dict[tuple[str, str], dict[str, str]]:
    with (dossier / "report" / "scores.csv").open(encoding="utf-8", newline="") as f:
        return {
            (r["config_id"], r["criterion"]): r
            for r in csv.DictReader(f)
            if r["question_type"] == "all" and r["condition"] == "standard"
        }


def test_abstention_fidelite_na_auto_sans_juge_et_panel_na(
    run: tuple[Path, Path, list[tuple[str, tuple[str, ...]]]],
) -> None:
    _, dossier, appels = run
    reponses = read_answers(dossier)
    muettes = {a.answer_id for a in reponses.values() if a.config_id == "sans-contexte"}
    assert muettes and all(reponses[a].abstained for a in muettes)
    textes_muets = {reponses[a].text for a in muettes}
    # Aucune requête de Juge ne demande faithfulness pour une abstention ; bm25 la demande.
    assert all("faithfulness" not in c for t, c in appels if t in textes_muets)
    assert any("faithfulness" in c for t, c in appels if t not in textes_muets)
    verdicts = read_verdicts(dossier)
    panel = read_panel(dossier)
    for aid in muettes:
        fid = [
            (m, v.verdict)
            for (i, m, c, _), v in verdicts.items()
            if i == aid and c == "faithfulness"
        ]
        assert fid == [("auto", "na")]
        assert panel[(aid, "faithfulness")].verdict == "na"
        assert panel[(aid, "faithfulness")].judges == ()
        assert panel[(aid, "completeness")].verdict in ("yes", "no")  # autres Critères jugés
    # Rapport : aucun taux de fidélité pour sans-contexte, mais les `na` sont affichés.
    scores = _scores(dossier)
    assert ("sans-contexte", "faithfulness") not in scores
    assert scores[("bm25", "faithfulness")]["n_na"] == "0"
    md = (dossier / "report" / "report.md").read_text(encoding="utf-8")
    assert f"n/a ({len(muettes)} na)" in md
    # Comparaison appariée : aucune paire commune en fidélité (verdicts `na` exclus).
    with (dossier / "report" / "pairs.csv").open(encoding="utf-8", newline="") as f:
        paires = {r["metric"]: r for r in csv.DictReader(f) if r["condition"] == "standard"}
    assert paires["faithfulness"]["n_common"] == "0" and paires["faithfulness"]["p_value"] == ""
    assert paires["completeness"]["n_common"] == "3"


def test_rapport_taux_hors_na_n_effectif_et_compte_na(
    run: tuple[Path, Path, list[tuple[str, tuple[str, ...]]]],
) -> None:
    _, dossier, _ = run
    chemin = dossier / "panel.jsonl"
    lignes = _lignes(chemin)
    bm25 = sorted(
        x["answer_id"]
        for x in lignes
        if "/bm25/" in x["answer_id"] and x["criterion"] == "faithfulness"
    )
    assert len(bm25) == 3
    for x in lignes:  # une fidélité de bm25 passe à `na`, les deux autres à yes et no
        if x["criterion"] == "faithfulness" and x["answer_id"] in bm25:
            x["verdict"] = {bm25[0]: "na", bm25[1]: "yes", bm25[2]: "no"}[x["answer_id"]]
    _ecrire(chemin, lignes)
    _wl("rapport", dossier.name)
    ligne = _scores(dossier)[("bm25", "faithfulness")]
    assert (ligne["n"], ligne["n_na"], float(ligne["value"])) == ("2", "1", 0.5)
    md = (dossier / "report" / "report.md").read_text(encoding="utf-8")
    assert "(n 2, 1 na)" in md
    assert "Une paire où l'un des deux verdicts est `na` (sans objet) est exclue" in md


def test_anciens_fichiers_booleens_restent_lisibles_par_wl_rapport(
    run: tuple[Path, Path, list[tuple[str, tuple[str, ...]]]],
) -> None:
    """Exécution antérieure à la v0.3.0 : `verdict` booléen dans verdicts.jsonl et panel.jsonl."""
    _, dossier, _ = run
    for nom in ("verdicts.jsonl", "panel.jsonl"):
        lignes = [x for x in _lignes(dossier / nom) if x["verdict"] != "na"]
        for x in lignes:
            x["verdict"] = x["verdict"] == "yes"
        _ecrire(dossier / nom, lignes)
    avant = _scores(dossier)
    _wl("rapport", dossier.name)
    apres = _scores(dossier)
    assert apres == avant  # mêmes taux : seuls les `na` (absents des taux) ont disparu
    assert {v.verdict for v in read_panel(dossier).values()} <= {"yes", "no"}


def test_calibration_fidelite_na_sans_appel_et_accords_na_comptes(
    run: tuple[Path, Path, list[tuple[str, tuple[str, ...]]]], tmp_path: Path
) -> None:
    exp, dossier, appels = run
    reponses = read_answers(dossier)
    lignes = []
    for a in sorted(reponses.values(), key=lambda r: r.answer_id):
        muette = a.config_id == "sans-contexte"
        lignes.append(
            {
                "answer_id": a.answer_id,
                "criterion": "faithfulness",
                "verdict": "na" if muette else "yes",
            }
        )
        lignes.append({"answer_id": a.answer_id, "criterion": "completeness", "verdict": "no"})
    ann = tmp_path / "ann"
    ann.mkdir()
    texte = yaml.safe_dump({"annotator": "anael", "annotations": lignes}, allow_unicode=True)
    (ann / "anael.yaml").write_text(texte, encoding="utf-8")
    appels.clear()
    sortie = tmp_path / "cal.json"
    _wl(
        "calibrer",
        str(exp),
        "--annotations",
        str(ann),
        "--run",
        dossier.name,
        "--sortie",
        str(sortie),
    )
    textes_muets = {a.text for a in reponses.values() if a.config_id == "sans-contexte"}
    assert appels and all("faithfulness" not in c for t, c in appels if t in textes_muets)
    d = json.loads(sortie.read_text(encoding="utf-8"))
    for fiche in d["judges"].values():
        fid = fiche["criteria"]["faithfulness"]
        # 3 abstentions : accord `na` (humain et calcul automatique) ; 3 Réponses bm25 au kappa.
        assert fid["na_agreements"] == 3 and fid["na_disagreements"] == 0
        assert fid["n_items"] == 3
        assert fiche["criteria"]["completeness"]["na_agreements"] == 0
    brut = _lignes(tmp_path / "cal_verdicts.jsonl")
    assert all(v["verdict"] in ("yes", "no", "na") for x in brut for v in x["verdicts"].values())


def test_rejugement_produit_les_na_de_fidelite(
    run: tuple[Path, Path, list[tuple[str, tuple[str, ...]]]], wl_home: Path
) -> None:
    """`wl rejuger` (story 9.6) passe par `juger` : une abstention y reçoit aussi `na` sans Juge."""
    exp, source, appels = run
    appels.clear()
    _wl("rejuger", source.name, str(exp))
    (cible,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir() and d != source]
    reponses = read_answers(cible)
    muettes = {a.answer_id for a in reponses.values() if a.config_id == "sans-contexte"}
    textes_muets = {reponses[a].text for a in muettes}
    assert appels and all("faithfulness" not in c for t, c in appels if t in textes_muets)
    verdicts, panel = read_verdicts(cible), read_panel(cible)
    for aid in muettes:
        assert verdicts[(aid, "auto", "faithfulness", 0)].verdict == "na"
        assert panel[(aid, "faithfulness")].verdict == "na"
