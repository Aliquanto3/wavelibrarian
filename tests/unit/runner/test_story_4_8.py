"""Story 4.8 : arrêt au plafond et reprise d'une Exécution (profil `test`, Faux LLM)."""

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.types import Answer
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions
from wavelibrarian.runner import execute
from wavelibrarian.runner.execute import load_questions, run_experiment
from wavelibrarian.runner.lock import RunLock
from wavelibrarian.runner.rundir import read_answers

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
SANS_CONTEXTE = {"id": "sans-contexte", "architecture": "no_context"}
BM25 = {"id": "bm25", "architecture": "bm25_only"}
N = 8  # Questions posées par Configuration (`max_questions`)
MARGE = Decimal("1e-9")


def _experience(
    tmp_path: Path, nom: str = "exp", plafond: Decimal | None = None, **champs: Any
) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-4-8",
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
    if plafond is not None:
        donnees["budget"] = {"per_run": {"fake": {"amount": str(plafond), "currency": "USD"}}}
    chemin = tmp_path / f"{nom}.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl(*args: str, code: int) -> Any:
    res = CliRunner().invoke(app, ["run", *args])
    assert res.exit_code == code, res.output
    return res


def _un_run(wl_home: Path) -> Path:
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return dossier


def _manifest(dossier: Path) -> dict[str, Any]:
    return json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))


def _lignes(dossier: Path, nom: str) -> list[dict[str, Any]]:
    texte = (dossier / nom).read_text(encoding="utf-8")
    return [json.loads(ligne) for ligne in texte.splitlines()]


def _reservations(wl_home: Path, run_id: str | None = None) -> list[tuple[str, str, str | None]]:
    """(statut, estimé, réel) des réservations du registre, dans l'ordre."""
    conn = sqlite3.connect(wl_home / "ledger.sqlite")
    try:
        requete = "SELECT status, estimated, actual FROM reservations"
        if run_id is not None:
            requete += f" WHERE run_id='{run_id}'"
        return list(conn.execute(requete + " ORDER BY id"))
    finally:
        conn.close()


def _plafond_pour(tmp_path: Path, n: int) -> Decimal:
    """Plafond qui couvre exactement les `n` premiers appels payants : un probe sans plafond, dans
    un autre `WL_HOME`, donne l'estimé et le réel de chaque appel (même suite d'appels)."""
    probe = tmp_path / "probe_home"
    chemin = _experience(tmp_path, "probe")
    resolue = validate_file(chemin).resolved
    run_experiment(resolue, load_questions(resolue), wl_home=probe)
    lignes = _reservations(probe)
    reels = [Decimal(r or "0") for _, _, r in lignes]
    estimes = [Decimal(e) for _, e, _ in lignes]
    plafond = sum(reels[:n]) + estimes[n] - MARGE
    for i in range(n):  # les n premiers passent bien, le suivant est refusé
        assert sum(reels[:i]) + estimes[i] <= plafond
    assert sum(reels[:n]) + estimes[n] > plafond
    return plafond


@pytest.fixture
def arrete(tmp_path: Path, wl_home: Path) -> tuple[Path, Path, Decimal]:
    """Exécution arrêtée après 5 appels payants : (dossier, fichier d'Expérience, plafond)."""
    plafond = _plafond_pour(tmp_path, 5)
    chemin = _experience(tmp_path, "plafonne", plafond)
    _wl(str(chemin), code=3)
    return _un_run(wl_home), chemin, plafond


# --- AC 1 : arrêt au plafond ------------------------------------------------------------------


def test_sixieme_appel_refuse_les_restantes_budget_exceeded_et_code_3(
    arrete: tuple[Path, Path, Decimal], wl_home: Path
) -> None:
    dossier, _, _ = arrete
    reponses = _lignes(dossier, "answers.jsonl")
    assert [a["status"] for a in reponses] == ["ok"] * 5 + ["budget_exceeded"] * (2 * N - 5)
    assert {a["config_id"] for a in reponses if a["status"] == "ok"} == {"sans-contexte"}
    # Les Questions de la Configuration jamais atteinte sont aussi marquées, une ligne par clé.
    assert len({a["answer_id"] for a in reponses}) == 2 * N
    assert all(a["error"] for a in reponses if a["status"] == "budget_exceeded")
    manifeste = _manifest(dossier)
    assert manifeste["status"] == "budget_exceeded" and "finished_at" in manifeste
    assert manifeste["answers"] == {
        "ok": 5,
        "error": 0,
        "inapplicable": 0,
        "budget_exceeded": 2 * N - 5,
    }
    # Refus avant émission : 5 réservations réglées, aucune pour le 6e ; span `budget_refused`.
    assert [s for s, _, _ in _reservations(wl_home)] == ["settled"] * 5
    spans = _lignes(dossier, "traces.jsonl")
    assert [s["wl.status"] for s in spans if s["wl.kind"] == "llm"].count("budget_refused") == 1


def test_un_nouvel_arret_n_ecrit_pas_deux_fois_les_budget_exceeded(
    tmp_path: Path, arrete: tuple[Path, Path, Decimal], wl_home: Path
) -> None:
    dossier, _, _ = arrete
    avant = len(_lignes(dossier, "answers.jsonl"))
    deux_de_plus = _experience(tmp_path, "plus", _plafond_pour(tmp_path, 7))
    _wl(str(deux_de_plus), "--reprendre", dossier.name, code=3)
    lignes = _lignes(dossier, "answers.jsonl")
    assert len(lignes) == avant + 2  # seules les 2 nouvelles Réponses sont ajoutées
    effectives = read_answers(dossier)
    statuts = [a.status for a in effectives.values()]
    assert statuts.count("ok") == 7 and statuts.count("budget_exceeded") == 2 * N - 7
    assert _manifest(dossier)["answers"]["budget_exceeded"] == 2 * N - 7


# --- AC 2 : reprise après plafond relevé ------------------------------------------------------


def test_reprise_saute_les_cles_presentes_et_ne_fait_que_les_appels_manquants(
    tmp_path: Path, arrete: tuple[Path, Path, Decimal], wl_home: Path
) -> None:
    dossier, _, plafond = arrete
    avant_answers = (dossier / "answers.jsonl").read_bytes()
    avant_traces = (dossier / "traces.jsonl").read_bytes()
    relevee = _experience(tmp_path, "releve", plafond * 100)
    res = _wl(str(relevee), "--reprendre", dossier.name, code=0)
    assert dossier.name in res.output

    effectives = read_answers(dossier)
    assert len(effectives) == 2 * N and {a.status for a in effectives.values()} == {"ok"}
    # answers.jsonl : append seulement, les cinq premières lignes sont inchangées.
    apres = (dossier / "answers.jsonl").read_bytes()
    assert apres.startswith(avant_answers)
    nouvelles = [json.loads(ligne) for ligne in apres[len(avant_answers) :].decode().splitlines()]
    assert len(nouvelles) == 2 * N - 5
    assert all(a["status"] == "ok" for a in nouvelles)
    # traces.jsonl n'est jamais réécrit, seulement complété.
    assert (dossier / "traces.jsonl").read_bytes().startswith(avant_traces)
    # Aucun appel repayé : 2 * N appels payants en tout, un par Question.
    spans = [s for s in _lignes(dossier, "traces.jsonl") if s["wl.kind"] == "llm"]
    payes = [s for s in spans if s["wl.status"] == "ok" and not s["wl.llm_cache_hit"]]
    assert len(payes) == 2 * N
    assert [s for s, _, _ in _reservations(wl_home)] == ["settled"] * (2 * N)
    # Somme des wl.cost = dépense réelle du registre pour ce run_id.
    total = sum(Decimal(s["wl.cost"]) for s in _lignes(dossier, "traces.jsonl"))
    reel = sum(Decimal(r or "0") for _, _, r in _reservations(wl_home, dossier.name))
    assert total == reel and total > 0
    manifeste = _manifest(dossier)
    assert manifeste["status"] == "completed"
    assert manifeste["answers"] == {"ok": 2 * N, "error": 0, "inapplicable": 0}
    assert len(manifeste["resumptions"]) == 1
    assert manifeste["resumptions"][0]["budget"]["per_run"]["fake"]["amount"] == str(plafond * 100)
    # Les fichiers du départ restent ceux de l'Exécution d'origine.
    assert (dossier / "experiment.sha256").read_text().strip() == manifeste["experiment_sha256"]


# --- AC 3 : arrêt brutal ----------------------------------------------------------------------


class _Kill(BaseException):
    """Arrêt brutal simulé : n'est attrapé par aucun `except Exception`."""


def test_arret_brutal_reservation_orpheline_reglee_puis_running_et_completed(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian.llm.budget import Ledger

    regler = Ledger.settle
    appels: list[int] = []

    def settle_puis_mort(self: Ledger, reservation: int, actual: Decimal) -> None:
        appels.append(reservation)
        if len(appels) == 4:
            raise _Kill  # le 4e appel est parti, la réservation reste ouverte
        regler(self, reservation, actual)

    monkeypatch.setattr(Ledger, "settle", settle_puis_mort)
    chemin = _experience(tmp_path, configurations=[SANS_CONTEXTE])
    resolue = validate_file(chemin).resolved
    with pytest.raises(_Kill):
        run_experiment(resolue, load_questions(resolue), wl_home=wl_home)
    monkeypatch.setattr(Ledger, "settle", regler)

    dossier = _un_run(wl_home)
    # État laissé par un arrêt dur : manifeste resté `running`, Réponses et spans locaux de la
    # phase (retenus en mémoire jusqu'à sa fin) perdus ; les spans d'appel, eux, sont écrits.
    manifeste = _manifest(dossier)
    manifeste["status"] = "running"
    manifeste.pop("finished_at", None)
    (dossier / "manifest.json").write_text(json.dumps(manifeste), encoding="utf-8")
    (dossier / "answers.jsonl").write_text("", encoding="utf-8")
    appels_traces = [s for s in _lignes(dossier, "traces.jsonl") if s["wl.kind"] == "llm"]
    (dossier / "traces.jsonl").write_text(
        "".join(json.dumps(s) + "\n" for s in appels_traces), encoding="utf-8"
    )
    avant_traces = (dossier / "traces.jsonl").read_bytes()
    assert [s for s, _, _ in _reservations(wl_home)].count("reserved") == 1

    statuts: list[str] = []
    reprendre = execute._Runner.reprendre  # pyright: ignore[reportPrivateUsage]

    def espion(self: Any) -> None:
        statuts.append(_manifest(dossier)["status"])
        reprendre(self)

    monkeypatch.setattr(execute._Runner, "reprendre", espion)  # pyright: ignore[reportPrivateUsage]
    _wl(str(chemin), "--reprendre", dossier.name, code=0)

    assert statuts == ["running"]  # repassé à `running` au démarrage de la reprise
    assert _manifest(dossier)["status"] == "completed"
    lignes = _reservations(wl_home)
    assert "reserved" not in {s for s, _, _ in lignes}
    orpheline = lignes[3]  # la 4e : réglée au montant estimé
    assert orpheline[0] == "settled" and orpheline[2] == orpheline[1]
    assert {a.status for a in read_answers(dossier).values()} == {"ok"}
    assert (dossier / "traces.jsonl").read_bytes().startswith(avant_traces)

    # Appels déjà payés et refaits : cache, coût nul, et marqués pour ne pas être recomptés.
    spans = [
        s for s in _lignes(dossier, "traces.jsonl")[len(appels_traces) :] if s["wl.kind"] == "llm"
    ]
    rejoues = [s for s in spans if s.get("wl.resumed")]
    assert len(rejoues) == 3  # Questions 1 à 3, payées avant l'arrêt
    assert all(s["wl.llm_cache_hit"] and Decimal(s["wl.cost"]) == 0 for s in rejoues)
    assert [s["wl.question_id"] for s in rejoues] == sorted(s["wl.question_id"] for s in rejoues)
    # Les appels réellement nouveaux (Questions 4 à N) ne sont pas marqués.
    assert all(not s.get("wl.resumed") for s in spans if not s["wl.llm_cache_hit"])
    assert len(spans) == N


# --- AC 4 : empreinte -------------------------------------------------------------------------


@pytest.mark.parametrize("champ", ["seed", "configurations", "split"])
def test_reprise_d_une_experience_differente_refusee_code_2(
    tmp_path: Path, arrete: tuple[Path, Path, Decimal], champ: str
) -> None:
    dossier, _, plafond = arrete
    valeurs: dict[str, Any] = {
        "seed": 43,
        "configurations": [SANS_CONTEXTE],
        "split": "test",
    }
    autre = _experience(tmp_path, "autre", plafond * 100, **{champ: valeurs[champ]})
    avant = ((dossier / "answers.jsonl").read_bytes(), (dossier / "manifest.json").read_bytes())
    res = _wl(str(autre), "--reprendre", dossier.name, code=2)
    assert "experiment.sha256" in res.output
    assert (
        (dossier / "answers.jsonl").read_bytes(),
        (dossier / "manifest.json").read_bytes(),
    ) == avant
    assert _manifest(dossier)["status"] == "budget_exceeded"


def test_reprise_d_une_execution_inconnue_ou_terminee_refusee_code_2(
    tmp_path: Path, arrete: tuple[Path, Path, Decimal]
) -> None:
    dossier, _, plafond = arrete
    relevee = _experience(tmp_path, "releve", plafond * 100)
    res = _wl(str(relevee), "--reprendre", "run-inconnu", code=2)
    assert "introuvable" in res.output
    _wl(str(relevee), "--reprendre", dossier.name, code=0)
    res = _wl(str(relevee), "--reprendre", dossier.name, code=2)
    assert "déjà terminée" in res.output


def test_reprise_apres_degel_du_jeu_refusee_code_2(
    tmp_path: Path, arrete: tuple[Path, Path, Decimal]
) -> None:
    dossier, _, plafond = arrete
    manifeste = _manifest(dossier)
    manifeste["freeze_sha256"] = "0" * 64
    (dossier / "manifest.json").write_text(json.dumps(manifeste), encoding="utf-8")
    res = _wl(
        str(_experience(tmp_path, "releve", plafond * 100)), "--reprendre", dossier.name, code=2
    )
    assert "Gel" in res.output


# --- AC 5 : une seule Exécution à la fois -----------------------------------------------------


def test_reprise_pendant_une_autre_execution_code_1_et_dossier_intact(
    tmp_path: Path, arrete: tuple[Path, Path, Decimal], wl_home: Path
) -> None:
    dossier, _, plafond = arrete
    avant = (dossier / "manifest.json").read_bytes(), (dossier / "answers.jsonl").read_bytes()
    verrou = RunLock(wl_home, "autre-run")
    verrou.acquire()
    try:
        res = _wl(
            str(_experience(tmp_path, "releve", plafond * 100)), "--reprendre", dossier.name, code=1
        )
    finally:
        verrou.release()
    assert "Exécution autre-run en cours" in res.output
    assert (
        (dossier / "manifest.json").read_bytes(),
        (dossier / "answers.jsonl").read_bytes(),
    ) == avant


# --- Lecture des Réponses ---------------------------------------------------------------------


def test_read_answers_la_derniere_ligne_d_une_cle_fait_foi(tmp_path: Path) -> None:
    base: dict[str, Any] = {
        "answer_id": "r/c/standard/all/base/q-1",
        "question_id": "q-1",
        "config_id": "c",
        "text": "",
        "abstained": False,
        "retrieval_method": "none",
    }
    lignes = [{**base, "status": "budget_exceeded"}, {**base, "status": "ok"}]
    (tmp_path / "answers.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in lignes), encoding="utf-8"
    )
    effectives = read_answers(tmp_path)
    assert list(effectives) == [base["answer_id"]]
    assert isinstance(effectives[base["answer_id"]], Answer)
    assert effectives[base["answer_id"]].status == "ok"
    assert read_answers(tmp_path / "vide") == {}


def test_les_questions_dev_suffisent(tmp_path: Path) -> None:
    dev = select_questions(io.load(RACINE / "questions.yaml"), "dev")
    assert len(dev) >= N
