"""Story 1.10 : rôles LLM, Faux LLM branché sur la passerelle (aucun réseau)."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.experiment import Budget
from wavelibrarian.core.errors import NonConformantOutput, WlError
from wavelibrarian.core.types import Condition, CostPost, Phase
from wavelibrarian.llm.budget import Ledger
from wavelibrarian.llm.cache import ResponseCache
from wavelibrarian.llm.gateway import MeteredGateway
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.llm.roles import ROLES
from wavelibrarian.measure.energy import FakeEstimator
from wavelibrarian.measure.tokenizers import ApproxTokenizer
from wavelibrarian.measure.tracing import Tracer
from wavelibrarian.ports.gateway import LLMRequest, LLMRole, Message


class _Ctx:
    run_id = "run-1"
    config_id = "cfg-1"
    condition: Condition = "standard"
    tier: int | None = None
    phase: Phase = "base"
    post: CostPost = "query"
    question_id: str | None = "q-1"


class Env:
    def __init__(self, wl_home: Path, tmp: Path) -> None:
        self.fake = FakeProvider()
        self.ledger = Ledger(Budget(per_run={}, period={}), "run-1", wl_home)
        self.cache = ResponseCache(wl_home)
        self.path = tmp / "traces.jsonl"
        self.gw = MeteredGateway(
            catalog=load_catalog(),
            providers={"fake": self.fake},
            ledger=self.ledger,
            cache=self.cache,
            tracer=Tracer(_Ctx(), self.path),
            tokenizer_for=lambda _m: ApproxTokenizer(),
            estimator=FakeEstimator(),
            sleep=lambda _s: None,
        )

    def spans(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def env(wl_home: Path, tmp_path: Path) -> Iterator[Env]:
    e = Env(wl_home, tmp_path)
    yield e
    e.ledger.close()
    e.cache.close()


def _req(role: LLMRole, inputs: dict[str, Any], **kw: Any) -> LLMRequest:
    base: dict[str, Any] = {
        "model_id": "fake-llm-a",
        "role": role,
        "step": role,
        "system": "Sys.",
        "messages": (Message(role="user", content="Prompt libre sans importance."),),
        "max_tokens": 100,
        "inputs": inputs,
    }
    return LLMRequest(**{**base, **kw})


def _schema(role: LLMRole) -> type[BaseModel]:
    sortie = ROLES[role].output
    assert sortie is not None
    return sortie


# Entrées valides par rôle (contracts.md §3) et sortie par défaut attendue.
_ANCRES = [
    {"anchor_id": "a1", "text": "Orvane fut fondée en 1204. Elle est ancienne."},
    {"anchor_id": "a2", "text": "La guilde taille la pierre."},
]
_REFS = ("Orvane fut fondée en 1204.", "La guilde taille la pierre.")
_MOTS_30 = " ".join(f"m{i}" for i in range(30))
CAS: dict[str, tuple[dict[str, Any], Any]] = {
    "generate": (
        {"question": "q", "blocks": {"S1": "Orvane fut fondée en 1204. Autre.", "S2": "Zut."}},
        {"answer": "Orvane fut fondée en 1204.", "citations": ["S1"], "abstain": False},
    ),
    "judge": (
        {
            "question": "q",
            "reference_answer": "la guilde taille la pierre",
            "answer": "La guilde taille du bois",
            "criteria": ["correctness", "completeness"],
        },
        {
            "verdicts": {
                c: {"verdict": "yes", "justification": "3/4 mots de la référence présents"}
                for c in ("correctness", "completeness")
            }
        },
    ),
    "rewrite": ({"text": "Qui a fondé Orvane ?"}, "Qui a fondé Orvane ?"),
    "hyde": ({"text": _MOTS_30 + " m30 m31"}, _MOTS_30),
    "summarize": ({"text": "un deux trois"}, "un deux trois"),
    "closed_book": ({"text": "Qui a fondé Orvane ?"}, "Qui a fondé Orvane ?"),
    "community_report": ({"text": "a b"}, "a b"),
    "global_map": ({"text": "c d e"}, "c d e"),
    "extract_entities": (
        {"text": "hier Marie Curie a visité Orvane"},
        {
            "entities": [
                {"name": n, "kind": "entity", "description": f"Entité citée : {n}"}
                for n in ("Marie Curie", "Orvane")
            ],
            "relations": [
                {
                    "source": "Marie Curie",
                    "target": "Orvane",
                    "description": "Marie Curie et Orvane sont voisines",
                    "weight": 1.0,
                }
            ],
        },
    ),
    "select_nodes": (
        {
            "question": "histoire de la guilde",
            "nodes": [
                {"id": "n1", "title": "Cuisine", "summary": "recettes"},
                {"id": "n2", "title": "Guilde", "summary": "organisation"},
                {"id": "n3", "title": "Autre", "summary": "histoire"},
            ],
            "max": 1,
        },
        {"node_ids": ["n2"], "done": True},
    ),
    "agent_step": (
        {"question": "q ?", "step": 1, "last_results": []},
        {"action": "search", "args": {"query": "q ?"}},
    ),
    "grade_relevance": (
        {"question": "guilde orvane", "passages": ["la guilde", "rien", "orvane guilde"]},
        {"scores": [0.5, 0.0, 1.0]},
    ),
    "wiki_compile": (
        {
            "documents": [
                {
                    "source_path": "d1.md",
                    "blocks": [{"anchor_id": f"b{i}", "text": f"t{i}"} for i in range(5)],
                }
            ]
        },
        {"pages": [{"title": "d1.md", "body": "t0\n\nt1\n\nt2", "anchor_ids": ["b0", "b1", "b2"]}]},
    ),
    "wiki_fidelity": (
        {"page": "La guilde taille. Le dragon vole haut.", "sources": ["la guilde taille"]},
        {"claims": 2, "supported": 1},
    ),
    "question_gen": (
        {"anchors": _ANCRES, "types": {"factual": 2}},
        {
            "questions": [
                {
                    "type": "factual",
                    "text": f"Que dit le passage {a['anchor_id']} ?",
                    "reference_answer": ref,
                    "answer_form": "free",
                    "anchor_ids": [a["anchor_id"]],
                }
                for a, ref in zip(_ANCRES, _REFS, strict=True)
            ]
        },
    ),
}


def test_quinze_roles_declares() -> None:
    assert len(ROLES) == 15
    assert set(CAS) == set(ROLES)  # un cas de test par rôle
    for role, spec in ROLES.items():
        assert spec.role == role
        assert spec.required_inputs
        assert spec.output is None or issubclass(spec.output, BaseModel)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_sortie_par_defaut_valide_pour_chaque_role(env: Env, role: LLMRole) -> None:
    inputs, attendu = CAS[role]
    requete = _req(role, inputs)
    if ROLES[role].output is None:
        assert env.gw.complete(requete).text == attendu
    else:
        valeur, res = env.gw.complete_structured(requete, _schema(role))
        assert json.loads(res.text) == attendu
        assert valeur.model_dump() == attendu


@pytest.mark.parametrize("role", sorted(ROLES))
def test_cle_manquante_refusee_avant_tout_appel(env: Env, role: LLMRole) -> None:
    inputs, _ = CAS[role]
    for cle in ROLES[role].required_inputs:
        incomplet = {k: v for k, v in inputs.items() if k != cle}
        with pytest.raises(WlError, match=cle):
            env.gw.complete(_req(role, incomplet))
        with pytest.raises(WlError, match=cle):
            env.gw.complete_structured(_req(role, incomplet), BaseModel)
    assert env.spans() == []  # ni réservation, ni appel, ni span


def test_ne_lit_jamais_le_texte_du_prompt() -> None:
    fake = FakeProvider()
    inputs, attendu = CAS["generate"]
    a = fake.complete(_req("generate", inputs, system="A A A"), timeout_s=1)
    msg = (Message(role="user", content="[S1] tout autre texte"),)
    b = fake.complete(_req("generate", inputs, messages=msg), timeout_s=1)
    assert json.loads(a.text) == json.loads(b.text) == attendu


def test_generate_abstention_si_blocks_vide(env: Env) -> None:
    requete = _req("generate", {"question": "q", "blocks": {}})
    sortie, _ = env.gw.complete_structured(requete, _schema("generate"))
    assert sortie.model_dump()["abstain"] is True
    assert sortie.model_dump()["citations"] == []


def test_judge_non_si_moins_de_la_moitie(env: Env) -> None:
    inputs = {**CAS["judge"][0], "answer": "rien de commun ici", "criteria": ["c"]}
    res = env.gw.complete(_req("judge", inputs))
    assert json.loads(res.text)["verdicts"]["c"]["verdict"] == "no"


def test_agent_step_enchainement(env: Env) -> None:
    resultats = [{"id": "p1", "text": "Orvane fut fondée en 1204. Suite."}]
    sorties = []
    for etape in (1, 2, 3):
        entrees = {"question": "q", "step": etape, "last_results": resultats}
        sorties.append(json.loads(env.gw.complete(_req("agent_step", entrees)).text))
    assert [s["action"] for s in sorties] == ["search", "read", "answer"]
    assert sorties[1]["args"] == {"id": "p1"}
    assert sorties[2]["args"]["answer"] == "Orvane fut fondée en 1204."
    assert sorties[2]["args"]["citations"] == ["p1"]


def test_tokens_en_mots_et_latence_nulle() -> None:
    fake = FakeProvider()
    # system "Sys." (1 mot) + prompt (4 mots) = 5 mots ; sortie : 3 mots
    rep = fake.complete(_req("summarize", {"text": "un deux trois"}), timeout_s=1)
    assert (rep.usage.input_tokens, rep.usage.output_tokens) == (5, 3)
    assert rep.usage.cache_read_tokens == 0


def test_cache_read_tokens_prefixe_deja_vu() -> None:
    fake = FakeProvider()
    inputs = {"text": "x"}
    systeme = "un deux trois quatre"
    msgs = (
        Message(role="user", content="cinq six", cache=True),
        Message(role="user", content="sept"),
    )
    r1 = fake.complete(
        _req("summarize", inputs, system=systeme, messages=msgs, cache_system=True), timeout_s=1
    )
    assert r1.usage.cache_read_tokens == 0 and r1.usage.input_tokens == 7
    # même préfixe (system + message `cache`), suffixe différent : 6 mots lus du cache
    msgs2 = (msgs[0], Message(role="user", content="huit neuf dix"))
    r2 = fake.complete(
        _req("summarize", inputs, system=systeme, messages=msgs2, cache_system=True), timeout_s=1
    )
    assert r2.usage.cache_read_tokens == 6 and r2.usage.input_tokens == 3
    # seul le system est en cache : préfixe de 4 mots, déjà vu
    r3 = fake.complete(_req("summarize", inputs, system=systeme, cache_system=True), timeout_s=1)
    assert r3.usage.cache_read_tokens == 4
    # préfixe jamais vu : rien lu
    r4 = fake.complete(
        _req("summarize", inputs, system="autre systeme", cache_system=True), timeout_s=1
    )
    assert r4.usage.cache_read_tokens == 0


def test_latence_nulle_par_la_passerelle(env: Env) -> None:
    # minuteur par défaut de la passerelle : la latence déclarée par le Faux LLM prime
    assert env.fake.complete(_req("summarize", {"text": "a"}), timeout_s=1).latency_s == 0.0
    res = env.gw.complete(_req("summarize", {"text": "a"}))
    assert res.latency_s == 0.0 and not res.from_cache
    assert env.spans()[-1]["wl.latency_s"] == 0.0


def test_script_prime_sur_le_defaut(env: Env) -> None:
    env.fake.script("grade_relevance", "crag.*", '{"scores":[0.1]}')
    inputs, defaut = CAS["grade_relevance"]
    schema = _schema("grade_relevance")
    scripte, _ = env.gw.complete_structured(
        _req("grade_relevance", inputs, step="crag.grade.loop1"), schema
    )
    assert scripte.model_dump()["scores"] == [0.1]
    # même prompt, mêmes `inputs`, même `pass_id` : l'étape non scénarisée n'est pas servie
    # par la sortie scénarisée en cache, ni l'inverse (`step` dans la clé du provider fake)
    autre, res = env.gw.complete_structured(_req("grade_relevance", inputs, step="autre"), schema)
    assert autre.model_dump() == defaut and not res.from_cache
    encore, res = env.gw.complete_structured(
        _req("grade_relevance", inputs, step="crag.grade.loop2"), schema
    )
    assert encore.model_dump()["scores"] == [0.1] and not res.from_cache


def test_script_callable_et_role_inconnu(env: Env) -> None:
    env.fake.script("rewrite", "*", lambda r: r.inputs["text"].upper())
    assert env.gw.complete(_req("rewrite", {"text": "abc"})).text == "ABC"
    with pytest.raises(WlError, match="rôle inconnu"):
        env.fake.script("inconnu", "*", "x")


def test_script_non_conforme_leve_apres_un_nouvel_essai(env: Env) -> None:
    env.fake.script("grade_relevance", "*", '{"scores":[2.0]}')
    inputs, _ = CAS["grade_relevance"]
    with pytest.raises(NonConformantOutput):
        env.gw.complete_structured(_req("grade_relevance", inputs), _schema("grade_relevance"))


def test_inputs_differents_pas_servis_par_le_cache(env: Env) -> None:
    appels: list[int] = []
    reel = env.fake.complete

    def espion(request: LLMRequest, *, timeout_s: float, **kw: Any) -> Any:
        appels.append(1)
        return reel(request, timeout_s=timeout_s, **kw)

    env.fake.complete = espion  # type: ignore[method-assign]
    a = {"question": "q", "blocks": {"S1": "Alpha un."}}
    b = {"question": "q", "blocks": {"S1": "Beta deux."}}
    r1 = env.gw.complete(_req("generate", a))
    r2 = env.gw.complete(_req("generate", b))  # même prompt, autres `inputs`
    r3 = env.gw.complete(_req("generate", a))  # mêmes `inputs` : servi par le cache
    assert (r1.from_cache, r2.from_cache, r3.from_cache) == (False, False, True)
    assert json.loads(r1.text)["answer"] == "Alpha un."
    assert json.loads(r2.text)["answer"] == "Beta deux."
    assert len(appels) == 2
