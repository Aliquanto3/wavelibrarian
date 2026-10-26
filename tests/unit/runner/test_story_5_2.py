"""Story 5.2 : `wl calibrer`, exclusion des Juges (profil `test`, Faux LLM, aucun réseau)."""

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.components.judges.llm import LLMJudge
from wavelibrarian.config.panel import excluded_judges
from wavelibrarian.core.errors import NonConformantOutput, ProviderError
from wavelibrarian.core.types import Criterion
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions
from wavelibrarian.ports.components import JudgeInput
from wavelibrarian.runner.rundir import read_answers
from wavelibrarian.scoring.panel import criteres_juges

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
BM25 = {"id": "bm25", "architecture": "bm25_only"}
Scenario = Callable[[str, int, str, bool], bool]  # (juge, passe, critère, verdict humain)


def _questions() -> dict[str, Any]:
    return {q.id: q for q in select_questions(io.load(RACINE / "questions.yaml"), "dev")}


def _experience(tmp_path: Path, nom: str = "exp.yaml", **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-5-2",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": [BM25],
        **champs,
    }
    chemin = tmp_path / nom
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


@pytest.fixture
def execution(tmp_path: Path, wl_home: Path) -> tuple[Path, Path]:
    """Une Exécution terminée au profil `test` : (experience.yaml, dossier de l'Exécution)."""
    exp = _experience(tmp_path)
    res = CliRunner().invoke(app, ["run", str(exp)])
    assert res.exit_code == 0, res.output
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return exp, dossier


def _humain(qid: str, critere: str) -> bool:
    """Annotation de référence, déterministe : une Question sur deux est jugée `yes`."""
    return int(qid.split("-")[1]) % 2 == 0 or critere == "faithfulness"


def _ecrire_annotations(cible: Path, par_annotateur: dict[str, list[dict[str, str]]]) -> None:
    cible.mkdir(exist_ok=True)
    for nom, lignes in par_annotateur.items():
        texte = yaml.safe_dump({"annotator": nom, "annotations": lignes}, allow_unicode=True)
        (cible / f"{nom}.yaml").write_text(texte, encoding="utf-8")


def _annoter(
    dossier: Path, cible: Path, *, doubles: int = 6, bruno_inverse: bool = False
) -> list[str]:
    """Deux annotateurs ; `bruno` annote les `doubles` premières Réponses (par `answer_id`)."""
    questions = _questions()
    reponses = sorted(read_answers(dossier).values(), key=lambda a: a.answer_id)
    par: dict[str, list[dict[str, str]]] = {"anael": [], "bruno": []}
    for n, a in enumerate(reponses):
        for c in criteres_juges(questions[a.question_id]):
            v = _humain(a.question_id, c)
            ligne = {"answer_id": a.answer_id, "criterion": c}
            par["anael"].append({**ligne, "verdict": "yes" if v else "no"})
            if n < doubles:
                w = (not v) if bruno_inverse and c == "completeness" else v
                par["bruno"].append({**ligne, "verdict": "yes" if w else "no"})
    _ecrire_annotations(cible, par)
    return [a.answer_id for a in reponses]


def _espion(
    monkeypatch: pytest.MonkeyPatch, scenario: Scenario | None = None
) -> list[tuple[str, str, int]]:
    """Remplace `LLMJudge.judge` : appels enregistrés (modèle, Question, passe), verdicts
    scénarisés ; sans scénario, le vrai Juge (Faux LLM) répond."""
    appels: list[tuple[str, str, int]] = []
    reel = LLMJudge.judge
    par_texte = {q.text: q.id for q in _questions().values()}

    def juge(self: LLMJudge, item: JudgeInput, criteria: Sequence[Criterion], pass_id: int) -> Any:
        qid = par_texte[item.question]
        appels.append((self.model_id, qid, pass_id))
        if scenario is None:
            return reel(self, item, criteria, pass_id)
        return {
            c: (scenario(self.model_id, pass_id, c, _humain(qid, c)), "scénarisé") for c in criteria
        }

    monkeypatch.setattr(LLMJudge, "judge", juge)
    return appels


def _calibrer(exp: Path, annotations: Path, run: str, *args: str, code: int = 0) -> Any:
    res = CliRunner().invoke(
        app, ["calibrer", str(exp), "--annotations", str(annotations), "--run", run, *args]
    )
    assert res.exit_code == code, res.output
    return res


def _sha(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _b_bon_c_mauvais(juge: str, passe: int, critere: str, humain: bool) -> bool:
    """`fake-llm-b` suit toujours l'humain ; `fake-llm-c` le contredit, sauf à la passe 2."""
    if juge == "fake-llm-b":
        return humain
    return humain if passe == 2 else not humain


# --- AC 1 : cinq passes, pass_id 0 à 4, poste judging, verdicts.jsonl intact ----------------------


def test_cinq_passes_par_juge_et_reponse_annotee_hors_cache(
    execution: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wl_home: Path
) -> None:
    exp, dossier = execution
    ids = _annoter(dossier, tmp_path / "ann")
    avant = _sha(dossier / "verdicts.jsonl")
    appels = _espion(monkeypatch)
    _calibrer(exp, tmp_path / "ann", dossier.name)

    # Producteur fake-llm-a (Famille écartée) : le réservoir admissible est {c, b}.
    assert {a[0] for a in appels} == {"fake-llm-b", "fake-llm-c"}
    questions = {q for _, q, _ in appels}
    assert len(questions) == len(ids)
    for modele in ("fake-llm-b", "fake-llm-c"):
        for qid in questions:
            passes = sorted(p for m, q, p in appels if (m, q) == (modele, qid))
            assert passes == [0, 1, 2, 3, 4]
    assert _sha(dossier / "verdicts.jsonl") == avant  # le Panel de l'Exécution n'est pas touché

    traces = [
        json.loads(ligne)
        for d in (wl_home / "hors-execution").iterdir()
        for ligne in (d / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    juges = [s for s in traces if s["wl.post"] == "judging"]
    assert len(juges) == len(appels)
    # Les passes 1 à 4 ne sont jamais servies par le Cache : 4 appels sur 5 au moins sont réels.
    assert sum(1 for s in juges if not s["wl.llm_cache_hit"]) >= 4 * len(juges) // 5
    lignes = (dossier / "calibration_verdicts.jsonl").read_text(encoding="utf-8").splitlines()
    assert {json.loads(x)["pass_id"] for x in lignes} == {0, 1, 2, 3, 4}


# --- AC 2 : calibration.json -------------------------------------------------------------------


def test_calibration_json_kappa_instabilite_items_et_inter_annotateurs(
    execution: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dossier = execution
    exp = _experience(tmp_path, "exp-seuil.yaml", judges={"kappa_threshold": 0.5})
    _annoter(dossier, tmp_path / "ann", bruno_inverse=True)
    _espion(monkeypatch, _b_bon_c_mauvais)
    _calibrer(exp, tmp_path / "ann", dossier.name)
    d = json.loads((dossier / "calibration.json").read_text(encoding="utf-8"))
    b, c = d["judges"]["fake-llm-b"], d["judges"]["fake-llm-c"]
    assert b["excluded"] is False and c["excluded"] is True
    for f in b["criteria"].values():
        assert f["instability"] == 0.0 and f["n_items"] > 0
    assert b["criteria"]["completeness"]["n_items"] == 19 + 6  # chaque annotateur compte
    assert b["criteria"]["completeness"]["kappa"] < 1.0  # bruno contredit b sur completeness
    assert b["criteria"]["faithfulness"]["kappa"] is None  # humains tous `yes` : indéfini
    assert c["criteria"]["completeness"]["instability"] == 1.0  # la passe 2 s'inverse
    assert c["criteria"]["completeness"]["kappa"] < 0
    (paire,) = d["inter_annotator"]
    assert paire["annotators"] == ["anael", "bruno"]
    assert paire["criteria"]["completeness"]["n_items"] == 6
    assert paire["criteria"]["completeness"]["kappa"] < 0  # bruno inverse tout anael
    assert paire["criteria"]["faithfulness"] == {"kappa": None, "n_items": 6}
    assert "calibration_judge" not in d
    assert excluded_judges(dossier / "calibration.json") == {"fake-llm-c"}


# --- AC 3 : exclusion affichée en français, kappa indéfini signalé --------------------------------


def test_juge_exclu_affiche_en_francais(
    execution: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    _annoter(dossier, tmp_path / "ann")
    _espion(monkeypatch, _b_bon_c_mauvais)
    res = _calibrer(exp, tmp_path / "ann", dossier.name)
    assert "Juge exclu : fake-llm-c (kappa" in res.output and "sous le seuil 0,60" in res.output
    assert "Coût des Juges (Poste judging)" in res.output


def test_kappa_indefini_n_exclut_pas_mais_est_signale(
    execution: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    lignes = [
        {"answer_id": a, "criterion": "faithfulness", "verdict": "yes"}
        for a in read_answers(dossier)
    ]
    _ecrire_annotations(tmp_path / "ann", {"x": lignes})
    _espion(monkeypatch, lambda *_: True)  # accord sur une seule classe : kappa indéfini
    res = _calibrer(exp, tmp_path / "ann", dossier.name, "--sortie", str(tmp_path / "c.json"))
    d = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    assert all(f["excluded"] is False for f in d["judges"].values())
    assert d["judges"]["fake-llm-b"]["criteria"]["faithfulness"]["kappa"] is None
    assert "kappa indéfini sur faithfulness" in res.output
    assert "Aucun Juge exclu." in res.output


# --- AC 4 : calibration_judge ------------------------------------------------------------------


def test_juge_de_calibration_ne_note_que_les_doublement_annotees(
    execution: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dossier = execution
    exp = _experience(tmp_path, "exp-cal.yaml", judges={"calibration_judge": "fake-llm-a"})
    ids = _annoter(dossier, tmp_path / "ann", doubles=2)
    appels = _espion(monkeypatch)
    _calibrer(exp, tmp_path / "ann", dossier.name)
    doubles = {i.rsplit("/", 1)[1] for i in ids[:2]}
    de_a = [a for a in appels if a[0] == "fake-llm-a"]
    assert {q for _, q, _ in de_a} == doubles and len(de_a) == 2 * 5
    d = json.loads((dossier / "calibration.json").read_text(encoding="utf-8"))
    assert d["calibration_judge"]["model"] == "fake-llm-a"
    assert "fake-llm-a" not in d["judges"]  # à part : ni dans le Panel ni exclu
    assert d["calibration_judge"]["criteria"]


# --- AC 5 : excluded_from, Panel, Rapport, Filtre closed-book -----------------------------------


def _calibration_a_la_main(chemin: Path, exclus: dict[str, bool]) -> None:
    corps = {
        "created_at": "2026-10-18T05:00:00+00:00",
        "judges": {m: {"excluded": e} for m, e in exclus.items()},
    }
    chemin.write_text(json.dumps(corps), encoding="utf-8")


def test_excluded_from_ecarte_le_juge_du_panel_et_le_rapport_le_mentionne(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path
) -> None:
    calibration = tmp_path / "calibration.json"
    # Exclure c ne laisse qu'un Juge admissible (a est de la Famille du Generator) : refus.
    _calibration_a_la_main(calibration, {"fake-llm-c": True, "fake-llm-b": False})
    refuse = _experience(tmp_path, "refus.yaml", judges={"excluded_from": str(calibration)})
    res = CliRunner().invoke(app, ["run", str(refuse)])
    assert res.exit_code == 2 and "judges.pool" in res.output

    _calibration_a_la_main(calibration, {"fake-llm-a": True})
    ok = _experience(tmp_path, "ok.yaml", judges={"excluded_from": str(calibration)})
    res = CliRunner().invoke(app, ["run", str(ok)])
    assert res.exit_code == 0, res.output
    rapports = [p for p in (wl_home / "runs").glob("*/report/*.md")]
    textes = [p.read_text(encoding="utf-8") for p in rapports]
    assert any(
        "Juges exclus par la calibration : `fake-llm-a` (calibration du 2026-10-18)." in t
        for t in textes
    )


def test_avertit_de_relancer_closed_book_si_le_juge_exclu_y_a_servi(
    execution: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    _annoter(dossier, tmp_path / "ann")
    _espion(monkeypatch, _b_bon_c_mauvais)
    res = _calibrer(exp, tmp_path / "ann", dossier.name)
    # Pool [c, b, a] : c juge le Filtre closed-book des modèles d'une autre Famille (a, b).
    assert "Le Juge fake-llm-c a servi au Filtre closed-book" in res.output
    assert "wl questions closed-book" in res.output


# --- AC 6 : code 2 -----------------------------------------------------------------------------


def test_code_2_run_inconnu_dossier_vide_et_annotations_hors_execution(
    execution: tuple[Path, Path], tmp_path: Path
) -> None:
    exp, dossier = execution
    vide = tmp_path / "vide"
    vide.mkdir()
    res = _calibrer(exp, vide, dossier.name, code=2)
    assert "aucun fichier d'annotations" in res.output
    _annoter(dossier, tmp_path / "ann")
    res = _calibrer(exp, tmp_path / "ann", "20260101-000000-inconnu", code=2)
    assert "introuvable" in res.output
    ailleurs = {
        "x": [
            {
                "answer_id": "ailleurs/bm25/standard/all/base/q-001",
                "criterion": "correctness",
                "verdict": "yes",
            }
        ]
    }
    _ecrire_annotations(tmp_path / "autre", ailleurs)
    res = _calibrer(exp, tmp_path / "autre", dossier.name, code=2)
    assert "aucune annotation ne porte sur une Réponse" in res.output
    assert not (dossier / "calibration.json").exists()


# --- Revue : Cache, échecs de fournisseur, bornes ----------------------------------------------


def _spans_judging(dossier_hors_execution: Path) -> list[dict[str, Any]]:
    lignes = (dossier_hors_execution / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    return [s for s in map(json.loads, lignes) if s["wl.post"] == "judging"]


def test_seconde_calibration_rappelle_les_passes_1_a_4_hors_cache(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path
) -> None:
    """La seconde calibration trouve tout au Cache ; seule la passe 0 peut y être servie."""
    exp, dossier = execution
    _annoter(dossier, tmp_path / "ann")
    _calibrer(exp, tmp_path / "ann", dossier.name)
    (premiere,) = list((wl_home / "hors-execution").iterdir())
    _calibrer(exp, tmp_path / "ann", dossier.name)
    (seconde,) = [d for d in (wl_home / "hors-execution").iterdir() if d != premiere]
    spans = _spans_judging(seconde)
    assert spans and len(spans) % 5 == 0
    reels = [s for s in spans if not s["wl.llm_cache_hit"]]
    assert len(reels) == 4 * len(spans) // 5  # passe 0 au Cache, passes 1 à 4 rappelées
    assert len(_spans_judging(premiere)) == len(spans)


def test_le_panel_de_wl_run_garde_le_cache_des_passes_suivantes() -> None:
    """Hors calibration, `pass_id` >= 1 lit toujours le Cache (comportement du Panel inchangé)."""
    vus: list[bool] = []

    class _Passerelle:
        def complete_structured(self, requete: Any, schema: Any, *, use_cache: bool = True) -> Any:
            vus.append(use_cache)
            raise RuntimeError("arrêt")

    class _Ctx:
        seed = 1
        gateway = _Passerelle()
        catalog = SimpleNamespace(
            get=lambda _m: SimpleNamespace(max_output_tokens=None, thinking_reserve_tokens=0)
        )

    item = JudgeInput(
        question="q", reference_answer="r", reference_texts=(), answer_text="a", context_texts=()
    )
    for drapeau in (True, False):
        juge = LLMJudge(LLMJudge.Params(model="fake-llm-b", cache_later_passes=drapeau), _Ctx())
        for passe in (0, 1):
            with pytest.raises(RuntimeError):
                juge.judge(item, ["correctness"], passe)
    assert vus == [True, True, True, False]


def test_fournisseur_injoignable_sort_en_code_4_sans_ecrire(
    execution: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    _annoter(dossier, tmp_path / "ann")

    def panne(juge: str, passe: int, critere: str, humain: bool) -> bool:
        if juge == "fake-llm-b":
            raise ProviderError("connexion refusée")
        return humain

    _espion(monkeypatch, panne)
    res = _calibrer(exp, tmp_path / "ann", dossier.name, code=4)
    assert "connexion refusée" in res.output
    assert not (dossier / "calibration.json").exists()


def test_juge_sans_aucun_verdict_conforme_fait_echouer_la_calibration(
    execution: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    _annoter(dossier, tmp_path / "ann")

    def muet(juge: str, passe: int, critere: str, humain: bool) -> bool:
        if juge == "fake-llm-c":
            raise NonConformantOutput("sortie non conforme")
        return humain

    _espion(monkeypatch, muet)
    res = _calibrer(exp, tmp_path / "ann", dossier.name, code=1)
    assert "aucun verdict conforme pour le(s) Juge(s) fake-llm-c" in res.output
    assert not (dossier / "calibration.json").exists()


def test_run_hors_nom_simple_et_passes_insuffisantes_refuses(
    execution: tuple[Path, Path], tmp_path: Path
) -> None:
    exp, dossier = execution
    _annoter(dossier, tmp_path / "ann")
    res = _calibrer(exp, tmp_path / "ann", f"../runs/{dossier.name}", code=2)
    assert "introuvable" in res.output
    une = _experience(tmp_path, "exp-1.yaml", judges={"calibration_passes": 1})
    res = _calibrer(une, tmp_path / "ann", dossier.name, code=2)
    assert "calibration_passes" in res.output
