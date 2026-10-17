"""Filtre closed-book et `wl questions closed-book` (story 3.5), Faux LLM seul."""

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

import wavelibrarian.cli as cli
from wavelibrarian.cli import app
from wavelibrarian.config.experiment import Amount, Budget
from wavelibrarian.evalset import io
from wavelibrarian.llm.providers.fake import FakeProvider, default_output
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context

FREEZE = {"sha256": "ab" * 32, "at": "2026-10-18T00:00:00Z", "seed": 1, "dev_ratio": 0.4}


def _q(i: int, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": f"q-{i:03d}",
        "type": "factual",
        "follow_up": False,
        "cross_lingual": False,
        "text": f"Quelle est la date de fondation de la guilde numéro {i} ?",
        "lang": "fr",
        "reference_answer": "Orvane",
        "answer_form": "short",
        "reference_anchors": [{"doc": "a.md", "headings": ["Guide", "Alpha"]}],
        "status": "validated",
        "split": None,
        "contaminated_by": [],
        "history": [],
        "origin": {"kind": "human", "name": "anael"},
        "scenario_target": None,
    }
    base.update(kw)
    return base


def _ecrire(chemin: Path, questions: list[dict[str, Any]], **kw: Any) -> Path:
    doc: dict[str, Any] = {
        "corpus_id": "demo",
        "target_count": 10,
        "freeze": None,
        "questions": questions,
    }
    doc.update(kw)
    chemin.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return chemin


class Env:
    def __init__(self) -> None:
        self.provider = FakeProvider()
        self.cb: list[LLMRequest] = []
        self.juge: list[LLMRequest] = []
        self.budget: Budget | None = None
        self.reponse: Callable[[LLMRequest], str] | None = None
        self.provider.script("closed_book", "closed_book*", self._cb)
        self.provider.script("judge", "judge*", self._juge)

    def _cb(self, req: LLMRequest) -> str:
        self.cb.append(req)
        if self.reponse is not None:
            return self.reponse(req)
        return default_output("closed_book", req.inputs)

    def _juge(self, req: LLMRequest) -> str:
        self.juge.append(req)
        return default_output("judge", req.inputs)


@pytest.fixture
def env(wl_home: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    e = Env()

    def _contexte(profil: str, seed: int) -> Context:
        return Context.from_profile(
            "test",
            wl_home=wl_home,
            run_id="hors-1",
            seed=seed,
            providers={"fake": e.provider},
            budget=e.budget,
        )

    monkeypatch.setattr(cli, "_contexte_hors_execution", _contexte)
    return e


def _lancer(fichier: Path, *args: str):
    return CliRunner().invoke(
        app, ["questions", "closed-book", str(fichier), "--profil", "test", *args]
    )


# --- AC 1 : statuts, unanswerable, modèles ----------------------------------------------------


def test_questions_validees_posees_sans_contexte_unanswerable_exclues(
    tmp_path: Path, env: Env
) -> None:
    f = _ecrire(
        tmp_path / "q.yaml",
        [
            _q(1),
            _q(2, status="corrected"),
            _q(3, type="unanswerable", reference_anchors=[], reference_answer=""),
            _q(4, status="generated"),
            _q(5, status="rejected"),
        ],
    )
    res = _lancer(f, "--modeles", "fake-llm-a,fake-llm-b")
    assert res.exit_code == 0, res.output
    assert sorted({(r.model_id, r.inputs["text"].split()[-2]) for r in env.cb}) == [
        ("fake-llm-a", "1"),
        ("fake-llm-a", "2"),
        ("fake-llm-b", "1"),
        ("fake-llm-b", "2"),
    ]
    assert all(r.role == "closed_book" and r.system and len(r.messages) == 1 for r in env.cb)
    assert all(r.messages[0].content == r.inputs["text"] for r in env.cb)  # aucun contexte
    assert len(env.cb) == 4 and env.juge == []
    assert "Questions posées : 2 ; non posées (unanswerable) : 1" in res.output
    assert "Questions contaminées : 0" in res.output


def test_sans_modeles_la_liste_vient_du_profil(tmp_path: Path, env: Env) -> None:
    f = _ecrire(tmp_path / "q.yaml", [_q(1)])
    assert _lancer(f).exit_code == 0
    assert [r.model_id for r in env.cb] == ["fake-llm-a", "fake-llm-b", "fake-llm-c"]


def test_modele_inconnu_ou_repete_code_2_sans_appel(tmp_path: Path, env: Env) -> None:
    f = _ecrire(tmp_path / "q.yaml", [_q(1)])
    octets = f.read_bytes()
    for arg in ("fake-llm-a,inconnu", "fake-llm-a,fake-llm-a", ""):
        res = _lancer(f, "--modeles", arg)
        assert res.exit_code == 2, res.output
    assert env.cb == [] and f.read_bytes() == octets


# --- AC 2 : réponse courte, correspondance exacte sans Juge ------------------------------------


def test_reponse_courte_contenant_la_reference_contamine_sans_juge(
    tmp_path: Path, env: Env
) -> None:
    env.reponse = lambda r: "C'est ORVANE, je crois." if r.model_id == "fake-llm-b" else "Aucune"
    f = _ecrire(tmp_path / "q.yaml", [_q(1), _q(2, reference_answer="1 412")])
    res = _lancer(f, "--modeles", "fake-llm-a,fake-llm-b")
    assert res.exit_code == 0, res.output
    jeu = io.load(f)
    assert jeu.questions[0].contaminated_by == ("fake-llm-b",)
    assert jeu.questions[1].contaminated_by == ()
    assert env.juge == []
    assert "q-001 : fake-llm-b" in res.output


# --- AC 3 : réponse libre, Juge d'une autre Famille -------------------------------------------


def test_reponse_libre_jugee_par_une_autre_famille(tmp_path: Path, env: Env) -> None:
    f = _ecrire(
        tmp_path / "q.yaml",
        [_q(1, answer_form="free", reference_answer="Orvane fonda la guilde")],
    )
    env.reponse = lambda r: "Orvane fonda la guilde"
    res = _lancer(f, "--modeles", "fake-llm-a,fake-llm-c")
    assert res.exit_code == 0, res.output
    # pool [c, b, a] : `fake-llm-a` (famille fake-a) -> c ; `fake-llm-c` (famille fake-c) -> b
    assert sorted(r.model_id for r in env.juge) == ["fake-llm-b", "fake-llm-c"]
    assert all(r.inputs["criteria"] == ["correctness"] for r in env.juge)
    assert io.load(f).questions[0].contaminated_by == ("fake-llm-a", "fake-llm-c")


def test_verdict_non_du_juge_ne_contamine_pas(tmp_path: Path, env: Env) -> None:
    f = _ecrire(
        tmp_path / "q.yaml",
        [_q(1, answer_form="free", reference_answer="Orvane fonda la guilde")],
    )
    env.reponse = lambda r: "Je ne sais pas du tout"
    assert _lancer(f, "--modeles", "fake-llm-a").exit_code == 0
    assert len(env.juge) == 1
    assert io.load(f).questions[0].contaminated_by == ()


def test_pool_sans_autre_famille_code_2_avant_appel(
    tmp_path: Path, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian.runner import context as module

    reel = module.load_profile

    def _profil(nom: str) -> Any:
        p = reel(nom)
        d = p.defaults.model_copy(update={"judge_pool": ("fake-llm-a",)})
        return p.model_copy(update={"defaults": d})

    monkeypatch.setattr(module, "load_profile", _profil)
    f = _ecrire(tmp_path / "q.yaml", [_q(1, answer_form="free")])
    res = _lancer(f, "--modeles", "fake-llm-a")
    assert res.exit_code == 2 and "aucun Juge closed-book" in res.output
    assert env.cb == []


# --- AC 4 : Faux LLM par défaut ----------------------------------------------------------------


def test_faux_llm_par_defaut_aucune_contamination(tmp_path: Path, env: Env) -> None:
    f = _ecrire(
        tmp_path / "q.yaml",
        [
            _q(1),
            _q(2, answer_form="free", reference_answer="Orvane fonda une guilde marchande"),
        ],
    )
    res = _lancer(f)
    assert res.exit_code == 0, res.output
    assert all(q.contaminated_by == () for q in io.load(f).questions)
    assert "Questions contaminées : 0" in res.output


# --- AC 5 : Jeu gelé, spans judging ------------------------------------------------------------


def test_jeu_gele_seul_contaminated_by_change_et_relance_remplace(
    tmp_path: Path, env: Env, wl_home: Path
) -> None:
    env.reponse = lambda r: "Orvane" if r.model_id == "fake-llm-a" else "rien"
    f = _ecrire(
        tmp_path / "q.yaml",
        [_q(1, contaminated_by=["fake-llm-b", "fake-llm-c"]), _q(2, status="rejected")],
        freeze=FREEZE,
    )
    avant = io.load(f)
    assert _lancer(f, "--modeles", "fake-llm-a,fake-llm-b").exit_code == 0
    apres = io.load(f)
    assert apres.freeze == avant.freeze and apres.freeze is not None
    assert apres.questions[1] == avant.questions[1]
    # fake-llm-b n'est plus contaminé, fake-llm-c (non retesté) est conservé
    assert apres.questions[0].contaminated_by == ("fake-llm-c", "fake-llm-a")

    def sans(j: io.QuestionsFile) -> dict[str, Any]:
        return j.model_dump(exclude={"freeze"}) | {
            "questions": [q.model_dump(exclude={"contaminated_by"}) for q in j.questions]
        }

    assert sans(apres) == sans(avant)
    traces = wl_home / "hors-execution" / "hors-1" / "traces.jsonl"
    spans = [json.loads(x) for x in traces.read_text(encoding="utf-8").splitlines()]
    assert len(spans) == 2
    assert {s["wl.post"] for s in spans} == {"judging"}
    assert {s["wl.step"] for s in spans} == {"closed_book"}


def test_relance_identique_ne_reecrit_pas_le_fichier(tmp_path: Path, env: Env) -> None:
    f = _ecrire(tmp_path / "q.yaml", [_q(1)])
    assert _lancer(f).exit_code == 0
    octets = f.read_bytes()
    assert _lancer(f).exit_code == 0
    assert f.read_bytes() == octets


def test_plafond_code_3_fichier_inchange(tmp_path: Path, env: Env) -> None:
    env.budget = Budget(per_run={"fake": Amount(amount=Decimal("0.0000001"), currency="USD")})
    f = _ecrire(tmp_path / "q.yaml", [_q(1)])
    octets = f.read_bytes()
    res = _lancer(f)
    assert res.exit_code == 3 and "Plafond atteint" in res.output
    assert f.read_bytes() == octets and env.cb == []
