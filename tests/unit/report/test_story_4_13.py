"""Story 4.13 : Rapport, Fraîcheur, Paliers, fronts de Pareto et export du front."""

import csv
import dataclasses
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.load import load_experiment
from wavelibrarian.core.types import Answer
from wavelibrarian.report.couts import Couts, LigneCout, LigneLatence
from wavelibrarian.report.export import exporter_front
from wavelibrarian.report.fraicheur import calculer_fraicheur
from wavelibrarian.report.fronts import construire_fronts, lignes_pareto
from wavelibrarian.report.generer import construire_markdown, generer_rapport
from wavelibrarian.report.lecture import Execution, charger
from wavelibrarian.report.scores import QUALITE, LigneScore, Resultats
from wavelibrarian.scoring.panel import PanelVerdict

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
CONFIGS = [
    {"id": "sans-contexte", "architecture": "no_context"},
    {"id": "bm25", "architecture": "bm25_only"},
]
DONNEES: dict[str, Any] = {
    "experiment_id": "exp-4-13",
    "seed": 42,
    "profile": "test",
    "corpus": str(RACINE / "corpus.yaml"),
    "questions": str(RACINE / "questions.yaml"),
    "split": "test",
    "scenario": str(RACINE / "scenario" / "scenario.yaml"),
    "tier": "all",
    "conditions": ["standard", "perfect_context"],
    "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
    "configurations": CONFIGS,
}


def _csv(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _lancer(tmp_path_factory: pytest.TempPathFactory, nom: str, **champs: Any) -> Path:
    base = tmp_path_factory.mktemp(nom)
    home = base / "wl_home"
    home.mkdir()
    chemin = base / "exp.yaml"
    donnees = {**DONNEES, **champs}
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setenv("WL_HOME", str(home))
    try:
        res = CliRunner().invoke(app, ["run", str(chemin)])
        assert res.exit_code == 0, res.output
        (dossier,) = [d for d in (home / "runs").iterdir() if d.is_dir()]
        generer_rapport(dossier)
    finally:
        mp.undo()
    return dossier


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Scénario et Questions liées (split test), un Palier de 20 Documents, deux Conditions."""
    return _lancer(tmp_path_factory, "run-4-13", tier=20)


@pytest.fixture(scope="module")
def run_paliers(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Paliers 5, 10 et 20 (3 Questions du split dev : les petits Paliers ne contiennent pas les
    Documents requis par les 28 Questions du split test)."""
    return _lancer(tmp_path_factory, "run-4-13-paliers", split="dev", max_questions=3)


def _ex(run_dir: Path) -> Execution:
    return charger(run_dir)


# --- fronts : grandeurs écrites à la main -------------------------------------------------------


def _score(
    config: str, valeur: float, critere: str = QUALITE, tier: int | None = None
) -> LigneScore:
    return LigneScore((config, "standard", tier, "base"), "all", critere, valeur, 0.0, 1.0, 10)


def _cout(config: str, post: str, eur: str, **kw: Any) -> LigneCout:
    return LigneCout((config, "standard", None, "base", post), api_real=Decimal(eur), **kw)


def _lat(config: str, p95: float) -> LigneLatence:
    return LigneLatence((config, "standard", None, "base"), 10, 1.0, p95, None, None, None)


def test_fronts_non_dominees_cout_energie_latence_et_critere(run_dir: Path) -> None:
    ex = _ex(run_dir)
    ids = {"sans-contexte", "bm25"}
    res = Resultats(
        scores=[
            _score("sans-contexte", 0.5),
            _score("bm25", 0.8),
            _score("sans-sans", 0.0),  # Configuration inconnue de l'Expérience : ignorée
            _score("sans-contexte", 0.9, "faithfulness"),
            _score("bm25", 0.4, "faithfulness"),
        ]
    )
    couts = Couts(
        lignes=[
            _cout("sans-contexte", "query", "3", kwh_measured=Decimal("0.5")),
            _cout("sans-contexte", "update", "1"),
            _cout("sans-contexte", "judging", "100"),  # hors coût d'une Configuration
            _cout("bm25", "indexing", "1", kwh_estimated=Decimal("2")),
            _cout("bm25", "query", "1"),
        ],
        latences=[_lat("sans-contexte", 0.5), _lat("bm25", 2.0)],
    )
    fronts = {f.nom: f for f in construire_fronts(ex, res, couts)}
    # sans-contexte : moins bon ET plus cher (4 contre 2) que bm25 ; judging n'entre pas
    assert [p.config_id for p in fronts["qualite-cout"].points] == ["bm25"]
    assert fronts["qualite-cout"].points[0].cout == 2.0
    # la latence p95 départage : les deux sont non dominés
    assert {p.config_id for p in fronts["qualite-latence-p95"].points} == ids
    # énergie : mesurée et estimée sont deux fronts, jamais additionnées
    assert [p.config_id for p in fronts["qualite-energie-mesuree"].points] == ["sans-contexte"]
    assert [p.config_id for p in fronts["qualite-energie-estimee"].points] == ["bm25"]
    # un front par Critère : faithfulness, sans-contexte (0,9 pour 4 €) et bm25 (0,4 pour 2 €)
    assert {p.config_id for p in fronts["critere-faithfulness-cout"].points} == ids
    lignes = lignes_pareto(list(fronts.values()))
    assert ["qualite-cout", "bm25", "2.000000000", "0.800000"] in lignes


def test_sans_traces_ni_front_de_cout_ni_d_energie(run_dir: Path) -> None:
    ex = _ex(run_dir)
    res = Resultats(scores=[_score("bm25", 0.8), _score("sans-contexte", 0.5)])
    couts = Couts(latences=[_lat("bm25", 1.0)], traces_presentes=False)
    fronts = construire_fronts(ex, res, couts)
    assert {f.nom for f in fronts} == {"qualite-latence-p95"}
    assert "Traces absentes" in construire_markdown(ex, res, couts, fronts, [])


def test_points_identiques_restent_et_plus_grand_palier_sans_suffixe(run_dir: Path) -> None:
    ex = _ex(run_dir)
    res = Resultats(
        scores=[
            _score("bm25", 0.8, tier=5),
            _score("sans-contexte", 0.8, tier=5),
            _score("bm25", 0.7, tier=20),
        ]
    )
    couts = Couts(
        lignes=[
            LigneCout(("bm25", "standard", 5, "base", "query"), api_real=Decimal(1)),
            LigneCout(("sans-contexte", "standard", 5, "base", "query"), api_real=Decimal(1)),
            LigneCout(("bm25", "standard", 20, "base", "query"), api_real=Decimal(1)),
        ]
    )
    fronts = {f.nom: f for f in construire_fronts(ex, res, couts)}
    assert {p.config_id for p in fronts["qualite-cout@palier-5"].points} == {
        "bm25",
        "sans-contexte",
    }
    assert [p.config_id for p in fronts["qualite-cout"].points] == ["bm25"]  # Palier 20


def test_front_calcule_sur_les_valeurs_ecrites_dans_pareto_csv(run_dir: Path) -> None:
    """Deux Qualités égales à 6 décimales : le front du Rapport garde les deux, comme le ferait
    un front recalculé depuis `pareto.csv` (revue 4.13)."""
    ex = _ex(run_dir)
    res = Resultats(scores=[_score("bm25", 0.8000001), _score("sans-contexte", 0.8)])
    couts = Couts(lignes=[_cout("bm25", "query", "1"), _cout("sans-contexte", "query", "1")])
    (front,) = [f for f in construire_fronts(ex, res, couts) if f.nom == "qualite-cout"]
    lignes = [x for x in lignes_pareto([front])]
    relus = [(c, float(y), float(x)) for _, c, x, y in lignes]
    assert {p.config_id for p in front.points} == {"bm25", "sans-contexte"}
    assert _non_domines(relus) == {c for c, _, _ in relus}


def test_synthese_signale_des_n_differents(run_dir: Path) -> None:
    ex = _ex(run_dir)
    partielle = dataclasses.replace(_score("sans-contexte", 0.9), n=4)
    res = Resultats(scores=[_score("bm25", 0.8), partielle])
    couts = Couts(lignes=[_cout("bm25", "query", "1"), _cout("sans-contexte", "query", "2")])
    fronts = construire_fronts(ex, res, couts)
    md = construire_markdown(ex, res, couts, fronts, [])
    assert "`bm25` 10, `sans-contexte` 4" in md
    egaux = Resultats(scores=[_score("bm25", 0.8), _score("sans-contexte", 0.9)])
    assert "**Attention**" not in construire_markdown(
        ex, egaux, couts, construire_fronts(ex, egaux, couts), []
    )


# --- pareto.csv et synthèse d'une vraie Exécution -----------------------------------------------


def _non_domines(points: list[tuple[str, float, float]]) -> set[str]:
    """(config, x, y) : x minimisé, y maximisé."""
    return {
        c
        for c, x, y in points
        if not any(x2 <= x and y2 >= y and (x2 < x or y2 > y) for _, x2, y2 in points)
    }


def test_pareto_csv_format_noms_et_non_dominance(run_paliers: Path) -> None:
    lignes = _csv(run_paliers / "report" / "pareto.csv")
    assert list(lignes[0]) == ["front", "config_id", "x", "y"]
    par_front: dict[str, list[tuple[str, float, float]]] = {}
    for x in lignes:
        par_front.setdefault(x["front"], []).append((x["config_id"], float(x["x"]), float(x["y"])))
    assert {
        "qualite-cout",
        "qualite-latence-p95",
        "critere-correctness-cout",
        "critere-citation_correctness-cout",
        "qualite-cout@perfect_context",
        "qualite-cout@palier-5",
        "qualite-cout@palier-10",
    } <= set(par_front)
    assert "qualite-cout@palier-20" not in par_front  # le plus grand Palier : sans suffixe
    for points in par_front.values():
        assert {c for c, _, _ in points} == _non_domines(points)
        assert {c for c, _, _ in points} <= {"sans-contexte", "bm25"}


def test_front_qualite_cout_recalcule_depuis_les_csv(run_paliers: Path) -> None:
    rapport = run_paliers / "report"
    couts = _csv(rapport / "costs.csv")
    qualite = {
        x["config_id"]: float(x["value"])
        for x in _csv(rapport / "scores.csv")
        if x["criterion"] == "quality"
        and x["question_type"] == "all"
        and x["condition"] == "standard"
        and x["tier"] == "20"
        and x["phase"] == "base"
    }
    total = {
        # Faux LLM pur (story 8.2) : `cost_eur_real` vaut 0, le front lit `cost_eur_fake`.
        c: sum(
            Decimal(x["cost_eur_real"]) + Decimal(x["cost_eur_fake"])
            for x in couts
            if x["config_id"] == c
            and x["condition"] == "standard"
            and x["tier"] == "20"
            and x["post"] in ("indexing", "update", "query")
        )
        for c in qualite
    }
    attendu = _non_domines([(c, float(total[c]), qualite[c]) for c in qualite])
    front = {
        x["config_id"]: x for x in _csv(rapport / "pareto.csv") if x["front"] == "qualite-cout"
    }
    assert set(front) == attendu
    for c, x in front.items():
        assert float(x["x"]) == pytest.approx(float(total[c]), abs=1e-6)
        assert float(x["y"]) == pytest.approx(qualite[c], abs=1e-6)


def test_report_s_ouvre_sur_la_synthese_du_front(run_dir: Path) -> None:
    md = (run_dir / "report" / "report.md").read_text(encoding="utf-8")
    titre = "## Configurations non dominées (Qualité × coût total)"
    # juste après l'en-tête (titre, statut, Expérience), avant tout autre résultat
    assert md.index("## Expérience") < md.index(titre) < md.index("## Profil de corpus")
    assert md.index(titre) < md.index("## Scores")
    bloc = md[md.index(titre) : md.index("## Profil de corpus")]
    assert "| config_id | Qualité [IC 95 %] | Coût total (€) | Latence p95 (s) |" in bloc
    ids = {
        x["config_id"]
        for x in _csv(run_dir / "report" / "pareto.csv")
        if x["front"] == "qualite-cout"
    }
    lignes = [ligne for ligne in bloc.splitlines() if ligne.startswith("| `")]
    assert {ligne.split("`")[1] for ligne in lignes} == ids  # le même front que pareto.csv
    assert "Aucun score global ni pondération" in bloc


# --- Paliers et Fraîcheur -----------------------------------------------------------------------


def test_section_paliers(run_paliers: Path) -> None:
    md = (run_paliers / "report" / "report.md").read_text(encoding="utf-8")
    bloc = md[md.index("## Résultats par Palier") :].split("\n## ")[0]
    for tier in ("5", "10", "20"):
        assert f"| standard | {tier} |" in bloc
    assert "sous-corpus du Palier" in bloc


def test_fraicheur_denominateur_sans_inapplicables_et_comptes_a_part(run_dir: Path) -> None:
    ex = _ex(run_dir)
    lignes = calculer_fraicheur(ex)
    cibles = {q.id for q in ex.jeu.values() if q.scenario_target and not q.contaminated_by}
    assert cibles  # le split `test` contient q-045 à q-047
    for x in lignes:
        config, condition, tier = x.cle
        attendues = [
            a
            for a in ex.reponses.values()
            if (a.config_id, a.condition, a.tier, a.phase)
            == (config, condition, tier, "after_update")
            and a.question_id in cibles
        ]
        assert x.inapplicables == sum(a.status == "inapplicable" for a in attendues)
        assert x.n + x.non_jugees == sum(a.status == "ok" for a in attendues)
    # en contexte parfait, q-047 (Ancrage supprimé) est inapplicable, hors dénominateur
    parfait = [x for x in lignes if x.cle[1] == "perfect_context"]
    assert parfait and all(x.inapplicables >= 1 for x in parfait)
    md = (run_dir / "report" / "report.md").read_text(encoding="utf-8")
    assert "## Fraîcheur" in md and "**retirées du dénominateur**" in md


def _reponse(qid: str, statut: str) -> Answer:
    return Answer(
        answer_id=f"r/bm25/standard/all/after_update/{qid}",
        question_id=qid,
        config_id="bm25",
        condition="standard",
        tier=None,
        phase="after_update",
        status=statut,  # type: ignore[arg-type]
        text="",
        abstained=False,
    )


def _verdict(qid: str, oui: bool) -> dict[str, PanelVerdict]:
    return {
        "correctness": PanelVerdict(
            answer_id=f"r/bm25/standard/all/after_update/{qid}",
            criterion="correctness",
            verdict=oui,
        )
    }


def test_fraicheur_calcul_a_la_main(run_dir: Path) -> None:
    ex = _ex(run_dir)
    reps = [
        _reponse("q-045", "ok"),
        _reponse("q-046", "ok"),
        _reponse("q-047", "inapplicable"),
        _reponse("q-001", "ok"),  # sans scenario_target : ignorée
    ]
    ex2 = dataclasses.replace(
        ex,
        reponses={a.answer_id: a for a in reps},
        verdicts_par_reponse={
            reps[0].answer_id: _verdict("q-045", True),
            reps[1].answer_id: _verdict("q-046", False),
        },
    )
    (x,) = calculer_fraicheur(ex2)
    assert (x.n, x.correctes, x.taux, x.inapplicables, x.echecs) == (2, 1, 0.5, 1, 0)
    # sans Scénario : une phrase, pas de Fraîcheur
    ex3 = dataclasses.replace(ex2, experience=ex.experience.model_copy(update={"scenario": None}))
    md = construire_markdown(ex3, Resultats(), None, [], calculer_fraicheur(ex3))
    assert "Aucun Scénario de mise à jour" in md


# --- export du front ----------------------------------------------------------------------------


def _wl(run_dir: Path, *args: str) -> Any:
    return CliRunner().invoke(app, ["rapport", run_dir.name, *args])


def test_export_front_accepte_par_config_load(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WL_HOME", str(run_dir.parents[1]))
    vers = tmp_path / "front.yaml"
    res = _wl(run_dir, "--exporter-front", "qualite-cout", "--vers", str(vers))
    assert res.exit_code == 0, res.output
    liste = yaml.safe_load(vers.read_text(encoding="utf-8"))
    ids = [c["id"] for c in liste["configurations"]]
    attendu = [
        x["config_id"]
        for x in _csv(run_dir / "report" / "pareto.csv")
        if x["front"] == "qualite-cout"
    ]
    assert ids == attendu and ids
    # collée telle quelle dans une nouvelle Expérience, la liste est acceptée par config/load.py
    nouvelle = {
        **DONNEES,
        "experiment_id": "exp-reprise",
        "configurations": liste["configurations"],
    }
    chemin = tmp_path / "nouvelle.yaml"
    chemin.write_text(yaml.safe_dump(nouvelle, allow_unicode=True), encoding="utf-8")
    assert [c.id for c in load_experiment(chemin).configurations] == ids
    assert all("+" not in c["parser"]["name"] for c in liste["configurations"])


def test_export_front_refus(run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WL_HOME", str(run_dir.parents[1]))
    vers = tmp_path / "f.yaml"
    inconnu = _wl(run_dir, "--exporter-front", "n-importe-quoi", "--vers", str(vers))
    assert inconnu.exit_code == 2 and "qualite-cout" in inconnu.output and not vers.exists()
    assert _wl(run_dir, "--exporter-front", "qualite-cout").exit_code == 2
    assert _wl(run_dir, "--exporter-front", "", "--vers", str(vers)).exit_code == 2
    assert not vers.exists()
    assert _wl(run_dir, "--vers", str(vers)).exit_code == 2
    assert _wl(run_dir).exit_code == 0


def test_export_recopie_reuse_index_et_params_rechargeables(run_dir: Path, tmp_path: Path) -> None:
    """`reuse_index` est une clé d'index (`<WL_HOME>/index/<cle>`), pas un `config_id` : recopié
    tel quel. Les params résolus (Composants imbriqués) se rechargent par `config/load.py`."""
    copie = tmp_path / "copie"
    (copie / "report").mkdir(parents=True)
    (copie / "report" / "pareto.csv").write_text(
        "front,config_id,x,y\nqualite-cout,a,1,0.5\nqualite-cout,b,2,0.9\n", encoding="utf-8"
    )
    resolue = yaml.safe_load((run_dir / "experiment.resolved.yaml").read_text(encoding="utf-8"))
    (modele,) = [c for c in resolue["configurations"] if c["architecture"] == "bm25_only"]
    assert modele["params"]["chunker"]["params"]  # Composant imbriqué, params non triviaux
    modele["params"]["k"] = 3
    resolue["configurations"] = [
        {**modele, "id": "a", "reuse_index": "cle-index-0123"},
        {**modele, "id": "b", "reuse_index": None},
    ]
    (copie / "experiment.resolved.yaml").write_text(yaml.safe_dump(resolue), encoding="utf-8")
    vers = tmp_path / "x.yaml"
    assert exporter_front(copie, "qualite-cout", vers) == ["a", "b"]
    contenu = yaml.safe_load(vers.read_text(encoding="utf-8"))["configurations"]
    exportees = {c["id"]: c for c in contenu}
    assert exportees["a"]["reuse_index"] == "cle-index-0123"
    assert "reuse_index" not in exportees["b"]
    chemin = tmp_path / "reprise.yaml"
    chemin.write_text(
        yaml.safe_dump({**DONNEES, "experiment_id": "exp-reprise", "configurations": contenu}),
        encoding="utf-8",
    )
    rechargees = {c.id: c for c in load_experiment(chemin).configurations}
    assert rechargees["a"].reuse_index == "cle-index-0123"
    assert rechargees["a"].params == modele["params"]
    assert rechargees["a"].parser.name == "auto"


def test_wl_rapport_regenere_pareto_csv_identique(
    run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WL_HOME", str(run_dir.parents[1]))
    avant = (run_dir / "report" / "pareto.csv").read_bytes()
    assert _wl(run_dir).exit_code == 0
    assert (run_dir / "report" / "pareto.csv").read_bytes() == avant
    assert b"\r" not in avant
