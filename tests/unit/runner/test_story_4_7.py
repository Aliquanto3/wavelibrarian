"""Story 4.7 : phase après mise à jour (profil `test`, Faux LLM, Mini-corpus et son Scénario)."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.corpus.scenario import appliquer_fichier, charger
from wavelibrarian.ports.architecture import ArchitectureBase, CorpusChange

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
SCENARIO = RACINE / "scenario" / "scenario.yaml"
BASELINES = [
    {"id": "sans-contexte", "architecture": "no_context"},
    {"id": "contexte-long", "architecture": "long_context"},
    {"id": "bm25", "architecture": "bm25_only"},
]
LIEES_TEST = {"q-045", "q-046", "q-047"}  # Questions de Scénario du split `test`
N_TEST = 28  # Questions du split `test`, toutes reposées en `after_update`


def _experience(tmp_path: Path, numero: int = 1, **champs: Any) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": f"exp-4-7-{numero}",
        "seed": 42,
        "profile": "test",
        "corpus": str(RACINE / "corpus.yaml"),
        "questions": str(RACINE / "questions.yaml"),
        "split": "test",
        "scenario": str(SCENARIO),
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": BASELINES,
        **champs,
    }
    chemin = tmp_path / f"exp-{numero}.yaml"
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _wl_run(chemin: Path, wl_home: Path, code: int = 0) -> Path | None:
    avant = set((wl_home / "runs").glob("*")) if (wl_home / "runs").exists() else set()
    res = CliRunner().invoke(app, ["run", str(chemin)])
    assert res.exit_code == code, res.output
    nouveau = set((wl_home / "runs").glob("*")) - avant if (wl_home / "runs").exists() else set()
    if code != 0:
        assert not nouveau
        return None
    (dossier,) = nouveau
    return dossier


def _jsonl(chemin: Path) -> list[dict[str, Any]]:
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


def _empreinte(dossier: Path) -> dict[str, str]:
    return {
        str(f.relative_to(dossier)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(dossier.rglob("*"))
        if f.is_file()
    }


def _index_spans(dossier: Path, phase: str) -> list[dict[str, Any]]:
    return [
        s
        for s in _jsonl(dossier / "traces.jsonl")
        if s.get("name") == "index" and s.get("wl.phase") == phase
    ]


def _changement(wl_home: Path) -> tuple[CorpusChange, set[str]]:
    """Changement net du Scénario réel et `doc_id` du Corpus après mise à jour."""
    declare_corpus = declare(RACINE / "corpus.yaml")
    base = ingest(declare_corpus, "markdown+pdf_text", wl_home=wl_home)
    change, apres = appliquer_fichier(
        base, SCENARIO, lang=declare_corpus.spec.lang, parser="markdown+pdf_text"
    )
    return change, {d.doc_id for d in apres.documents}


# --- AC 1 : phases base puis after_update, update, nouvelle clé, ancien dossier intact ----------


def test_phase_apres_mise_a_jour_repose_toutes_les_questions_et_ne_touche_pas_l_ancien_index(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appels: list[tuple[str, CorpusChange, Path, Path, dict[str, str]]] = []
    original = ArchitectureBase.update

    def espion(self: Any, change: CorpusChange, apres: Any, ancien: Path, nouveau: Path) -> None:
        appels.append((self.name, change, ancien, nouveau, _empreinte(ancien)))
        original(self, change, apres, ancien, nouveau)

    monkeypatch.setattr(ArchitectureBase, "update", espion)
    dossier = _wl_run(_experience(tmp_path), wl_home)
    assert dossier is not None
    reponses = _jsonl(dossier / "answers.jsonl")
    base = [a for a in reponses if a["phase"] == "base"]
    apres = [a for a in reponses if a["phase"] == "after_update"]
    assert len(base) == 3 * N_TEST  # toutes les Questions du split en base
    # Toutes les Questions sont reposées (Fraîcheur et régression), par Configuration.
    assert {a["question_id"] for a in apres} == {a["question_id"] for a in base}
    assert LIEES_TEST <= {a["question_id"] for a in apres}
    assert len(apres) == 3 * N_TEST
    assert all(a["tier"] is None and a["condition"] == "standard" for a in apres)
    assert all("/standard/all/after_update/" in a["answer_id"] for a in apres)
    assert len({a["answer_id"] for a in reponses}) == len(reponses)

    # `update(change, corpus_after, old_dir, tmp_dir)` : une fois par Configuration indexée.
    assert sorted(nom for nom, *_ in appels) == ["bm25_only", "long_context", "no_context"]
    change, _ = _changement(wl_home)
    for _nom, vu, ancien, nouveau, avant in appels:
        assert vu == change  # le changement net du Scénario (story 2.6)
        assert (ancien / "manifest.json").is_file()
        assert nouveau.name.startswith(".tmp-") and nouveau.parent == ancien.parent
        assert _empreinte(ancien) == avant  # lecture seule pendant `update`
    # Chaque index après mise à jour a sa clé, distincte de celle de la base, et son manifeste.
    spans = _index_spans(dossier, "after_update")
    assert len(spans) == 3
    base_cles = {s["wl.index_key"] for s in _index_spans(dossier, "base")}
    for s in spans:
        cle = s["wl.index_key"]
        assert cle not in base_cles
        manifeste = json.loads((wl_home / "index" / cle / "manifest.json").read_text("utf-8"))
        assert manifeste["index_key"] == cle
        assert not list((wl_home / "index").glob(".tmp-*"))


def test_ancien_index_reste_reutilisable_par_une_autre_execution(
    tmp_path: Path, wl_home: Path
) -> None:
    premier = _wl_run(_experience(tmp_path, 1), wl_home)
    assert premier is not None
    cles_base = {s["wl.index_key"] for s in _index_spans(premier, "base")}
    avant = {cle: _empreinte(wl_home / "index" / cle) for cle in cles_base}
    # Autre Exécution, sans Scénario : mêmes index de base, servis par le cache, intacts.
    second = _wl_run(_experience(tmp_path, 2, scenario=None), wl_home)
    assert second is not None
    spans = _index_spans(second, "base")
    assert {s["wl.index_key"] for s in spans} == cles_base
    assert all(s["wl.index_cache_hit"] is True for s in spans)
    assert {cle: _empreinte(wl_home / "index" / cle) for cle in cles_base} == avant
    assert not [a for a in _jsonl(second / "answers.jsonl") if a["phase"] == "after_update"]


# --- AC 2 : réindexation complète, Poste `update`, énergie --------------------------------------


def test_reindexation_complete_par_defaut_spans_au_poste_update_et_energie(
    tmp_path: Path, wl_home: Path
) -> None:
    dossier = _wl_run(_experience(tmp_path, configurations=BASELINES[2:]), wl_home)
    assert dossier is not None
    spans = _jsonl(dossier / "traces.jsonl")
    apres = [s for s in spans if s.get("wl.phase") == "after_update"]
    index = [s for s in apres if s["name"] == "index"]
    assert len(index) == 1 and index[0]["wl.post"] == "update"
    assert index[0]["wl.index_cache_hit"] is False
    # `load` aussi est imputé au Poste `update` ; les questions, au Poste `query`.
    assert {s["wl.post"] for s in apres if s["name"] == "index"} == {"update"}
    reponses = [s for s in apres if s["name"] == "answer"]
    assert len(reponses) == N_TEST
    assert all(s["wl.post"] == "query" for s in reponses)
    # Énergie locale relevée pour la phase `update` (report 4.5), comme pour `index`.
    assert index[0]["wl.energy_method"] == "estimated"
    assert "wl.energy_kwh" in index[0]
    # La base reste imputée à `indexing`.
    base = [s for s in _index_spans(dossier, "base")]
    assert base and all(s["wl.post"] == "indexing" for s in base)


# --- AC 3 : plus de Document supprimé ni d'ancien doc_id ----------------------------------------


def test_apres_mise_a_jour_aucun_ancien_doc_id_et_ancrages_vers_les_nouveaux(
    tmp_path: Path, wl_home: Path
) -> None:
    dossier = _wl_run(
        _experience(tmp_path, configurations=BASELINES[2:], conditions=["standard"]), wl_home
    )
    assert dossier is not None
    change, nouveaux = _changement(wl_home)
    anciens = set(change.removed) | {ancien for ancien, _ in change.modified}
    assert anciens and not anciens & nouveaux
    toutes = [a for a in _jsonl(dossier / "answers.jsonl") if a["phase"] == "after_update"]
    assert len(toutes) == N_TEST and all(a["status"] == "ok" for a in toutes)
    apres = [a for a in toutes if a["question_id"] in LIEES_TEST]  # contrôle limité aux liées
    assert {a["question_id"] for a in apres} == LIEES_TEST
    modifies = {doc.doc_id for _, doc in change.modified}
    retrouves = 0
    for a in apres:
        docs = {r["passage"]["doc_id"] for r in a["retrieved"]}
        docs |= {x.split("#", 1)[0] for r in a["retrieved"] for x in r["passage"]["anchor_ids"]}
        docs |= {c["anchor_id"].split("#", 1)[0] for c in a["citations"]}
        assert not docs & anciens, a["question_id"]  # ni Passage, ni Citation d'un Document ancien
        assert docs <= nouveaux
        retrouves += len(docs & modifies)
    assert retrouves  # les Documents modifiés sont retrouvés sous leur nouveau doc_id


def test_contexte_parfait_apres_mise_a_jour_ancrages_nouveaux_et_ancrage_supprime_inapplicable(
    tmp_path: Path, wl_home: Path
) -> None:
    dossier = _wl_run(
        _experience(tmp_path, configurations=BASELINES[2:], conditions=["perfect_context"]),
        wl_home,
    )
    assert dossier is not None
    reponses = _jsonl(dossier / "answers.jsonl")
    _, nouveaux = _changement(wl_home)
    base = {a["question_id"]: a for a in reponses if a["phase"] == "base"}
    apres = {a["question_id"]: a for a in reponses if a["phase"] == "after_update"}
    assert set(apres) == set(base) and LIEES_TEST <= set(apres)
    assert all(a["condition"] == "perfect_context" for a in apres.values())
    # Questions non liées : leurs Ancrages existent toujours après la mise à jour.
    assert all(a["status"] == "ok" for q, a in apres.items() if q not in LIEES_TEST)
    # Ancrage du Document modifié : retrouvé sous son nouveau doc_id ; supprimé : inapplicable.
    for qid in ("q-045", "q-046"):
        assert apres[qid]["status"] == "ok"
        assert {r["passage"]["doc_id"] for r in apres[qid]["retrieved"]} <= nouveaux
    assert apres["q-047"]["status"] == "inapplicable"
    assert "supprimé" in apres["q-047"]["error"]
    assert base["q-047"]["status"] == "ok"  # en base, l'Ancrage existe
    # Aucun index construit en contexte parfait, donc aucun `update`.
    assert not _index_spans(dossier, "after_update")


# --- AC 4 : rejeu servi par le cache d'index ------------------------------------------------------


def test_rejeu_l_index_apres_mise_a_jour_est_servi_par_le_cache(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    premier = _wl_run(_experience(tmp_path, 1), wl_home)
    assert premier is not None
    assert all(s["wl.index_cache_hit"] is False for s in _index_spans(premier, "after_update"))
    appels: list[str] = []
    original = ArchitectureBase.update
    monkeypatch.setattr(
        ArchitectureBase,
        "update",
        lambda self, *a: (appels.append(self.name), original(self, *a))[1],
    )
    second = _wl_run(_experience(tmp_path, 2), wl_home)
    assert second is not None
    spans = _index_spans(second, "after_update")
    assert len(spans) == 3
    assert all(s["wl.index_cache_hit"] is True for s in spans)
    assert all(s["wl.post"] == "update" for s in spans)
    assert appels == []  # aucun `update` : l'index existe sous la nouvelle clé
    cles = {s["wl.index_key"] for s in spans}
    cles_premier = {s["wl.index_key"] for s in _index_spans(premier, "after_update")}
    assert cles == cles_premier


# --- Reports : lang et parser passés à corpus_apres ; refus ; cas limites -----------------------


def test_scenario_applique_avec_la_langue_du_corpus_et_le_parser_de_la_configuration(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vus: list[dict[str, Any]] = []
    import wavelibrarian.runner.execute as execute

    original = execute.appliquer_fichier

    def espion(parse: Any, chemin: Path, **kw: Any) -> Any:
        vus.append({"chemin": chemin, **kw})
        return original(parse, chemin, **kw)

    monkeypatch.setattr(execute, "appliquer_fichier", espion)
    _wl_run(_experience(tmp_path, configurations=BASELINES[2:]), wl_home)
    assert len(vus) == 1  # une fois par parser, pas par Condition
    assert vus[0]["lang"] == declare(RACINE / "corpus.yaml").spec.lang
    assert vus[0]["parser"] == "markdown+pdf_text"
    assert vus[0]["chemin"] == SCENARIO


def test_scenario_avec_paliers_applique_le_scenario_au_sous_corpus_de_chaque_palier(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Palier tiré sur le Corpus de base (Documents visés par le Scénario requis), puis Scénario
    appliqué au sous-corpus : l'index après mise à jour du Palier a la taille du Palier, plus
    l'ajout, moins la suppression (4.13 : Fraîcheur par Palier)."""
    vus: list[tuple[int, int, int, int]] = []
    original = ArchitectureBase.update

    def espion(self: Any, change: CorpusChange, apres: Any, ancien: Path, nouveau: Path) -> None:
        vus.append(
            (len(apres.documents), len(change.added), len(change.removed), len(change.modified))
        )
        original(self, change, apres, ancien, nouveau)

    monkeypatch.setattr(ArchitectureBase, "update", espion)
    champs: dict[str, Any] = {"split": "dev", "max_questions": 3, "tier": "all"}
    dossier = _wl_run(
        _experience(tmp_path, configurations=BASELINES[2:], conditions=["standard"], **champs),
        wl_home,
    )
    assert dossier is not None
    tailles = declare(RACINE / "corpus.yaml").spec.tiers.sizes  # type: ignore[union-attr]
    # Palier de n Documents : +1 ajout, -1 suppression, 1 modification.
    assert sorted(vus) == sorted((t, 1, 1, 1) for t in tailles)
    reponses = _jsonl(dossier / "answers.jsonl")
    apres = [a for a in reponses if a["phase"] == "after_update"]
    assert {a["tier"] for a in apres} == set(tailles)
    assert len(apres) == len(tailles) * 3
    assert all(a["status"] == "ok" for a in apres)
    assert all(f"/standard/{a['tier']}/after_update/" in a["answer_id"] for a in apres)
    assert len({a["answer_id"] for a in reponses}) == len(reponses)
    # Chaque index de Palier après mise à jour a sa propre clé.
    assert len({s["wl.index_key"] for s in _index_spans(dossier, "after_update")}) == len(tailles)


def test_scenario_avec_paliers_refuse_en_2_si_les_cibles_ne_tiennent_pas(
    tmp_path: Path, wl_home: Path
) -> None:
    """Documents visés par le Scénario requis dans le plus petit Palier : tirage à blanc en 2."""
    faux = tmp_path / "scenario.yaml"
    cibles = "\n".join(
        f"  - {{id: op-{i}, op: delete, target: {d.source_path}}}"
        for i, d in enumerate(declare(RACINE / "corpus.yaml").documents[:6])
    )
    faux.write_text(
        f"scenario_id: s\ncorpus_id: minicorpus\noperations:\n{cibles}\n", encoding="utf-8"
    )
    chemin = _experience(tmp_path, split="dev", max_questions=1, tier=5, scenario=str(faux))
    _wl_run(chemin, wl_home, code=2)
    res = CliRunner().invoke(app, ["run", str(chemin)])
    assert "Documents requis" in res.output, res.output


def test_scenario_invalide_refuse_en_2(tmp_path: Path, wl_home: Path) -> None:
    faux = tmp_path / "scenario.yaml"
    faux.write_text(
        SCENARIO.read_text("utf-8").replace("note-obsolete.md", "inconnu.md"), encoding="utf-8"
    )
    (tmp_path / "updates").mkdir()
    for source in (RACINE / "scenario" / "updates").iterdir():
        (tmp_path / "updates" / source.name).write_bytes(source.read_bytes())
    _wl_run(_experience(tmp_path, scenario=str(faux)), wl_home, code=2)  # sans dossier créé


def test_scenario_sans_question_liee_repose_quand_meme_les_questions(
    tmp_path: Path, wl_home: Path
) -> None:
    dossier = _wl_run(_experience(tmp_path, split="dev", max_questions=3), wl_home)
    assert dossier is not None
    reponses = _jsonl(dossier / "answers.jsonl")
    base = {a["question_id"] for a in reponses if a["phase"] == "base"}
    apres = {a["question_id"] for a in reponses if a["phase"] == "after_update"}
    assert len(base) == 3 and apres == base


def test_architecture_incrementale_naive_rag_appelle_son_update_sans_reindexer(
    tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`naive_rag` (`incremental_update: true`) : son `update` n'encode que les Documents
    ajoutés ou modifiés ; `index` n'est appelé qu'en phase `base`."""
    from wavelibrarian.architectures.naive_rag import NaiveRag
    from wavelibrarian.components.embedders.fake import FakeEmbedder

    appels: list[str] = []
    encodes: list[int] = []
    index_orig, update_orig = NaiveRag.index, NaiveRag.update
    embed_orig = FakeEmbedder.embed_passages

    def index(self: Any, *a: Any) -> None:
        appels.append("index")
        index_orig(self, *a)

    def update(self: Any, *a: Any) -> None:
        appels.append("update")
        update_orig(self, *a)

    def embed(self: Any, textes: Any) -> Any:
        encodes.append(len(textes))
        return embed_orig(self, textes)

    monkeypatch.setattr(NaiveRag, "index", index)
    monkeypatch.setattr(NaiveRag, "update", update)
    monkeypatch.setattr(FakeEmbedder, "embed_passages", embed)
    conf = {"id": "rag", "architecture": "naive_rag", "params": {"embedder": {"name": "fake"}}}
    dossier = _wl_run(
        _experience(tmp_path, configurations=[conf], conditions=["standard"]), wl_home
    )
    assert dossier is not None
    assert appels == ["index", "update"]
    spans = _index_spans(dossier, "after_update")
    assert len(spans) == 1 and spans[0]["wl.post"] == "update"
    # `update` encode moins de Passages que l'index complet de la base.
    assert len(encodes) >= 2 and sum(encodes[1:]) < encodes[0]
    reponses = [a for a in _jsonl(dossier / "answers.jsonl") if a["phase"] == "after_update"]
    assert len(reponses) == N_TEST and all(a["status"] == "ok" for a in reponses)


def test_charger_le_scenario_du_mini_corpus_reste_valide(wl_home: Path) -> None:
    declare_corpus = declare(RACINE / "corpus.yaml")
    base = ingest(declare_corpus, "markdown+pdf_text", wl_home=wl_home)
    assert len(charger(SCENARIO, base).scenario.operations) == 3
