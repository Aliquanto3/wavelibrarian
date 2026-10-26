"""Story 4.11 : Rapport, scores, recherche et comparaisons appariées (profil `test`, Faux LLM)."""

import csv
import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from scipy.stats import binomtest
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.jsonl import lire_jsonl, terminer_ligne
from wavelibrarian.report.ancrages import resolveur_de
from wavelibrarian.report.generer import construire_markdown, generer_rapport
from wavelibrarian.report.lecture import charger, lire_panel, lire_reponses
from wavelibrarian.report.scores import LignePaire, evaluer
from wavelibrarian.runner.execute import load_questions, run_experiment
from wavelibrarian.runner.rundir import JsonlWriter, read_answers
from wavelibrarian.scoring.retrieval import retrieval_metrics
from wavelibrarian.stats.bootstrap import bootstrap_ci, graine_derivee

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
BM25 = {"id": "bm25", "architecture": "bm25_only"}
SANS_CONTEXTE = {"id": "sans-contexte", "architecture": "no_context"}
N = 12


def _experience(tmp_path: Path, nom: str = "exp", **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-4-11",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "max_questions": N,
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": [SANS_CONTEXTE, BM25],
        **champs,
    }
    chemin = tmp_path / f"{nom}.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl(*args: str, code: int = 0) -> Any:
    res = CliRunner().invoke(app, list(args))
    assert res.exit_code == code, res.output
    return res


def _un_run(wl_home: Path) -> Path:
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return dossier


def _csv(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def run_complet(tmp_path: Path, wl_home: Path) -> Path:
    """Exécution terminée : deux Baselines, Conditions standard et contexte parfait."""
    _wl("run", str(_experience(tmp_path, conditions=["standard", "perfect_context"])))
    dossier = _un_run(wl_home)
    # Le Faux LLM donne des verdicts constants : on les varie, de façon déterministe, pour que les
    # taux, les IC et les tests apparies ne soient pas triviaux.
    lignes = [json.loads(x) for x in (dossier / "panel.jsonl").read_text("utf-8").splitlines()]
    for ligne in lignes:
        ligne["verdict"] = int(sha16(ligne["answer_id"], ligne["criterion"]), 16) % 3 != 0
        ligne["tie"] = False
    (dossier / "panel.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in lignes), encoding="utf-8", newline="\n"
    )
    generer_rapport(dossier)
    return dossier


# --- AC 1 : en-tête de report.md et groupement -------------------------------------------------


def test_wl_run_ecrit_le_rapport_complet_avec_l_entete(run_complet: Path) -> None:
    sortie = run_complet / "report"
    assert {p.name for p in sortie.iterdir()} == {
        "report.md",
        "scores.csv",
        "retrieval.csv",
        "pairs.csv",
        "costs.csv",
        "pareto.csv",
    }
    md = (sortie / "report.md").read_text(encoding="utf-8")
    empreinte = (run_complet / "experiment.sha256").read_text(encoding="utf-8").strip()
    manifeste = json.loads((run_complet / "manifest.json").read_text(encoding="utf-8"))
    for attendu in (
        "../experiment.resolved.yaml",
        empreinte,
        "Profil d'exécution : `test`",
        "Partie utilisée : `dev`",
        "Modèles gelés au",
        "## Profil de corpus",
        "## Juges",
        "Juges exclus par la calibration : aucun",
        "## Contexte parfait",
        "## Questions contaminées",
        "## Comparaisons appariées",
        "## Configurations inapplicables",
        *(f"`{m}`" for m in manifeste["models"]),
    ):
        assert attendu in md, attendu
    # Le Panel admissible figure par Configuration, avec le nombre d'égalités.
    assert "`fake-llm-b`" in md and "`fake-llm-c`" in md and "Égalités" in md


def test_rapport_regenere_identique_wl_rapport(run_complet: Path, wl_home: Path) -> None:
    avant = {p.name: p.read_bytes() for p in (run_complet / "report").iterdir()}
    _wl("rapport", run_complet.name)
    apres = {p.name: p.read_bytes() for p in (run_complet / "report").iterdir()}
    assert avant == apres  # graines dérivées : mêmes IC et mêmes p-valeurs
    _wl("rapport", "inconnu", code=2)
    _wl("rapport", "../x", code=2)


# --- AC 2 : scores.csv -------------------------------------------------------------------------


def test_scores_csv_colonnes_et_valeurs_recalculees(run_complet: Path) -> None:
    lignes = _csv(run_complet / "report" / "scores.csv")
    assert list(lignes[0]) == [
        "config_id", "condition", "tier", "phase", "question_type", "criterion",
        "value", "ci_low", "ci_high", "n", "n_na",
    ]  # fmt: skip
    ex = charger(run_complet)
    reponses = read_answers(run_complet)
    assert reponses == lire_reponses(run_complet)
    panel = lire_panel(run_complet)
    attendues = 0
    for ligne in lignes:
        groupe = (ligne["config_id"], ligne["condition"], ligne["phase"])
        choisies = [
            a
            for a in reponses.values()
            if (a.config_id, a.condition, a.phase) == groupe
            and a.status == "ok"
            and (ligne["question_type"] in ("all", ex.jeu[a.question_id].type))
        ]
        if ligne["criterion"] == "quality":
            bruts = [
                panel[
                    (
                        a.answer_id,
                        "abstention_correctness"
                        if ex.jeu[a.question_id].type == "unanswerable"
                        else "correctness",
                    )
                ].verdict
                for a in choisies
            ]
        else:
            bruts = [panel[(a.answer_id, ligne["criterion"])].verdict for a in choisies]
        valeurs = [v == "yes" for v in bruts if v != "na"]  # taux hors `na` (story 9.3)
        assert int(ligne["n_na"]) == bruts.count("na")
        assert int(ligne["n"]) == len(valeurs) > 0
        assert float(ligne["value"]) == pytest.approx(sum(valeurs) / len(valeurs), abs=1e-6)
        ic = bootstrap_ci(
            [float(v) for v in valeurs],
            seed=graine_derivee(
                42,
                ligne["config_id"],
                ligne["condition"],
                ligne["tier"],
                ligne["phase"],
                ligne["question_type"],
                ligne["criterion"],
            ),
        )
        assert ic is not None
        assert float(ligne["ci_low"]) == pytest.approx(ic.low, abs=1e-6)
        assert float(ligne["ci_high"]) == pytest.approx(ic.high, abs=1e-6)
        attendues += 1
    assert attendues == len(lignes)
    criteres = {ligne["criterion"] for ligne in lignes}
    assert criteres == {
        "quality", "correctness", "completeness", "faithfulness",
        "citation_correctness", "abstention_correctness",
    }  # fmt: skip
    assert {ligne["tier"] for ligne in lignes} == {"all"}
    assert {ligne["condition"] for ligne in lignes} == {"standard", "perfect_context"}


def test_qualite_unanswerable_suit_abstention_correctness(run_complet: Path) -> None:
    lignes = _csv(run_complet / "report" / "scores.csv")
    ex = charger(run_complet)
    if not any(q.type == "unanswerable" for q in ex.jeu.values()):
        pytest.skip("pas de Question unanswerable dans l'échantillon")
    par = {(r["config_id"], r["condition"], r["question_type"], r["criterion"]): r for r in lignes}
    for config in ("bm25", "sans-contexte"):
        qualite = par.get((config, "standard", "unanswerable", "quality"))
        abstention = par.get((config, "standard", "unanswerable", "abstention_correctness"))
        if qualite and abstention:
            assert qualite["value"] == abstention["value"]


# --- AC 3 : contaminées et contexte parfait à part ---------------------------------------------


def test_questions_contaminees_exclues_des_scores_principaux(run_complet: Path) -> None:
    ex = charger(run_complet)
    reference = evaluer(ex, resolveur_de(ex.experience, run_complet.parent.parent))
    contaminee = next(
        q for q in ex.jeu.values() if q.type != "unanswerable" and q.id in _ids_repondus(ex)
    )
    ex.jeu[contaminee.id] = contaminee.model_copy(update={"contaminated_by": ("fake-llm-a",)})
    res = evaluer(ex, resolveur_de(ex.experience, run_complet.parent.parent))
    avant = {(s.groupe, s.question_type, s.critere): s.n for s in reference.scores}
    apres = {(s.groupe, s.question_type, s.critere): s.n for s in res.scores}
    tout = {(g, "all", "quality") for g in reference.comptes}
    assert all(apres[c] == avant[c] - 1 for c in tout)
    assert all(c.contaminees == 1 for c in res.comptes.values())
    assert {r.groupe for r in res.contaminees} == set(res.comptes)
    # Ni les métriques de recherche ni les paires ne la comptent.
    n_avant = {(r.groupe, r.question_type, r.metric): r.n for r in reference.recherche}
    n_apres = {(r.groupe, r.question_type, r.metric): r.n for r in res.recherche}
    assert all(n_apres.get(c, 0) <= n for c, n in n_avant.items())
    md = construire_markdown(ex, res)
    section = md.split("## Questions contaminées")[1].split("\n## ")[0]
    assert "exclues de tous les scores" in section and "| `bm25` |" in section
    assert "Aucune Réponse à une Question contaminée" not in section


def _ids_repondus(ex: Any) -> set[str]:
    return {a.question_id for a in ex.reponses.values() if a.status == "ok"}


def test_contexte_parfait_a_sa_propre_section_etiquetee(run_complet: Path) -> None:
    md = (run_complet / "report" / "report.md").read_text(encoding="utf-8")
    scores = md.split("## Scores")[1].split("\n## ")[0]
    parfait = md.split("## Contexte parfait")[1].split("\n## ")[0]
    assert "contexte parfait" in parfait.lower()
    assert "| `bm25` | all | base | " in scores and "| `bm25` | all | base | " in parfait
    # La Condition standard ne contient pas les lignes de contexte parfait, et inversement.
    assert len(scores.split("| `bm25` |")) == 2 and len(parfait.split("| `bm25` |")) == 2


# --- AC 4 : retrieval.csv et pairs.csv ---------------------------------------------------------


def test_retrieval_csv_sans_no_context_avec_methode_et_valeurs_a_la_main(
    run_complet: Path,
) -> None:
    lignes = _csv(run_complet / "report" / "retrieval.csv")
    assert list(lignes[0]) == [
        "config_id", "condition", "tier", "phase", "question_type", "metric", "k",
        "value", "ci_low", "ci_high", "n", "method",
    ]  # fmt: skip
    assert "sans-contexte" not in {ligne["config_id"] for ligne in lignes}
    assert {ligne["metric"] for ligne in lignes} == {"recall", "mrr", "ndcg"}
    assert {ligne["condition"] for ligne in lignes} == {"standard"}  # contexte parfait : tautologie
    assert {ligne["method"] for ligne in lignes} == {"ranked"}
    # Recalcul indépendant du rappel@5 de bm25 en Condition standard.
    ex = charger(run_complet)
    resoudre = resolveur_de(ex.experience, run_complet.parent.parent)
    rappels = []
    for a in ex.reponses.values():
        if a.config_id != "bm25" or a.condition != "standard" or a.status != "ok":
            continue
        s = retrieval_metrics(
            a.retrieved, resoudre("bm25", a.phase, ex.jeu[a.question_id]), a.retrieval_method
        )
        if s.recall is not None:
            rappels.append(s.recall)
    ligne = next(
        r
        for r in lignes
        if (r["config_id"], r["condition"], r["question_type"], r["metric"])
        == ("bm25", "standard", "all", "recall")
    )
    assert int(ligne["n"]) == len(rappels) and float(ligne["k"]) == 5
    assert float(ligne["value"]) == pytest.approx(sum(rappels) / len(rappels), abs=1e-6)


def test_pairs_csv_mcnemar_exact_et_bootstrap_apparie(run_complet: Path) -> None:
    lignes = _csv(run_complet / "report" / "pairs.csv")
    assert list(lignes[0])[:7] == [
        "config_a", "config_b", "metric", "diff", "p_value", "test", "n_common",
    ]  # fmt: skip
    assert {(r["config_a"], r["config_b"]) for r in lignes} == {("bm25", "sans-contexte")}
    qualite = next(r for r in lignes if r["metric"] == "quality" and r["condition"] == "standard")
    assert qualite["test"] == "mcnemar_exact"
    ex = charger(run_complet)
    panel = lire_panel(run_complet)

    def oui(config: str, qid: str) -> bool:
        a = next(
            r
            for r in ex.reponses.values()
            if (r.config_id, r.condition, r.question_id) == (config, "standard", qid)
        )
        critere = "abstention_correctness" if ex.jeu[qid].type == "unanswerable" else "correctness"
        return panel[(a.answer_id, critere)].verdict == "yes"

    ids = sorted({a.question_id for a in ex.reponses.values()})
    b = sum(oui("bm25", q) and not oui("sans-contexte", q) for q in ids)
    c = sum(oui("sans-contexte", q) and not oui("bm25", q) for q in ids)
    attendu = 1.0 if b + c == 0 else float(binomtest(min(b, c), b + c, 0.5).pvalue)
    assert int(qualite["n_common"]) == len(ids)
    assert float(qualite["p_value"]) == pytest.approx(attendu, abs=1e-6)
    assert float(qualite["diff"]) == pytest.approx((b - c) / len(ids), abs=1e-6)
    continues = [r for r in lignes if r["metric"] in ("recall", "mrr", "ndcg")]
    assert all(r["test"] == "bootstrap_apparie" for r in continues)
    # no_context n'a pas de métrique de recherche : aucune paire continue avec lui.
    assert all(int(r["n_common"]) == 0 and r["diff"] == "" for r in continues)


def test_rapport_signale_l_absence_de_correction_de_multiplicite(run_complet: Path) -> None:
    md = (run_complet / "report" / "report.md").read_text(encoding="utf-8")
    assert "Multiplicité" in md and "Aucune correction" in md


def test_paire_sans_question_commune_n_a_pas_de_p_valeur(run_complet: Path) -> None:
    ex = charger(run_complet)
    res = evaluer(ex, resolveur_de(ex.experience, run_complet.parent.parent))
    vides = [p for p in res.paires if p.n_common == 0]
    assert vides and all(p.diff is None and p.p_value is None for p in vides)
    assert all(isinstance(p, LignePaire) for p in res.paires)
    md = construire_markdown(ex, res)
    assert "donc aucune « Qualité égale » n'en est déduite" in md


# --- AC 5 : inapplicables ----------------------------------------------------------------------


def test_inapplicables_listees_avec_leur_raison(tmp_path: Path, wl_home: Path) -> None:
    confs = [
        BM25,
        {
            "id": "contexte-long",
            "architecture": "long_context",
            "params": {"generator": {"name": "llm", "params": {"max_tokens": 99000}}},
        },
    ]
    _wl("run", str(_experience(tmp_path, configurations=confs, max_questions=4)))
    dossier = _un_run(wl_home)
    raison = json.loads((dossier / "applicability.json").read_text(encoding="utf-8"))[
        "contexte-long"
    ]["reason"]
    md = (dossier / "report" / "report.md").read_text(encoding="utf-8")
    section = md.split("## Configurations inapplicables")[1].split("\n## ")[0]
    assert "`contexte-long`" in section and raison in section
    # Les Réponses `inapplicable` ne sont ni notées ni comptées dans n.
    comptes = md.split("## Réponses non notées")[1]
    assert "| `contexte-long` | all | base | standard | 0 | 0 | 4 | 0 | 0 |" in comptes


# --- AC 6 : plafond ----------------------------------------------------------------------------


def _plafond_pour(tmp_path: Path, n: int) -> Decimal:
    probe = tmp_path / "probe_home"
    resolue = validate_file(_experience(tmp_path, "probe")).resolved
    run_experiment(resolue, load_questions(resolue), wl_home=probe)
    conn = sqlite3.connect(probe / "ledger.sqlite")
    try:
        lignes = list(conn.execute("SELECT estimated, actual FROM reservations ORDER BY id"))
    finally:
        conn.close()
    reels = [Decimal(r or "0") for _, r in lignes]
    return sum(reels[:n]) + Decimal(lignes[n][0]) - Decimal("1e-9")


def test_plafond_atteint_rapport_partiel_en_tete_puis_code_3(tmp_path: Path, wl_home: Path) -> None:
    plafond = _plafond_pour(tmp_path, 5)
    chemin = _experience(
        tmp_path,
        "plafonne",
        budget={"per_run": {"fake": {"amount": str(plafond), "currency": "USD"}}},
    )
    res = _wl("run", str(chemin), code=3)
    assert "Rapport écrit dans" in res.output
    dossier = _un_run(wl_home)
    md = (dossier / "report" / "report.md").read_text(encoding="utf-8")
    assert md.split("\n")[2].startswith("> **Exécution arrêtée au plafond de dépense")
    reponses = read_answers(dossier)
    restantes = [a for a in reponses.values() if a.status == "budget_exceeded"]
    assert restantes
    # Aucune Réponse `budget_exceeded` n'entre dans un score.
    ex = charger(dossier)
    res_scores = evaluer(ex, resolveur_de(ex.experience, wl_home))
    assert sum(c.budget_exceeded for c in res_scores.comptes.values()) == len(restantes)
    assert sum(c.ok for c in res_scores.comptes.values()) == 5


# --- Reports : lecteurs, unjudged, wiki --------------------------------------------------------


def test_lecteurs_tolerent_une_derniere_ligne_tronquee_et_l_ajout_la_termine(
    run_complet: Path,
) -> None:
    for nom in ("answers.jsonl", "panel.jsonl", "traces.jsonl"):
        with (run_complet / nom).open("ab") as f:
            f.write(b'{"answer_id": "tronque", "sta')
    avant = read_answers(run_complet)
    assert lire_reponses(run_complet) == avant  # ligne tronquée ignorée, aucune perte
    assert len(lire_panel(run_complet)) == len(lire_jsonl(run_complet / "panel.jsonl"))
    generer_rapport(run_complet)  # le Rapport se génère malgré les lignes tronquées
    # L'ajout suivant ne se colle pas à la ligne tronquée.
    nouvelle = next(iter(avant.values())).model_copy(update={"answer_id": "r/nouvelle"})
    with JsonlWriter(run_complet, "answers.jsonl") as w:
        w.append(nouvelle.model_dump(mode="json"))
    lignes = (run_complet / "answers.jsonl").read_text(encoding="utf-8").split("\n")
    assert lignes[-3].endswith('"sta') and lignes[-2].startswith("{") and lignes[-1] == ""
    apres = read_answers(run_complet)  # la ligne tronquée, terminée, reste ignorée
    assert set(apres) == set(avant) | {"r/nouvelle"}


def test_terminer_ligne_et_ligne_invalide_au_milieu(tmp_path: Path) -> None:
    chemin = tmp_path / "f.jsonl"
    terminer_ligne(chemin)  # fichier absent : rien
    assert not chemin.exists()
    chemin.write_bytes(b'{"a":1}\n{"b":')
    assert lire_jsonl(chemin) == [{"a": 1}]
    terminer_ligne(chemin)
    terminer_ligne(chemin)  # idempotent
    assert chemin.read_bytes() == b'{"a":1}\n{"b":\n'
    chemin.write_bytes(b'{"a":1}\n{"b":\n{"c":2}\n[1]\n')
    assert lire_jsonl(chemin) == [{"a": 1}, {"c": 2}]
    chemin.write_bytes(b'{"a":1}\n{"b":2}\n')
    terminer_ligne(chemin)
    assert chemin.read_bytes() == b'{"a":1}\n{"b":2}\n'


def test_critere_sans_verdict_est_affiche_non_juge(run_complet: Path) -> None:
    lignes = (run_complet / "panel.jsonl").read_text(encoding="utf-8").splitlines()
    (run_complet / "panel.jsonl").write_text("\n".join(lignes[:-3]) + "\n", encoding="utf-8")
    generer_rapport(run_complet)
    md = (run_complet / "report" / "report.md").read_text(encoding="utf-8")
    comptes = md.split("## Réponses non notées")[1]
    derniers = [
        ligne.rstrip(" |").rsplit("|", 1)[-1].strip()
        for ligne in comptes.split("\n## ")[0].splitlines()
        if ligne.startswith("|") and "---" not in ligne
    ]
    assert derniers[0] == "non jugées" and any(x.isdigit() and int(x) > 0 for x in derniers[1:])
    ex = charger(run_complet)
    res = evaluer(ex, resolveur_de(ex.experience, run_complet.parent.parent))
    assert sum(c.non_jugees for c in res.comptes.values()) >= 1


def test_fidelite_du_wiki_branchee_dans_le_rapport(run_complet: Path) -> None:
    (run_complet / "wiki_fidelity.json").write_text(
        json.dumps({"wiki": {"claims": 4, "supported": 3}}), encoding="utf-8"
    )
    generer_rapport(run_complet)
    md = (run_complet / "report" / "report.md").read_text(encoding="utf-8")
    assert "## Fidélité du wiki" in md and "| wiki | 75% |" in md


def test_aucun_score_global_dans_les_colonnes(run_complet: Path) -> None:
    for nom in ("scores.csv", "retrieval.csv", "pairs.csv"):
        entete = next(csv.reader((run_complet / "report" / nom).open(encoding="utf-8")))
        assert not [c for c in entete if "global" in c or "overall" in c or "score" in c]


def test_exporteur_de_traces_termine_la_ligne_tronquee_a_la_reprise(tmp_path: Path) -> None:
    from wavelibrarian.measure.tracing import JsonlSpanExporter

    chemin = tmp_path / "traces.jsonl"
    chemin.write_bytes(b'{"name": "a"}\n{"name": "tr')
    JsonlSpanExporter(chemin)
    assert chemin.read_bytes() == b'{"name": "a"}\n{"name": "tr\n'
    assert lire_jsonl(chemin) == [{"name": "a"}]


# --- Revue : empreinte du Corpus, Ancrages non résolus, UTF-8 tronqué, échec du Rapport ---------


def test_corpus_modifie_depuis_l_execution_recherche_non_mesuree_et_signalee(
    run_complet: Path,
) -> None:
    md = (run_complet / "report" / "report.md").read_text(encoding="utf-8")
    assert "**Attention**" not in md  # Corpus inchangé : aucune alerte
    assert _csv(run_complet / "report" / "retrieval.csv")
    chemin = run_complet / "manifest.json"
    manifeste = json.loads(chemin.read_text(encoding="utf-8"))
    assert manifeste["inputs"]["corpus_fingerprint"]
    manifeste["inputs"]["corpus_fingerprint"] = "0" * 16
    chemin.write_text(json.dumps(manifeste), encoding="utf-8")
    generer_rapport(run_complet)
    md = (run_complet / "report" / "report.md").read_text(encoding="utf-8")
    recherche = md.split("## Recherche")[1]
    assert "Corpus modifié depuis l'Exécution (base)" in recherche
    assert "0000000000000000" in recherche
    assert _csv(run_complet / "report" / "retrieval.csv") == []


def test_ancrage_non_resolu_compte_et_signale(run_complet: Path) -> None:
    from wavelibrarian.core.types import AnchorRef

    ex = charger(run_complet)
    resoudre = resolveur_de(ex.experience, run_complet.parent.parent)
    q = next(q for q in ex.jeu.values() if q.reference_anchors)
    bonne = resoudre("bm25", "base", q)
    assert bonne and resoudre.alertes() == []
    fausse = q.model_copy(
        update={"reference_anchors": (*q.reference_anchors, AnchorRef(doc="absent.md"))}
    )
    assert resoudre("bm25", "base", fausse) == bonne
    resoudre("bm25", "base", fausse)  # comptée une fois par Question
    (alerte,) = resoudre.alertes()
    assert alerte.startswith("1 Question(s) avec au moins un Ancrage de référence non résolu")
    assert q.id in alerte


def test_lire_jsonl_tolere_une_troncature_au_milieu_d_un_caractere_multioctet(
    tmp_path: Path,
) -> None:
    chemin = tmp_path / "f.jsonl"
    chemin.write_bytes('{"a": "é"}\n'.encode() + '{"b": "é'.encode()[:-1])
    assert lire_jsonl(chemin) == [{"a": "é"}]
    chemin.write_bytes(b'{"a": 1}\n{"b": "\xff"}\n{"c": 2}\n')
    assert lire_jsonl(chemin) == [{"a": 1}, {"c": 2}]


def test_echec_du_rapport_ne_masque_pas_le_code_de_l_execution(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def casse(*_: Any, **__: Any) -> Path:
        raise RuntimeError("panne inattendue")

    monkeypatch.setattr("wavelibrarian.cli.generer_rapport", casse)
    plafond = _plafond_pour(tmp_path, 5)
    chemin = _experience(
        tmp_path,
        "plafonne",
        budget={"per_run": {"fake": {"amount": str(plafond), "currency": "USD"}}},
    )
    res = _wl("run", str(chemin), code=3)  # le code du plafond, pas celui du Rapport
    assert "Rapport non généré : RuntimeError: panne inattendue" in res.output
    res = _wl("run", str(_experience(tmp_path, "complet")), code=1)  # completed, Rapport en échec
    assert "Rapport non généré" in res.output


def test_paire_continue_avec_questions_communes(run_complet: Path) -> None:
    """Bootstrap apparié avec `n_common` > 0 : deux Configurations de recherche dont l'une ne
    retrouve qu'une partie des Ancrages (résolveur injecté)."""
    ex = charger(run_complet)
    vrai = resolveur_de(ex.experience, run_complet.parent.parent)
    bm25 = [a for a in ex.reponses.values() if a.config_id == "bm25"]
    # Copie des Réponses bm25 sous un second config_id, même recherche.
    copies = {
        f"{a.answer_id}#b": a.model_copy(update={"answer_id": f"{a.answer_id}#b", "config_id": "b"})
        for a in bm25
    }
    ex.reponses.update(copies)
    for aid, critere_verdict in list(ex.verdicts_par_reponse.items()):
        if f"{aid}#b" in copies:
            ex.verdicts_par_reponse[f"{aid}#b"] = critere_verdict

    def resoudre(config_id: str, phase: Any, q: Any) -> list[str]:
        ids = vrai("bm25", phase, q)
        return ids if config_id == "bm25" else ids[:1] + ["inconnu"]

    res = evaluer(ex, resoudre)
    lignes = {
        p.metric: p
        for p in res.paires
        if {p.config_a, p.config_b} == {"b", "bm25"} and p.condition == "standard"
    }
    rappel = lignes["recall"]
    assert rappel.test == "bootstrap_apparie" and rappel.n_common > 0
    # Oracle : moyenne des écarts par Question, recalculée depuis les Réponses.
    ecarts = []
    for a in bm25:
        if a.condition != "standard":
            continue
        q = ex.jeu[a.question_id]
        sa = retrieval_metrics(
            a.retrieved, resoudre(rappel.config_a, a.phase, q), a.retrieval_method, 5
        )
        sb = retrieval_metrics(
            a.retrieved, resoudre(rappel.config_b, a.phase, q), a.retrieval_method, 5
        )
        if sa.recall is not None and sb.recall is not None:
            ecarts.append(sa.recall - sb.recall)
    assert rappel.n_common == len(ecarts)
    assert rappel.diff == pytest.approx(sum(ecarts) / len(ecarts))
    assert rappel.p_value is not None and 0.0 <= rappel.p_value <= 1.0


def test_exporteur_de_traces_termine_la_ligne_apres_une_ecriture_partielle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian.measure import tracing

    chemin = tmp_path / "traces.jsonl"
    exporteur = tracing.JsonlSpanExporter(chemin)
    ouvrir = Path.open

    def partiel(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if mode == "a":
            with ouvrir(self, "ab") as f:
                f.write(b'{"name": "par')
            raise OSError("disque plein")
        return ouvrir(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", partiel)
    attributs = {"name": "x", "start_time": 0, "end_time": 1, "attributes": {}}
    span: Any = type("S", (), {"get_span_context": lambda _: None, **attributs})()
    assert exporteur.export([span]) == tracing.SpanExportResult.FAILURE
    monkeypatch.setattr(Path, "open", ouvrir)
    assert chemin.read_bytes() == b'{"name": "par\n'
    assert exporteur.export([span]) == tracing.SpanExportResult.SUCCESS
    assert [s["name"] for s in lire_jsonl(chemin)] == ["x"]
