"""Story 9.6 : `wl rejuger <run_id> <experience.yaml>` (Faux LLM, profil `test`, sans réseau)."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian import cli
from wavelibrarian.cli import app
from wavelibrarian.config.validate import validate_file
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import empreinte
from wavelibrarian.llm.providers.fake import FakeProvider, default_output
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.rejuger import differences
from wavelibrarian.runner.rejuger import rejuger as rejugement
from wavelibrarian.runner.rundir import read_answers, read_panel, read_verdicts

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
MODELES = Path(__file__).resolve().parents[3] / "src" / "wavelibrarian" / "defaults" / "models.yaml"
BM25 = {"id": "bm25", "architecture": "bm25_only"}
SOURCE_JUGES = {"pool": ["fake-llm-c", "fake-llm-b"], "panel_size": 2}
AUTRES_JUGES = {"pool": ["fake-llm-d", "fake-llm-c"], "panel_size": 2}


@pytest.fixture
def jeu(tmp_path: Path) -> Path:
    """Copie du Mini-corpus gelé (re-Gel possible dans le test) et Catalogue avec un 4e Juge."""
    (tmp_path / "jeu").mkdir()
    questions = tmp_path / "jeu" / "questions.yaml"
    shutil.copyfile(RACINE / "questions.yaml", questions)
    catalogue = tmp_path / "jeu" / "models.yaml"
    texte = MODELES.read_text(encoding="utf-8")
    catalogue.write_text(
        texte + "  - <<: *fake_llm\n    id: fake-llm-d\n    family: fake-d\n", encoding="utf-8"
    )
    return tmp_path / "jeu"


def _experience(tmp_path: Path, jeu: Path, nom: str, **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-9-6",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(jeu / "questions.yaml"),
        "catalog": str(jeu / "models.yaml"),
        "split": "dev",
        "max_questions": 4,
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": [BM25],
        "judges": SOURCE_JUGES,
        **champs,
    }
    chemin = tmp_path / nom
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl(*args: str, code: int = 0) -> Any:
    res = CliRunner().invoke(app, list(args))
    assert res.exit_code == code, res.output
    return res


def _source(tmp_path: Path, jeu: Path, wl_home: Path, **champs: Any) -> Path:
    _wl("run", str(_experience(tmp_path, jeu, "source.yaml", **champs)))
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    return dossier


def _autres(wl_home: Path, source: Path) -> list[Path]:
    return [d for d in (wl_home / "runs").iterdir() if d.is_dir() and d != source]


def _manifeste(dossier: Path) -> dict[str, Any]:
    return json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))


def _spans(dossier: Path) -> list[str]:
    return (dossier / "traces.jsonl").read_text(encoding="utf-8").splitlines()


def _post(ligne: str) -> str:
    return json.loads(ligne)["wl.post"]


def _juge_d_dit_non(request: LLMRequest) -> str:
    """`fake-llm-d` prend le contre-pied de la sortie par défaut ; les autres Juges la gardent."""
    sortie = json.loads(default_output(request.role, request.inputs))
    if request.model_id == "fake-llm-d":
        for v in sortie["verdicts"].values():
            v["verdict"] = "no" if v["verdict"] == "yes" else "yes"
    return json.dumps(sortie)


def _avec_faux(monkeypatch: pytest.MonkeyPatch, faux: FakeProvider) -> None:
    def lancer(*a: Any, **k: Any) -> Any:
        return rejugement(*a, providers={"fake": faux}, **k)

    monkeypatch.setattr(cli, "rejugement", lancer)


def _faux(sortie: Any = _juge_d_dit_non) -> FakeProvider:
    faux = FakeProvider()
    faux.script("judge", "*", sortie)
    return faux


# --- AC 1 et 4 : Réponses identiques octet pour octet, seuls les verdicts changent ----------


def test_rejugement_copie_la_generation_et_ne_change_que_les_verdicts(
    tmp_path: Path, jeu: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, jeu, wl_home)
    _avec_faux(monkeypatch, _faux())
    exp = _experience(tmp_path, jeu, "rejuge.yaml", judges=AUTRES_JUGES)
    res = _wl("rejuger", source.name, str(exp))
    (cible,) = _autres(wl_home, source)
    assert f"rejugement de {source.name}" in res.output and "écartées" not in res.output

    manifeste = _manifeste(cible)
    assert manifeste["rejudged_from"] == source.name
    assert manifeste["excluded_questions"] == []
    assert manifeste["status"] == "completed" and manifeste["unjudged"] == 0
    assert manifeste["source_freeze_sha256"] == _manifeste(source)["freeze_sha256"]
    assert manifeste["answers"] == {"ok": 4, "error": 0, "inapplicable": 0}

    # Réponses copiées octet pour octet (answer_id de la source compris).
    assert (cible / "answers.jsonl").read_bytes() == (source / "answers.jsonl").read_bytes()
    assert set(read_answers(cible)) == set(read_answers(source))
    for nom in ("corpus_profile.json", "applicability.json"):
        assert (cible / nom).read_bytes() == (source / nom).read_bytes()

    # Spans de génération copiés tels quels, spans `judging` refaits avec le nouveau Panel.
    generation = [s for s in _spans(source) if _post(s) != "judging"]
    assert [s for s in _spans(cible) if _post(s) != "judging"] == generation
    jugement = [json.loads(s) for s in _spans(cible) if _post(s) == "judging"]
    assert len(jugement) == 2 * 4 and all(s["wl.run_id"] == cible.name for s in jugement)

    # Verdicts : Critères automatiques recalculés à l'identique, Juges du nouveau Panel.
    avant, apres = read_verdicts(source), read_verdicts(cible)
    assert {m for (_, m, _, _) in avant} == {"auto", "fake-llm-b", "fake-llm-c"}
    assert {m for (_, m, _, _) in apres} == {"auto", "fake-llm-c", "fake-llm-d"}
    auto = {k: v.verdict for k, v in avant.items() if k[1] == "auto"}
    assert {k: v.verdict for k, v in apres.items() if k[1] == "auto"} == auto
    c_avant = {(i, c, p): v.verdict for (i, m, c, p), v in avant.items() if m == "fake-llm-c"}
    c_apres = {(i, c, p): v.verdict for (i, m, c, p), v in apres.items() if m == "fake-llm-c"}
    d_apres = {(i, c, p): v.verdict for (i, m, c, p), v in apres.items() if m == "fake-llm-d"}
    assert c_apres == c_avant and set(d_apres) == set(c_avant)
    assert all(v != c_avant[k] for k, v in d_apres.items())
    panel_avant, panel_apres = read_panel(source), read_panel(cible)
    assert set(panel_apres) == set(panel_avant)
    juges = {k for k, v in panel_apres.items() if v.judges}  # Critères notés par le Panel
    assert juges and all(panel_apres[k].judges == ("fake-llm-d", "fake-llm-c") for k in juges)
    assert any(v.tie for v in panel_apres.values()) and not any(v.tie for v in panel_avant.values())

    # Rapport généré, mesures de génération marquées copiées de la source.
    rapport = (cible / "report" / "report.md").read_text(encoding="utf-8")
    assert f"Rejugement de l'Exécution `{source.name}`" in rapport
    assert f"### Coûts et énergie par Poste (copiés de `{source.name}`)" in rapport
    assert f"### Latence, débit et coût par requête (copiés de `{source.name}`)" in rapport
    assert "le Poste `judging` est celui du rejugement" in rapport


# --- AC 1 : Questions sorties du split courant (Gel b2, q-044) ------------------------------


def _sortir_du_dev(questions: Path, qid: str) -> None:
    """Passe la Question `qid` en `test` puis re-Gèle le Jeu (comme le Gel b2 pour q-044)."""
    doc = io.load(questions)
    nouvelles = [
        q.model_copy(update={"split": "test"}) if q.id == qid else q for q in doc.questions
    ]
    doc = doc.model_copy(update={"questions": tuple(nouvelles)})
    assert doc.freeze is not None
    gel = doc.freeze.model_copy(update={"sha256": empreinte(doc)})
    io.save(questions, doc.model_copy(update={"freeze": gel}))


def test_question_hors_split_courant_ecartee_et_listee(
    tmp_path: Path, jeu: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Tout le split dev, comme mini-cpu : sortir une Question ne fait entrer aucune autre.
    source = _source(tmp_path, jeu, wl_home, max_questions=None)
    reponses = read_answers(source)
    sortie = sorted(a.question_id for a in reponses.values())[0]
    _sortir_du_dev(jeu / "questions.yaml", sortie)
    exp = _experience(tmp_path, jeu, "source.yaml", max_questions=None)  # Gel seul différent

    # `wl run --reprendre` reste refusé sur l'ancien Gel (limite (iii) de fix-arbitrages-8-3-8-8).
    refus = _wl("run", str(exp), "--reprendre", source.name, code=2)
    assert "Gel" in refus.output

    _avec_faux(monkeypatch, _faux())
    res = _wl("rejuger", source.name, str(exp))
    assert f"écartées : {sortie}" in res.output
    (cible,) = _autres(wl_home, source)
    manifeste = _manifeste(cible)
    assert manifeste["excluded_questions"] == [sortie]
    assert manifeste["freeze_sha256"] != manifeste["source_freeze_sha256"]
    copiees = read_answers(cible)
    assert sortie not in {a.question_id for a in copiees.values()}
    assert copiees == {i: a for i, a in reponses.items() if a.question_id != sortie}
    assert all(json.loads(s).get("wl.question_id") != sortie for s in _spans(cible))
    assert all(k[0] in copiees for k in read_verdicts(cible))
    rapport = (cible / "report" / "report.md").read_text(encoding="utf-8")
    assert f"hors du split courant, écartées : `{sortie}`" in rapport


# --- AC 2 : refus en code 2 de tout écart hors judges, budget, max_error_rate -------------


def test_refus_configuration_modifiee_nomme_la_difference(
    tmp_path: Path, jeu: Path, wl_home: Path
) -> None:
    source = _source(tmp_path, jeu, wl_home)
    generateur = {"generator": {"name": "llm", "params": {"max_tokens": 321}}}
    exp = _experience(
        tmp_path,
        jeu,
        "modifiee.yaml",
        judges=AUTRES_JUGES,
        configurations=[{**BM25, "params": generateur}],
    )
    res = _wl("rejuger", source.name, str(exp), code=2)
    assert "configurations.bm25." in res.output
    assert "seuls judges, budget, max_error_rate peuvent changer" in res.output
    assert _autres(wl_home, source) == []


def test_refus_graine_et_split_mais_plafonds_admis(tmp_path: Path, jeu: Path) -> None:
    def resolue(nom: str, **champs: Any) -> Any:
        return validate_file(_experience(tmp_path, jeu, nom, **champs)).resolved

    base = resolue("a.yaml")
    admis = resolue(
        "b.yaml",
        judges=AUTRES_JUGES,
        max_error_rate=0.5,
        budget={"per_run": {"fake": {"amount": "1", "currency": "USD"}}},
    )
    assert differences(base, admis) == []
    assert differences(base, resolue("c.yaml", seed=7, split="test")) == ["seed", "split"]
    ajout = resolue("d.yaml", configurations=[BM25, {"id": "sc", "architecture": "no_context"}])
    assert differences(base, ajout) == ["configurations.sc (absente de la source)"]


def test_refus_source_non_terminee_ou_inconnue(tmp_path: Path, jeu: Path, wl_home: Path) -> None:
    source = _source(tmp_path, jeu, wl_home)
    exp = str(_experience(tmp_path, jeu, "rejuge.yaml", judges=AUTRES_JUGES))
    assert "introuvable" in _wl("rejuger", "inconnu", exp, code=2).output
    assert "run_id invalide" in _wl("rejuger", "../x", exp, code=2).output
    manifeste = _manifeste(source)
    manifeste["status"] = "budget_exceeded"
    (source / "manifest.json").write_text(json.dumps(manifeste), encoding="utf-8")
    res = _wl("rejuger", source.name, exp, code=2)
    assert "non terminée (statut budget_exceeded)" in res.output
    assert _autres(wl_home, source) == []


# --- AC 3 : plafond, completed_with_errors et --reprendre comme `wl run` ---------------------


def test_plafond_puis_reprise_du_rejugement(
    tmp_path: Path, jeu: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, jeu, wl_home)
    _avec_faux(monkeypatch, _faux())
    petit = {"per_run": {"fake": {"amount": "0.000001", "currency": "USD"}}}
    exp = _experience(tmp_path, jeu, "rejuge.yaml", judges=AUTRES_JUGES, budget=petit)
    _wl("rejuger", source.name, str(exp), code=3)
    (cible,) = _autres(wl_home, source)
    assert _manifeste(cible)["status"] == "budget_exceeded"
    copie = (cible / "answers.jsonl").read_bytes()

    # Reprise sur une Exécution qui n'est pas un rejugement de la source : code 2.
    _wl("rejuger", source.name, str(exp), "--reprendre", source.name, code=2)
    # Juges changés à la reprise : refusés (seuls les plafonds se relèvent).
    autre = _experience(tmp_path, jeu, "autre.yaml", budget=petit)
    _wl("rejuger", source.name, str(autre), "--reprendre", cible.name, code=2)

    grand = {"per_run": {"fake": {"amount": "100", "currency": "USD"}}}
    releve = _experience(tmp_path, jeu, "releve.yaml", judges=AUTRES_JUGES, budget=grand)
    _wl("rejuger", source.name, str(releve), "--reprendre", cible.name)
    manifeste = _manifeste(cible)
    assert manifeste["status"] == "completed" and len(manifeste["resumptions"]) == 1
    assert manifeste["rejudged_from"] == source.name
    assert (cible / "answers.jsonl").read_bytes() == copie
    assert _autres(wl_home, source) == [cible]
    juges = {m for (_, m, _, _) in read_verdicts(cible)}
    assert juges == {"auto", "fake-llm-c", "fake-llm-d"}
    assert set(read_panel(cible)) == set(read_panel(source))

    res = _wl("rejuger", source.name, str(releve), "--reprendre", cible.name)
    assert "déjà terminée" in res.output


def test_juge_en_echec_donne_completed_with_errors(
    tmp_path: Path, jeu: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, jeu, wl_home)

    def d_en_echec(request: LLMRequest) -> str:
        if request.model_id == "fake-llm-d":
            return "pas du JSON"
        return default_output(request.role, request.inputs)

    _avec_faux(monkeypatch, _faux(d_en_echec))
    exp = _experience(tmp_path, jeu, "rejuge.yaml", judges=AUTRES_JUGES)
    res = _wl("rejuger", source.name, str(exp), code=1)
    (cible,) = _autres(wl_home, source)
    assert f"wl rejuger {source.name} {exp} --reprendre {cible.name}" in res.output
    manifeste = _manifeste(cible)
    assert manifeste["status"] == "completed_with_errors" and manifeste["unjudged"] > 0
    assert (cible / "report" / "report.md").is_file()

    _avec_faux(monkeypatch, _faux())  # le Juge répond de nouveau
    _wl("rejuger", source.name, str(exp), "--reprendre", cible.name)
    assert _manifeste(cible)["status"] == "completed"
    assert _manifeste(cible)["unjudged"] == 0


# --- Revue : Catalogue changé, contenu du Jeu, source sans Réponse, --tolerer-erreurs ---------


def _regeler(questions: Path, qid: str, **champs: Any) -> None:
    """Modifie la Question `qid` puis re-Gèle le Jeu."""
    doc = io.load(questions)
    nouvelles = [q.model_copy(update=champs) if q.id == qid else q for q in doc.questions]
    doc = doc.model_copy(update={"questions": tuple(nouvelles)})
    assert doc.freeze is not None
    gel = doc.freeze.model_copy(update={"sha256": empreinte(doc)})
    io.save(questions, doc.model_copy(update={"freeze": gel}))


def test_catalogue_et_chemins_changes_acceptes(
    tmp_path: Path, jeu: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cas de la 9.10 : le Catalogue (fichier, date, gel des modèles) a changé depuis la source,
    et le Corpus a changé de chemin sans changer de contenu."""
    source = _source(tmp_path, jeu, wl_home)
    resolue = source / "experiment.resolved.yaml"
    donnees = yaml.safe_load(resolue.read_text(encoding="utf-8"))
    donnees |= {
        "catalog_date": "2026-10-01",
        "models_frozen_at": "2026-10-01",
        "corpus": "C:/ailleurs/minicorpus/corpus.yaml",
    }
    resolue.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    catalogue = tmp_path / "models-2.yaml"
    texte = (jeu / "models.yaml").read_text(encoding="utf-8")
    catalogue.write_text(texte + "  - <<: *fake_llm\n    id: fake-llm-e\n", encoding="utf-8")
    _avec_faux(monkeypatch, _faux())
    exp = _experience(tmp_path, jeu, "rejuge.yaml", judges=AUTRES_JUGES, catalog=str(catalogue))
    _wl("rejuger", source.name, str(exp))
    (cible,) = _autres(wl_home, source)
    assert (cible / "answers.jsonl").read_bytes() == (source / "answers.jsonl").read_bytes()
    assert _manifeste(cible)["status"] == "completed"


def test_differences_nomme_les_cles_d_une_section(tmp_path: Path, jeu: Path) -> None:
    base = validate_file(_experience(tmp_path, jeu, "a.yaml")).resolved
    retries = base.retries.model_copy(update={"max_attempts": 3})
    assert differences(base, base.model_copy(update={"retries": retries})) == [
        "retries.max_attempts"
    ]
    contexte = {"catalog": "x.yaml", "questions": "y.yaml", "corpus": "z.yaml"}
    assert differences(base, base.model_copy(update=contexte)) == []


def test_refus_contenu_d_une_question_gardee_modifie(
    tmp_path: Path, jeu: Path, wl_home: Path
) -> None:
    source = _source(tmp_path, jeu, wl_home)
    gardee = sorted(a.question_id for a in read_answers(source).values())[0]
    _regeler(jeu / "questions.yaml", gardee, reference_answer="autre chose")
    exp = _experience(tmp_path, jeu, "rejuge.yaml", judges=AUTRES_JUGES)
    res = _wl("rejuger", source.name, str(exp), code=2)
    assert "diffère du Gel de l'Exécution" in res.output
    assert _autres(wl_home, source) == []


def test_refus_question_entree_dans_le_split_sans_reponse(
    tmp_path: Path, jeu: Path, wl_home: Path
) -> None:
    """Avec `max_questions`, sortir une Question du dev en fait entrer une autre, jamais posée."""
    source = _source(tmp_path, jeu, wl_home)
    posees = sorted({a.question_id for a in read_answers(source).values()})
    _sortir_du_dev(jeu / "questions.yaml", posees[0])
    exp = _experience(tmp_path, jeu, "rejuge.yaml", judges=AUTRES_JUGES)
    res = _wl("rejuger", source.name, str(exp), code=2)
    assert "sans Réponse dans l'Exécution" in res.output
    assert _autres(wl_home, source) == []


def test_refus_source_sans_reponse(tmp_path: Path, jeu: Path, wl_home: Path) -> None:
    source = _source(tmp_path, jeu, wl_home)
    (source / "answers.jsonl").unlink()
    exp = _experience(tmp_path, jeu, "rejuge.yaml", judges=AUTRES_JUGES)
    assert "sans Réponse : rien à rejuger" in _wl("rejuger", source.name, str(exp), code=2).output
    assert _autres(wl_home, source) == []


def test_tolerer_erreurs_sur_un_rejugement(
    tmp_path: Path, jeu: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, jeu, wl_home)

    def d_en_echec(request: LLMRequest) -> str:
        if request.model_id == "fake-llm-d":
            return "pas du JSON"
        return default_output(request.role, request.inputs)

    _avec_faux(monkeypatch, _faux(d_en_echec))
    exp = _experience(tmp_path, jeu, "rejuge.yaml", judges=AUTRES_JUGES)
    _wl("rejuger", source.name, str(exp), "--tolerer-erreurs")
    (cible,) = _autres(wl_home, source)
    assert _manifeste(cible)["status"] == "completed_with_errors"
