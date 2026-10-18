"""Story 4.4 : Exécution d'une Expérience par `wl run` (profil `test`, Faux LLM, Mini-corpus)."""

import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import Answer
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions
from wavelibrarian.llm.providers.fake import FakeProvider, default_output
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.execute import load_questions, run_experiment
from wavelibrarian.runner.lock import RunLock

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
BASELINES = [
    {"id": "sans-contexte", "architecture": "no_context"},
    {"id": "contexte-long", "architecture": "long_context"},
    {"id": "bm25", "architecture": "bm25_only"},
]


def _experience(tmp_path: Path, **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-4-4",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "dev",
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": BASELINES,
        **champs,
    }
    chemin = tmp_path / "exp.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _ids_dev() -> list[str]:
    return sorted(q.id for q in select_questions(io.load(RACINE / "questions.yaml"), "dev"))


def _un_run(wl_home: Path) -> Path:
    runs = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    assert len(runs) == 1
    return runs[0]


def _answers(dossier: Path) -> list[Answer]:
    lignes = (dossier / "answers.jsonl").read_text(encoding="utf-8").splitlines()
    return [Answer.model_validate(json.loads(ligne)) for ligne in lignes]


def _wl_run(chemin: Path) -> Any:
    return CliRunner().invoke(app, ["run", str(chemin)])


# --- AC 1 : bout en bout -----------------------------------------------------------------------


def test_wl_run_trois_baselines_de_bout_en_bout(tmp_path: Path, wl_home: Path) -> None:
    res = _wl_run(_experience(tmp_path))
    assert res.exit_code == 0, res.output
    sortie = res.output
    assert (
        sortie.index("Validation réussie")
        < sortie.index("Préflight réussi")
        < sortie.index("completed")
    )
    dossier = _un_run(wl_home)
    run_id = dossier.name
    manifest = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed" and "finished_at" in manifest
    assert manifest["freeze_sha256"] == io.load(RACINE / "questions.yaml").freeze.sha256  # type: ignore[union-attr]
    profil = json.loads((dossier / "corpus_profile.json").read_text(encoding="utf-8"))
    assert profil["corpus_id"] == "minicorpus" and profil["parser"] == "markdown+pdf_text"
    assert json.loads((dossier / "applicability.json").read_text(encoding="utf-8")) == {}
    assert "name: auto" not in (dossier / "experiment.resolved.yaml").read_text(encoding="utf-8")

    ids = _ids_dev()
    reponses = _answers(dossier)
    assert len(reponses) == 3 * len(ids)
    cles = {(a.config_id, a.condition, a.tier, a.phase, a.question_id) for a in reponses}
    assert len(cles) == len(reponses)  # un Answer par clé
    for a in reponses:
        assert a.status == "ok", a.error
        assert a.answer_id == f"{run_id}/{a.config_id}/standard/all/base/{a.question_id}"
    for conf in ("sans-contexte", "contexte-long", "bm25"):
        assert [a.question_id for a in reponses if a.config_id == conf] == ids
    assert {a.retrieval_method for a in reponses if a.config_id == "sans-contexte"} == {"none"}
    assert any(a.citations for a in reponses if a.config_id == "bm25")

    # Ordre d'AD-11 : ingestion, profilage, puis check, index et answer par Configuration.
    journal = (dossier / "run.log").read_text(encoding="utf-8")
    etapes = [
        "étape ingestion",
        "étape profilage",
        "étape check : sans-contexte",
        "étape index : sans-contexte",
        "étape answer : sans-contexte",
        "étape check : contexte-long",
        "étape index : contexte-long",
        "étape answer : contexte-long",
        "étape check : bm25",
        "étape index : bm25",
        "étape answer : bm25",
    ]
    positions = [journal.index(e) for e in etapes]
    assert positions == sorted(positions)
    # Les appels d'`answer` sont au Poste `query`, avec la Question de la Configuration.
    spans = [
        json.loads(ligne)
        for ligne in (dossier / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    llm = [s for s in spans if s.get("wl.kind") == "llm" and s["wl.post"] != "judging"]
    assert llm and all(s["wl.post"] == "query" and s["wl.question_id"] in ids for s in llm)
    assert {s["wl.config_id"] for s in llm} == {"sans-contexte", "contexte-long", "bm25"}


# --- AC 2 : Jeu non Gelé ou modifié --------------------------------------------------------------


def _questions_copiees(tmp_path: Path) -> Path:
    cible = tmp_path / "questions.yaml"
    shutil.copyfile(RACINE / "questions.yaml", cible)
    return cible


@pytest.mark.parametrize("cas", ["non_gele", "modifie"])
def test_jeu_non_gele_ou_modifie_refuse_avant_tout_appel(
    tmp_path: Path, wl_home: Path, cas: str
) -> None:
    chemin = _questions_copiees(tmp_path)
    doc = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    if cas == "non_gele":
        doc["freeze"] = None
    else:
        doc["questions"][0]["text"] += " (modifiée)"
    chemin.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    res = _wl_run(_experience(tmp_path, questions=str(chemin)))
    assert res.exit_code == 2, res.output
    assert ("non gelé" if cas == "non_gele" else "empreinte différente") in res.output
    assert not (wl_home / "runs").exists()  # ni dossier d'Exécution, ni trace, ni appel
    assert not (wl_home / "ledger.sqlite").exists()


def test_seules_les_questions_validees_ou_corrigees_de_la_partie_sont_posees(
    tmp_path: Path, wl_home: Path
) -> None:
    doc = io.load(RACINE / "questions.yaml")
    attendues = sorted(
        q.id for q in doc.questions if q.split == "test" and q.status in ("validated", "corrected")
    )
    res = _wl_run(_experience(tmp_path, split="test", configurations=BASELINES[2:]))
    assert res.exit_code == 0, res.output
    assert [a.question_id for a in _answers(_un_run(wl_home))] == attendues
    assert not set(attendues) & set(_ids_dev())


# --- AC 3 : Configuration inapplicable -----------------------------------------------------------


def test_long_context_inapplicable_les_autres_s_executent(tmp_path: Path, wl_home: Path) -> None:
    confs = [
        BASELINES[0],
        {
            "id": "contexte-long",
            "architecture": "long_context",
            "params": {"generator": {"name": "llm", "params": {"max_tokens": 99000}}},
        },
        BASELINES[2],
    ]
    res = _wl_run(_experience(tmp_path, configurations=confs, max_questions=4))
    assert res.exit_code == 0, res.output
    dossier = _un_run(wl_home)
    applicabilite = json.loads((dossier / "applicability.json").read_text(encoding="utf-8"))
    assert list(applicabilite) == ["contexte-long"]
    raison = applicabilite["contexte-long"]["reason"]
    assert "fenêtre" in raison and applicabilite["contexte-long"]["applicable"] is False
    reponses = _answers(dossier)
    longues = [a for a in reponses if a.config_id == "contexte-long"]
    assert len(longues) == 4
    assert all(a.status == "inapplicable" and a.error == raison for a in longues)
    autres = [a for a in reponses if a.config_id != "contexte-long"]
    assert len(autres) == 8 and all(a.status == "ok" for a in autres)
    assert json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))["status"] == (
        "completed"
    )


# --- AC 4 : NonConformantOutput sur une Question -------------------------------------------------


def test_sortie_non_conforme_status_error_et_l_execution_continue(wl_home: Path) -> None:
    resolue = validate_file(_experience(wl_home.parent, configurations=BASELINES[2:]), wl_home)
    resolue_exp = resolue.resolved.model_copy(update={"max_questions": 3})
    questions = load_questions(resolue_exp)
    cible = questions.questions[0]
    verrou_tenu: list[bool] = []

    def sortie(request: LLMRequest) -> str:
        try:  # le RunContext reste vivant : run.lock est tenu pendant `answer`
            RunLock(wl_home, "intrus").acquire()
            verrou_tenu.append(False)
        except WlError:
            verrou_tenu.append(True)
        if request.inputs["question"] == cible.text:
            return "pas du JSON"
        return default_output("generate", request.inputs)

    faux = FakeProvider()
    faux.script("generate", "*", sortie)
    issue = run_experiment(resolue_exp, questions, wl_home=wl_home, providers={"fake": faux})
    # 1 `error` sur 3 : taux 1/3 > `max_error_rate` 0,2 (story 8.3)
    assert issue.status == "completed_with_errors"
    assert issue.causes == ({"config_id": "bm25", "cause": "error_rate", "count": 1},)
    reponses = _answers(issue.run_dir)
    assert [a.question_id for a in reponses] == [q.id for q in questions.questions]
    assert reponses[0].status == "error"
    assert reponses[0].error and "NonConformantOutput" in reponses[0].error
    assert [a.status for a in reponses[1:]] == ["ok", "ok"]
    assert verrou_tenu and all(verrou_tenu)
    assert "en erreur" in (issue.run_dir / "run.log").read_text(encoding="utf-8")


# --- AC 5 : max_questions ----------------------------------------------------------------------


def test_max_questions_trois_premieres_par_id(tmp_path: Path, wl_home: Path) -> None:
    res = _wl_run(_experience(tmp_path, max_questions=3))
    assert res.exit_code == 0, res.output
    reponses = _answers(_un_run(wl_home))
    assert len(reponses) == 9
    for conf in ("sans-contexte", "contexte-long", "bm25"):
        assert [a.question_id for a in reponses if a.config_id == conf] == _ids_dev()[:3]


# --- Reports : run.lock, registre, cache des runs scénarisés, hors périmètre --------------------


def test_second_wl_run_code_1_sans_regler_les_reservations_du_premier(
    tmp_path: Path, wl_home: Path
) -> None:
    resolue = validate_file(_experience(tmp_path), wl_home).resolved
    with Context.from_experiment(resolue, wl_home=wl_home, run_id="run-1") as premier:
        reservation = premier._ledger.reserve("fake", Decimal("0.10"), "USD")  # pyright: ignore[reportPrivateUsage, reportOptionalMemberAccess]
        res = _wl_run(_experience(tmp_path))
        assert res.exit_code == 1, res.output
        assert "Exécution run-1 en cours" in res.output
        # la réservation du premier est toujours ouverte : pas « déjà close »
        premier._ledger.settle(reservation, Decimal("0.10"))  # pyright: ignore[reportPrivateUsage, reportOptionalMemberAccess]
    assert [d.name for d in (wl_home / "runs").iterdir()] == ["run-1"]  # aucun second dossier


def test_sortie_scenarisee_ne_persiste_pas_dans_le_cache_de_wl_home(wl_home: Path) -> None:
    resolue = validate_file(_experience(wl_home.parent, configurations=BASELINES[2:]), wl_home)
    exp = resolue.resolved.model_copy(update={"max_questions": 2})
    questions = load_questions(exp)
    marque = '{"answer": "SORTIE SCENARISEE", "citations": [], "abstain": false}'
    faux = FakeProvider()
    faux.script("generate", "*", marque)
    premier = run_experiment(exp, questions, wl_home=wl_home, providers={"fake": faux})
    assert all(a.text == "SORTIE SCENARISEE" for a in _answers(premier.run_dir))
    second = run_experiment(exp, questions, wl_home=wl_home, providers={"fake": FakeProvider()})
    reponses = _answers(second.run_dir)
    assert reponses and all(a.text != "SORTIE SCENARISEE" for a in reponses)


# --- Revue : Gel avant préflight, plafond, échecs de Configuration et d'Exécution ---------------


def _manifest(dossier: Path) -> dict[str, Any]:
    return json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))


def _wl_run_scenarise(monkeypatch: pytest.MonkeyPatch, chemin: Path, sortie: Any) -> Any:
    """`wl run` par la CLI, avec un Faux LLM scénarisé injecté dans `run_experiment`."""
    from wavelibrarian import cli

    def avec_faux(*a: Any, **k: Any) -> Any:
        faux = FakeProvider()
        faux.script("generate", "*", sortie)
        return run_experiment(*a, providers={"fake": faux}, **k)

    monkeypatch.setattr(cli, "run_experiment", avec_faux)
    return _wl_run(chemin)


def test_jeu_non_gele_refuse_en_2_avant_le_preflight(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian import cli

    chemin = _questions_copiees(tmp_path)
    doc = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    doc["freeze"] = None
    chemin.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")

    def preflight_interdit(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("préflight appelé avant le contrôle du Gel")

    monkeypatch.setattr(cli, "preflight", preflight_interdit)
    res = _wl_run(_experience(tmp_path, questions=str(chemin)))
    assert res.exit_code == 2, res.output
    assert "Préflight" not in res.output


def test_plafond_atteint_code_3_et_manifeste_budget_exceeded(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian.core.errors import BudgetExceeded

    appels: list[str] = []

    def sortie(request: LLMRequest) -> str:
        appels.append(request.inputs["question"])
        if len(appels) == 2:
            raise BudgetExceeded("plafond fake atteint")
        return default_output("generate", request.inputs)

    exp = _experience(tmp_path, configurations=BASELINES[2:], max_questions=3)
    res = _wl_run_scenarise(monkeypatch, exp, sortie)
    assert res.exit_code == 3, res.output
    dossier = _un_run(wl_home)
    manifest = _manifest(dossier)
    assert manifest["status"] == "budget_exceeded" and "finished_at" in manifest
    # Story 4.8 : les Questions non traitées sont écrites `budget_exceeded`.
    assert manifest["answers"] == {"ok": 1, "error": 0, "inapplicable": 0, "budget_exceeded": 2}
    assert [a.status for a in _answers(dossier)] == ["ok", "budget_exceeded", "budget_exceeded"]
    assert len(appels) == 2
    assert json.loads((dossier / "applicability.json").read_text(encoding="utf-8")) == {}


def test_toutes_les_reponses_en_erreur_code_1_et_decompte_au_manifeste(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp = _experience(tmp_path, configurations=BASELINES[2:], max_questions=2)
    res = _wl_run_scenarise(monkeypatch, exp, "pas du JSON")
    assert res.exit_code == 1, res.output
    assert "Aucune Réponse valide" in res.output
    dossier = _un_run(wl_home)
    manifest = _manifest(dossier)
    assert manifest["status"] == "completed_with_errors"  # story 8.3
    assert manifest["answers"] == {"ok": 0, "error": 2, "inapplicable": 0}


def test_configuration_en_echec_ses_questions_en_erreur_les_autres_s_executent(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian.architectures.bm25_only import Bm25Only

    def check_en_panne(self: Any, profile: Any) -> Any:
        raise RuntimeError("check en panne")

    monkeypatch.setattr(Bm25Only, "check", check_en_panne)
    confs = [BASELINES[0], BASELINES[2]]
    res = _wl_run(_experience(tmp_path, configurations=confs, max_questions=2))
    assert res.exit_code == 1, res.output  # story 8.3 : `bm25` sans Réponse `ok`
    dossier = _un_run(wl_home)
    reponses = _answers(dossier)
    bm25 = [a for a in reponses if a.config_id == "bm25"]
    assert len(bm25) == 2
    assert all(
        a.status == "error" and "RuntimeError : check en panne" in (a.error or "") for a in bm25
    )
    assert [a.status for a in reponses if a.config_id == "sans-contexte"] == ["ok", "ok"]
    assert _manifest(dossier)["answers"] == {"ok": 2, "error": 2, "inapplicable": 0}
    assert _manifest(dossier)["status"] == "completed_with_errors"
    assert {(c["config_id"], c["cause"]) for c in _manifest(dossier)["causes"]} == {
        ("bm25", "no_ok_answer"),
        ("bm25", "error_rate"),
    }


def test_exception_non_rattrapee_manifeste_failed(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian.runner import execute

    def profil_en_panne(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("profilage en panne")

    monkeypatch.setattr(execute, "profil_corpus", profil_en_panne)
    resolue = validate_file(_experience(tmp_path, configurations=BASELINES[2:]), wl_home).resolved
    with pytest.raises(RuntimeError, match="profilage en panne"):
        run_experiment(resolue, load_questions(resolue), wl_home=wl_home)
    dossier = _un_run(wl_home)
    assert _manifest(dossier)["status"] == "failed"
    assert "profilage en panne" in (dossier / "run.log").read_text(encoding="utf-8")
    RunLock(wl_home, "suivant").acquire()  # le verrou est libéré
