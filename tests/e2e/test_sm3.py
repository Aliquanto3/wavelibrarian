"""SM-3 (story 4.14) : `wl run experiments/mini-test.yaml`, profil `test`, sans réseau.

Toutes les Architectures du registre, Conditions standard et contexte parfait, Scénario du
Mini-corpus, un Palier : l'Exécution termine en `completed` et le Rapport est complet (FR-40).
"""

import csv
import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian import registry
from wavelibrarian.cli import app
from wavelibrarian.config.load import load_experiment

RACINE = Path(__file__).resolve().parents[2]
MINI_TEST = RACINE / "experiments" / "mini-test.yaml"

# Sections de FR-40 (« Paliers » : un Palier est posé ; « Fronts » : la synthèse en tête).
SECTIONS = (
    "## Expérience",
    "## Configurations non dominées (Qualité × coût total)",
    "## Profil de corpus",
    "## Juges",
    "## Configurations inapplicables",
    "## Scores",
    "## Qualité par Type de question",
    "## Contexte parfait",
    "## Fraîcheur",
    "## Résultats par Palier",
    "## Questions contaminées",
    "## Recherche",
    "## Comparaisons appariées",
    "## Coûts, énergie et latence",
    "## Réponses non notées",
)
# Les six fichiers du Rapport (contracts.md §6) : `report.md` et cinq CSV.
FICHIERS = ("report.md", "scores.csv", "pairs.csv", "pareto.csv", "costs.csv", "retrieval.csv")


def _csv(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _wl(home: Path, *args: str) -> Any:
    mp = pytest.MonkeyPatch()
    mp.setenv("WL_HOME", str(home))
    try:
        return CliRunner().invoke(app, list(args))
    finally:
        mp.undo()


def _executions(home: Path) -> list[Path]:
    return sorted(d for d in (home / "runs").iterdir() if d.is_dir())


@pytest.fixture(scope="module")
def home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dossier = tmp_path_factory.mktemp("sm3") / "wl_home"
    dossier.mkdir()
    res = _wl(dossier, "run", str(MINI_TEST))
    assert res.exit_code == 0, res.output
    return dossier


@pytest.fixture(scope="module")
def run_dir(home: Path) -> Path:
    (dossier,) = _executions(home)
    return dossier


def _experience_absolue(**champs: Any) -> dict[str, Any]:
    """`mini-test.yaml` avec ses chemins rendus absolus, pour l'écrire ailleurs."""
    donnees = yaml.safe_load(MINI_TEST.read_text(encoding="utf-8"))
    for cle in ("corpus", "questions", "scenario"):
        donnees[cle] = str((MINI_TEST.parent / donnees[cle]).resolve())
    return {**donnees, **champs}


def test_mini_test_cite_chaque_architecture_enregistree() -> None:
    registry.discover()
    citees = {c.architecture for c in load_experiment(MINI_TEST).configurations}
    assert set(registry.names("architecture")) <= citees


def test_mini_test_graphrag_local_et_global() -> None:
    recherches = {
        c.params.get("search")
        for c in load_experiment(MINI_TEST).configurations
        if c.architecture == "graphrag"
    }
    assert recherches == {"local", "global"}


def test_execution_completed_et_rapport_complet(run_dir: Path) -> None:
    manifeste = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifeste["status"] == "completed"
    rapport = run_dir / "report"
    for nom in FICHIERS:
        chemin = rapport / nom
        assert chemin.is_file() and chemin.stat().st_size > 0, nom
        if nom.endswith(".csv"):
            assert _csv(chemin), f"{nom} sans ligne de données"
    texte = (rapport / "report.md").read_text(encoding="utf-8")
    titres = [ligne for ligne in texte.splitlines() if ligne.startswith("## ")]
    manquantes = [s for s in SECTIONS if s not in titres]
    assert not manquantes, manquantes
    assert titres[1] == SECTIONS[1]  # la synthèse du front ouvre le Rapport


def test_aucune_reponse_en_erreur(run_dir: Path) -> None:
    """Chaque Configuration répond (ok ou inapplicable motivé), dans les deux Conditions et les
    deux phases."""
    reponses = [json.loads(ligne) for ligne in (run_dir / "answers.jsonl").open(encoding="utf-8")]
    statuts = {r["status"] for r in reponses}
    assert statuts <= {"ok", "inapplicable"}, statuts
    configs = {c.id for c in load_experiment(MINI_TEST).configurations}
    vues = {(r["config_id"], r["condition"], r["phase"]) for r in reponses if r["status"] == "ok"}
    for c in configs:
        for condition in ("standard", "perfect_context"):
            for phase in ("base", "after_update"):
                assert (c, condition, phase) in vues, (c, condition, phase)


def test_pareto_csv_porte_le_front_qualite_cout(run_dir: Path) -> None:
    lignes = _csv(run_dir / "report" / "pareto.csv")
    front = [x for x in lignes if x["front"] == "qualite-cout"]
    assert front
    assert all(Decimal(x["x"]) >= 0 for x in front)


def test_cout_du_rapport_egal_au_cout_trace(home: Path, run_dir: Path) -> None:
    """Somme des `wl.cost` des spans = registre de dépenses (même devise) ; `costs.csv`, hors
    possession, = cette somme convertie en euros, au centime près."""
    traces = [json.loads(ligne) for ligne in (run_dir / "traces.jsonl").open(encoding="utf-8")]
    devises = {s["wl.currency"] for s in traces if Decimal(s.get("wl.cost", "0")) != 0}
    assert devises == {"USD"}
    trace = sum((Decimal(s.get("wl.cost", "0")) for s in traces), Decimal(0))
    base = sqlite3.connect(home / "ledger.sqlite")
    try:
        lignes = base.execute(
            "SELECT actual FROM reservations WHERE run_id = ? AND status = 'settled'",
            (run_dir.name,),
        ).fetchall()
    finally:
        base.close()
    assert lignes and trace > 0
    assert sum((Decimal(a) for (a,) in lignes), Decimal(0)) == trace
    resolue = yaml.safe_load((run_dir / "experiment.resolved.yaml").read_text(encoding="utf-8"))
    taux = Decimal(str(resolue["costs"]["fx"]["rates_to_eur"]["USD"]))
    couts = _csv(run_dir / "report" / "costs.csv")
    api = sum(
        (Decimal(x["cost_eur_real"]) - Decimal(x["possession_eur"]) for x in couts), Decimal(0)
    )
    assert abs(api - trace * taux) < Decimal("0.01")


def test_front_exporte_relance_par_wl_run(home: Path, run_dir: Path, tmp_path: Path) -> None:
    vers = tmp_path / "front.yaml"
    res = _wl(
        home, "rapport", run_dir.name, "--exporter-front", "qualite-cout", "--vers", str(vers)
    )
    assert res.exit_code == 0, res.output
    liste = yaml.safe_load(vers.read_text(encoding="utf-8"))["configurations"]
    assert liste
    chemin = tmp_path / "front-exp.yaml"
    donnees = _experience_absolue(experiment_id="mini-test-front", configurations=liste)
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    relance = _wl(home, "run", str(chemin))
    assert relance.exit_code == 0, relance.output


def test_reuse_index_refuse_sur_un_autre_wl_home(home: Path, tmp_path: Path) -> None:
    """Une clé d'index de ce `WL_HOME` n'existe pas dans un autre : `wl run` refuse (code 2)."""
    cle = next(d.name for d in (home / "index").iterdir() if (d / "manifest.json").is_file())
    configuration = {"id": "bm25", "architecture": "bm25_only", "reuse_index": cle}
    chemin = tmp_path / "reuse.yaml"
    donnees = _experience_absolue(experiment_id="mini-test-reuse", configurations=[configuration])
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    autre = tmp_path / "autre_home"
    autre.mkdir()
    res = _wl(autre, "run", str(chemin))
    assert res.exit_code == 2, res.output
    assert "reuse_index" in res.output
    assert not (autre / "runs").exists() or not _executions(autre)
