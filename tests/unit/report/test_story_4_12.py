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
        _span("a", "query", **{"wl.energy_kwh": 0.5, "wl.energy_method": "estimated",
                               "wl.energy_source": "windows_emi"}),
        _span("a", "query", **{"wl.energy_kwh": 0.25, "wl.energy_method": "estimated",
                               "wl.energy_source": "windows_emi"}),
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
    assert couts.sources_energie == {"windows_emi": 2, "absent": 1}
    assert "`wl.energy_source`" in md and "`windows_emi` (2)" in md
    assert "compteurs matériels pour toutes les parts suivies" in md
    assert "kWh mesurés" in md and "kWh estimés" in md
    assert f"{float(Decimal(2) * gco2):.3f}".replace(".", ",") in md  # 39,200 g mesurés


def test_energie_mixte_a_part_et_judging_hors_configuration(run_dir: Path, tmp_path: Path) -> None:
    """Story 9.8 : trois colonnes d'énergie, jamais additionnées ; l'énergie `judging` d'un Juge
    local reste au Poste `judging`, possession comprise, hors du coût d'une Configuration."""
    mixte = {"wl.energy_method": "mixed", "wl.energy_source": "windows_emi"}
    spans = [
        _span(
            "a", "query", **mixte,
            **{"wl.kind": "local", "wl.energy_kwh": 0.5, "wl.latency_s": 2.0},
        ),
        _span("a", "query", **{"wl.energy_kwh": 2.0, "wl.energy_method": "measured"}),
        _span("a", "query", **{"wl.energy_kwh": 0.25, "wl.energy_method": "estimated"}),
        _span(
            "a", "judging", **{"gen_ai.provider.name": "ollama"}, **mixte,
            **{"wl.kind": "llm", "wl.energy_kwh": 0.125, "wl.latency_s": 4.0},
        ),
    ]  # fmt: skip
    ex = _ex(run_dir, tmp_path, spans, {"a": 1})
    couts = calculer_couts(ex, _res())
    par_poste = {ligne.cle[4]: ligne for ligne in couts.lignes}
    q, j = par_poste["query"], par_poste["judging"]
    assert (q.kwh_mixed, q.kwh_measured, q.kwh_estimated) == (
        Decimal("0.5"), Decimal(2), Decimal("0.25"),
    )  # fmt: skip
    gco2 = ex.experience.costs.carbon.gco2e_per_kwh
    assert q.co2e_mixed_g == Decimal("0.5") * gco2
    assert (j.kwh_mixed, j.kwh_measured, j.kwh_estimated) == (Decimal("0.125"), 0, 0)
    # profil `test` : compteur factice et énergie non `measured`, la possession est fictive
    attendue = possession_cost(ex.experience.costs, kwh=0.125, compute_seconds=4.0, index_gb=0)
    assert j.possession_fake == attendue > 0
    assert couts.total_configuration("a", "standard", None, fictif=True) == q.real + q.fake
    assert j.fake > 0  # le Poste judging pèse, mais hors du total ci-dessus
    md = construire_markdown(ex, _res(), couts)
    assert "Légende de `mixed`" in md and "estimée par formule" in md
    assert "kWh mixtes" in md and "trois colonnes" in md
    assert couts.sources_energie == {"windows_emi": 2, "absent": 2}
    hors = md.split("### Postes hors Configuration")[1].split("### Latence")[0]
    assert "judging" in hors and "0.125000" in hors.replace(",", ".")


def test_costs_csv_ajoute_les_colonnes_mixtes_en_fin(run_dir: Path) -> None:
    from wavelibrarian.report.couts import ENTETE_COUTS, ligne_csv

    assert ENTETE_COUTS[-2:] == ["kwh_mixed", "co2e_g_mixed"]
    assert ENTETE_COUTS[:8] == [
        "config_id", "post", "cost_eur_real", "cost_eur_uncached", "kwh_measured",
        "kwh_estimated", "co2e_g", "n_calls",
    ]  # fmt: skip
    from wavelibrarian.report.couts import LigneCout

    ligne = LigneCout(("a", "standard", None, "base", "query"))
    ligne.kwh_mixed = Decimal("0.5")
    ligne.co2e_mixed_g = Decimal("12.5")
    csv_ligne = ligne_csv(ligne)
    assert len(csv_ligne) == len(ENTETE_COUTS)
    assert csv_ligne[-2:] == ["0.500000000", "12.500000"]


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


# --- Story 8.2 : coûts factices hors du coût réel ----------------------------------------------


def test_cout_reel_exclut_les_spans_fake(run_dir: Path, tmp_path: Path) -> None:
    spans = [
        _span("a", "query", **{"wl.cost": "1.00", "gen_ai.provider.name": "anthropic"}),
        _span("a", "query", **{"wl.cost": "0.20", "gen_ai.provider.name": "ollama"}),
        _span("a", "judging", **{"wl.cost": "5.00", "gen_ai.provider.name": "fake"}),
        _span("a", "query", **{"wl.cost": "0.50", "gen_ai.provider.name": "fake"}),
    ]
    couts = calculer_couts(_ex(run_dir, tmp_path, spans, {"a": 1}), _res())
    assert couts.total_api() == Decimal("1.20") * USD
    assert couts.total_fake() == Decimal("5.50") * USD
    assert not couts.faux_llm_pur
    requete = next(x for x in couts.lignes if x.cle[4] == "query")
    assert requete.api_fake == Decimal("0.50") * USD and requete.real == Decimal("1.20") * USD
    assert requete.uncached == Decimal("0")  # le fake n'entre pas non plus dans le hors-cache
    # le front de coût reste sur le coût réel quand un fournisseur réel est présent
    assert couts.total_configuration("a", "standard", None) == Decimal("1.20") * USD


def test_costs_csv_colonne_fake_separee_et_faux_llm_pur(run_dir: Path) -> None:
    generer_rapport(run_dir)
    with (run_dir / "report" / "costs.csv").open(encoding="utf-8", newline="") as f:
        lignes = list(csv.DictReader(f))
    assert "cost_eur_fake" in lignes[0]
    # AC 2 : 0 exactement, possession comprise (énergie du compteur factice : possession fictive)
    assert all(Decimal(x["cost_eur_real"]) == 0 == Decimal(x["possession_eur"]) for x in lignes)
    assert sum((Decimal(x["cost_eur_fake"]) for x in lignes), Decimal(0)) > 0
    md = (run_dir / "report" / "report.md").read_text(encoding="utf-8")
    assert "Faux LLM pur" in md and "cost_eur_fake" in md
    with (run_dir / "report" / "pareto.csv").open(encoding="utf-8", newline="") as f:
        x_cout = [float(r["x"]) for r in csv.DictReader(f) if r["front"].startswith("qualite-cout")]
    assert x_cout and max(x_cout) > 0  # le front se calcule sur le coût fictif, non nul


def test_cache_reel_a_cout_nul_n_est_pas_du_faux_llm_pur(run_dir: Path, tmp_path: Path) -> None:
    spans = [
        _span("a", "query", **{"wl.cost": "0", "gen_ai.provider.name": "anthropic",
                               "wl.llm_cache_hit": True}),
        _span("a", "judging", **{"wl.cost": "5.00", "gen_ai.provider.name": "fake"}),
    ]  # fmt: skip
    couts = calculer_couts(_ex(run_dir, tmp_path, spans, {"a": 1}), _res())
    assert couts.spans_reels == 1 and not couts.faux_llm_pur


def test_possession_d_une_energie_factice_hors_du_cout_reel(run_dir: Path, tmp_path: Path) -> None:
    local = {"wl.kind": "local", "wl.energy_kwh": 0.004, "wl.latency_s": 3.0}
    spans = [
        _span("a", "indexing", **local, **{"wl.energy_method": "estimated"}),
        _span("a", "query", **{"wl.cost": "0.50", "gen_ai.provider.name": "fake"}),
    ]
    ex = _ex(run_dir, tmp_path, spans, {"a": 1})  # profil `test` : compteur local factice
    couts = calculer_couts(ex, _res())
    possession = possession_cost(ex.experience.costs, kwh=0.004, compute_seconds=3.0, index_gb=0)
    assert couts.total_reel() == 0 and couts.total_possession() == 0
    assert couts.total_fake() == Decimal("0.50") * USD + possession
    assert couts.faux_llm_pur
    (lat,) = couts.latences  # coût par requête sur le fictif en Faux LLM pur
    assert lat.cout_requete == Decimal("0.50") * USD
    # une énergie `measured` (compteur matériel) reste réelle, même en profil `test`
    spans[0]["wl.energy_method"] = "measured"
    couts = calculer_couts(_ex(run_dir, tmp_path, spans, {"a": 1}), _res())
    assert couts.total_possession() == possession and not couts.faux_llm_pur
