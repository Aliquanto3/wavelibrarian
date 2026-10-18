"""Story 4.12 : Rapport, coûts, énergie, latence, débit et point mort (traces écrites à la main)."""

import csv
import dataclasses
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import Answer
from wavelibrarian.measure.tco import possession_cost
from wavelibrarian.report.couts import calculer_couts, quantile
from wavelibrarian.report.generer import construire_markdown, generer_rapport
from wavelibrarian.report.lecture import Execution, charger
from wavelibrarian.report.scores import QUALITE, LignePaire, Resultats

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
USD = Decimal("0.8938")


@pytest.fixture
def run_dir(tmp_path: Path, wl_home: Path) -> Path:
    donnees = {
        "experiment_id": "exp-4-12",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "max_questions": 4,
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": [{"id": "bm25", "architecture": "bm25_only"}],
    }
    chemin = tmp_path / "exp.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    res = CliRunner().invoke(app, ["run", str(chemin)])
    assert res.exit_code == 0, res.output
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return dossier


def _span(config: str, post: str, **attrs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "generate",
        "start_time": 0,
        "end_time": 0,
        "wl.config_id": config,
        "wl.condition": "standard",
        "wl.phase": "base",
        "wl.post": post,
        "wl.kind": "llm",
        "wl.cost": "0",
        "wl.cost_uncached": "0",
        "wl.currency": "USD",
        "wl.llm_cache_hit": False,
        "wl.latency_s": 0.0,
    }
    return base | attrs


def _ex(run_dir: Path, tmp_path: Path, spans: list[dict[str, Any]], reponses: dict[str, int]):
    """Exécution dont les traces et les Réponses sont écrites à la main (config -> n Réponses)."""
    dossier = Path(tempfile.mkdtemp(dir=tmp_path))
    (dossier / "traces.jsonl").write_text(
        "".join(json.dumps(s) + "\n" for s in spans), encoding="utf-8"
    )
    answers = {
        f"{c}-{i}": Answer(
            answer_id=f"{c}-{i}",
            question_id=f"q{i}",
            config_id=c,
            status="ok",
            text="",
            abstained=False,
            latency_s=float(i + 1),
        )  # fmt: skip
        for c, n in reponses.items()
        for i in range(n)
    }
    return dataclasses.replace(charger(run_dir), run_dir=dossier, reponses=answers)


def _paire(a: str, b: str, diff: float | None, p: float | None) -> LignePaire:
    return LignePaire(a, b, QUALITE, diff, p, "mcnemar_exact", 10, "standard", None, "base")


def _res(*paires: LignePaire) -> Resultats:
    return Resultats(paires=list(paires))


# --- AC 1 : costs.csv et somme des wl.cost ---------------------------------------------------


def test_costs_csv_colonnes_et_somme_des_wl_cost_convertie(run_dir: Path) -> None:
    generer_rapport(run_dir)
    with (run_dir / "report" / "costs.csv").open(encoding="utf-8", newline="") as f:
        lignes = list(csv.DictReader(f))
    assert list(lignes[0])[:8] == [
        "config_id", "post", "cost_eur_real", "cost_eur_uncached", "kwh_measured",
        "kwh_estimated", "co2e_g", "n_calls",
    ]  # fmt: skip
    assert {x["post"] for x in lignes} >= {"indexing", "query"}
    md = (run_dir / "report" / "report.md").read_text(encoding="utf-8")
    assert "Taux de change daté du" in md and "Coût de possession" in md


def test_somme_des_couts_convertie_egale_le_total_affiche(run_dir: Path, tmp_path: Path) -> None:
    spans = [
        _span("a", "indexing", **{"wl.cost": "1.00", "wl.cost_uncached": "1.50"}),
        _span("a", "query", **{"wl.cost": "0.10", "wl.cost_uncached": "0.30"}),
        _span("a", "query", **{"wl.cost": "0.15", "wl.currency": "EUR"}),
        _span("a", "judging", **{"wl.cost": "0.05"}),
        _span("a", "evalset", **{"wl.cost": "0.07"}),
    ]
    ex = _ex(run_dir, tmp_path, spans, {"a": 2})
    couts = calculer_couts(ex, _res())
    attendu = (
        Decimal("1.00") * USD
        + Decimal("0.10") * USD
        + Decimal("0.15")
        + Decimal("0.05") * USD
        + Decimal("0.07") * USD
    )
    assert couts.total_api() == attendu
    md = construire_markdown(ex, _res(), couts)
    assert f"{float(attendu):.4f}".replace(".", ",") + " €" in md
    # judging et evalset hors coût d'une Configuration
    assert couts.total_configuration("a", "standard", None) == (
        Decimal("1.00") * USD + Decimal("0.10") * USD + Decimal("0.15")
    )
    assert "Postes hors Configuration" in md
    ligne = next(x for x in couts.lignes if x.cle[4] == "indexing")
    assert ligne.uncached == Decimal("1.50") * USD


def test_devise_inconnue_est_une_erreur_de_configuration(run_dir: Path, tmp_path: Path) -> None:
    ex = _ex(run_dir, tmp_path, [_span("a", "query", **{"wl.currency": "JPY"})], {"a": 1})
    with pytest.raises(ConfigError):
        calculer_couts(ex, _res())


def test_possession_du_calcul_local_hors_hits_et_reprises(run_dir: Path, tmp_path: Path) -> None:
    local = {"wl.kind": "local", "wl.energy_kwh": 0.002, "wl.energy_method": "measured"}
    spans = [
        _span("a", "query", **local, **{"wl.latency_s": 3.0}),
        _span("a", "query", **local, **{"wl.latency_s": 99.0, "wl.llm_cache_hit": True}),
        _span("a", "query", **local, **{"wl.latency_s": 50.0, "wl.resumed": True}),
    ]
    ex = _ex(run_dir, tmp_path, spans, {"a": 1})
    (ligne,) = calculer_couts(ex, _res()).lignes
    attendu = possession_cost(ex.experience.costs, kwh=0.004, compute_seconds=3.0, index_gb=0)
    assert ligne.possession == attendu > 0
    assert ligne.real == ligne.api_real + attendu
    assert ligne.n_calls == 0  # spans `local` : pas des appels ; le span `resumed` est ignoré


# --- AC 2 : énergie ----------------------------------------------------------------------------


def test_energie_mesuree_et_estimee_jamais_additionnees(run_dir: Path, tmp_path: Path) -> None:
    spans = [
        _span("a", "query", **{"wl.energy_kwh": 0.5, "wl.energy_method": "estimated"}),
        _span("a", "query", **{"wl.energy_kwh": 0.25, "wl.energy_method": "estimated"}),
        _span("a", "query", **{"wl.energy_kwh": 2.0, "wl.energy_method": "measured"}),
        _span("a", "query", **{"wl.energy_method": "unknown"}),
        _span(
            "a",
            "query",
            **{"wl.energy_kwh": 9.0, "wl.energy_method": "estimated", "wl.resumed": True},
        ),
    ]  # fmt: skip
    ex = _ex(run_dir, tmp_path, spans, {"a": 1})
    couts = calculer_couts(ex, _res())
    (ligne,) = couts.lignes
    assert (ligne.kwh_estimated, ligne.kwh_measured) == (Decimal("0.75"), Decimal(2))
    gco2 = ex.experience.costs.carbon.gco2e_per_kwh
    assert ligne.co2e_estimated_g == Decimal("0.75") * gco2
    assert ligne.co2e_measured_g == Decimal(2) * gco2
    assert ligne.n_calls == 4  # le span `resumed` n'est pas recompté
    md = construire_markdown(ex, _res(), couts)
    assert "jamais additionnées" in md and "ne se comparent pas" in md
    assert "kWh mesurés" in md and "kWh estimés" in md
    assert f"{float(Decimal(2) * gco2):.3f}".replace(".", ",") in md  # 39,200 g mesurés


# --- AC 3 : latence, débit, coût par requête ---------------------------------------------------


def test_quantiles_par_interpolation_lineaire() -> None:
    assert quantile([], 0.5) is None
    assert quantile([4.0], 0.95) == 4.0
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)
    assert quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95) == pytest.approx(4.8)


def test_latence_debit_et_cout_par_requete(run_dir: Path, tmp_path: Path) -> None:
    mn = 60_000_000_000
    spans = [
        _span("a", "query", start_time=0, end_time=mn, **{"wl.cost": "0.20"}),
        # un hit du cache ne compte pas dans la durée murale : ses bornes sont fictives
        _span(
            "a",
            "query",
            start_time=0,
            end_time=3 * mn,
            **{"wl.llm_cache_hit": True, "wl.cost": "0", "wl.cost_uncached": "0.20"},
        ),
        _span("a", "query", start_time=0, end_time=10 * mn, **{"wl.resumed": True}),
    ]  # fmt: skip
    ex = _ex(run_dir, tmp_path, spans, {"a": 3})
    (lat,) = calculer_couts(ex, _res()).latences
    assert lat.n == 3 and lat.p50 == 2.0 and lat.p95 == pytest.approx(2.9)
    # fenêtre de 0 à 3 min : le hit n'ouvre pas la fenêtre et le span repris est ignoré
    assert lat.debit_qpm == pytest.approx(3 / 3.0)
    assert lat.cout_requete == (Decimal("0.20") * USD) / 3  # un hit ne coûte rien
    assert lat.cout_1000 == (lat.cout_requete or 0) * 1000


def test_debit_absent_sans_duree(run_dir: Path, tmp_path: Path) -> None:
    ex = _ex(run_dir, tmp_path, [_span("a", "query")], {"a": 2})
    (lat,) = calculer_couts(ex, _res()).latences
    assert lat.debit_qpm is None
    assert "n/a" in construire_markdown(ex, _res(), calculer_couts(ex, _res()))


# --- AC 4 : point mort -------------------------------------------------------------------------


def _deux_configs(cout_a: str, cout_b: str) -> list[dict[str, Any]]:
    return [
        _span("a", "indexing", **{"wl.cost": "1.00"}),
        _span("b", "indexing", **{"wl.cost": "0.00"}),
        *(_span("a", "query", **{"wl.cost": cout_a}) for _ in range(2)),
        *(_span("b", "query", **{"wl.cost": cout_b}) for _ in range(2)),
    ]


def test_point_mort_a_qualite_egale(run_dir: Path, tmp_path: Path) -> None:
    ex = _ex(run_dir, tmp_path, _deux_configs("0.10", "0.30"), {"a": 2, "b": 2})
    couts = calculer_couts(ex, _res(_paire("a", "b", 0.0, 1.0)))
    (pm,) = couts.points_morts
    assert (pm.config_a, pm.config_b, pm.n_star) == ("a", "b", 5)  # 1,00 ÷ (0,30 − 0,10)
    md = construire_markdown(ex, _res(), couts)
    assert "| `a` | `b` | all | 5 |" in md


def test_point_mort_paire_orientee_dans_l_autre_sens(run_dir: Path, tmp_path: Path) -> None:
    # La paire est stockée (b, a) : diff = Qualité b − Qualité a = −0,3, mais p ≥ 0,05 -> égale.
    ex = _ex(run_dir, tmp_path, _deux_configs("0.10", "0.30"), {"a": 2, "b": 2})
    (pm,) = calculer_couts(ex, _res(_paire("b", "a", -0.3, 0.2))).points_morts
    assert pm.n_star == 5
    # a significativement meilleure (b − a < 0, p < 0,05) : point mort calculé.
    (pm,) = calculer_couts(ex, _res(_paire("b", "a", -0.3, 0.01))).points_morts
    assert pm.n_star == 5
    # a significativement inférieure (b − a > 0, p < 0,05) : la raison.
    (pm,) = calculer_couts(ex, _res(_paire("b", "a", 0.3, 0.01))).points_morts
    assert pm.n_star is None and "significativement inférieure" in pm.raison


def test_point_mort_raisons_au_lieu_d_un_nombre(run_dir: Path, tmp_path: Path) -> None:
    ex = _ex(run_dir, tmp_path, _deux_configs("0.10", "0.30"), {"a": 2, "b": 2})
    (pm,) = calculer_couts(ex, _res(_paire("a", "b", -0.5, 0.001))).points_morts
    assert pm.n_star is None and "significativement inférieure" in pm.raison
    md = construire_markdown(ex, _res(), calculer_couts(ex, _res(_paire("a", "b", -0.5, 0.001))))
    assert "aucun : Qualité de A significativement inférieure" in md
    # requête_A >= requête_B
    ex2 = _ex(run_dir, tmp_path, _deux_configs("0.30", "0.10"), {"a": 2, "b": 2})
    (pm,) = calculer_couts(ex2, _res(_paire("a", "b", 0.0, 1.0))).points_morts
    assert pm.n_star is None and "coût par requête" in pm.raison
    # aucune Question commune : jamais de « Qualité égale » déduite
    (pm,) = calculer_couts(ex, _res(_paire("a", "b", None, None))).points_morts
    assert pm.n_star is None and "aucune Question commune" in pm.raison
    (pm,) = calculer_couts(ex, _res()).points_morts
    assert pm.n_star is None and "aucune Question commune" in pm.raison


def test_aucun_point_mort_sans_indexation_plus_chere(run_dir: Path, tmp_path: Path) -> None:
    spans = [_span("a", "query"), _span("b", "query")]
    ex = _ex(run_dir, tmp_path, spans, {"a": 1, "b": 1})
    couts = calculer_couts(ex, _res())
    assert couts.points_morts == []
    assert "Aucune paire où une Configuration coûte plus cher" in construire_markdown(
        ex, _res(), couts
    )


def test_traces_absentes_sont_signalees(run_dir: Path, tmp_path: Path) -> None:
    ex = _ex(run_dir, tmp_path, [], {})
    (ex.run_dir / "traces.jsonl").unlink()
    couts = calculer_couts(ex, _res())
    assert not couts.traces_presentes
    assert "`traces.jsonl` absent" in construire_markdown(ex, _res(), couts)


def test_wl_rapport_regenere_costs_csv_identique(run_dir: Path) -> None:
    generer_rapport(run_dir)
    avant = (run_dir / "report" / "costs.csv").read_bytes()
    res = CliRunner().invoke(app, ["rapport", run_dir.name])
    assert res.exit_code == 0, res.output
    assert (run_dir / "report" / "costs.csv").read_bytes() == avant
    assert isinstance(charger(run_dir), Execution)


# --- Revue -------------------------------------------------------------------------------------


def test_reprise_ne_recompte_pas_le_cout_hors_cache(run_dir: Path, tmp_path: Path) -> None:
    # Appel d'origine payé, puis le même appel refait à la reprise : hit du cache `wl.resumed`.
    spans = [
        _span("a", "query", **{"wl.cost": "0.10", "wl.cost_uncached": "0.10"}),
        _span(
            "a",
            "query",
            **{
                "wl.cost": "0",
                "wl.cost_uncached": "0.10",
                "wl.llm_cache_hit": True,
                "wl.resumed": True,
            },
        ),
    ]  # fmt: skip
    (ligne,) = calculer_couts(_ex(run_dir, tmp_path, spans, {"a": 1}), _res()).lignes
    assert ligne.api_real == ligne.api_uncached == Decimal("0.10") * USD
    assert ligne.n_calls == 1


def test_cout_illisible_compte_et_signale(run_dir: Path, tmp_path: Path) -> None:
    spans = [
        _span("a", "query", **{"wl.cost": "0.10"}),
        _span("a", "query", **{"wl.cost": "abc", "wl.cost_uncached": "NaN"}),
    ]
    ex = _ex(run_dir, tmp_path, spans, {"a": 1})
    couts = calculer_couts(ex, _res())
    assert couts.valeurs_invalides == 2
    assert couts.total_api() == Decimal("0.10") * USD
    assert "2 coût(s) illisible(s)" in construire_markdown(ex, _res(), couts)


def test_cout_par_requete_compte_les_echecs_payes(run_dir: Path, tmp_path: Path) -> None:
    # Deux Questions tracées au Poste query, une seule Réponse `ok` : l'échec payé reste dû.
    spans = [_span("a", "query", **{"wl.cost": "0.10"}) for _ in range(2)]
    ex = _ex(run_dir, tmp_path, spans, {"a": 2})
    rep = dict(ex.reponses)
    rep["a-1"] = rep["a-1"].model_copy(update={"status": "error"})
    ex = dataclasses.replace(ex, reponses=rep)
    (lat,) = calculer_couts(ex, _res()).latences
    assert lat.n == 1
    assert lat.cout_requete == Decimal("0.20") * USD
