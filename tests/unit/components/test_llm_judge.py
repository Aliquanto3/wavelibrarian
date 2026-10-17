"""Story 3.4 : Juge LLM (un appel pour tous les Critères, pass_id hors Cache), Faux LLM seul."""

import json
from pathlib import Path

import pytest

from wavelibrarian import registry
from wavelibrarian.components.judges.llm import LLMJudge
from wavelibrarian.core.errors import NonConformantOutput
from wavelibrarian.core.types import Criterion
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.components import ComponentSpec, Judge, JudgeInput
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context

CRITERES: list[Criterion] = ["correctness", "completeness", "faithfulness"]
ITEM = JudgeInput(
    question="Quand la guilde fut-elle fondée ?",
    reference_answer="La guilde fut fondée en 1412",
    reference_texts=("La guilde d'Orvane date de 1412.",),
    answer_text="La guilde fut fondée en 1412",
    context_texts=("Texte A fourni au Generator.", "Texte B fourni au Generator."),
)


class Env:
    def __init__(self, wl_home: Path) -> None:
        self.provider = FakeProvider()
        self.requetes: list[LLMRequest] = []
        self.sortie: str | None = None
        self.provider.script("judge", "judge*", self._appel)
        self.ctx = Context.from_profile(
            "test", wl_home=wl_home, run_id="r-1", seed=1, providers={"fake": self.provider}
        )

    def _appel(self, req: LLMRequest) -> str:
        self.requetes.append(req)
        if self.sortie is not None:
            return self.sortie
        from wavelibrarian.llm.providers.fake import default_output

        return default_output("judge", req.inputs)

    def juge(self, **params: str) -> Judge:
        return self.ctx.build("judge", ComponentSpec(name="llm", params=params))  # type: ignore[no-any-return]


@pytest.fixture
def env(tmp_path: Path):  # type: ignore[no-untyped-def]
    e = Env(tmp_path / "wl")
    with e.ctx:
        yield e


def test_enregistre_et_modele_par_defaut_du_reservoir(env: Env) -> None:
    assert registry.get("judge", "llm") is LLMJudge
    assert env.juge().model_id == env.ctx.profile.defaults.judge_pool[0]
    assert env.juge(model="fake-llm-a").model_id == "fake-llm-a"


def test_un_seul_appel_pour_tous_les_criteres(env: Env) -> None:
    with env.ctx.scope(post="judging", question_id="q-001"):
        res = env.juge().judge(ITEM, CRITERES, pass_id=0)
    assert len(env.requetes) == 1
    assert env.requetes[0].role == "judge"
    assert list(env.requetes[0].inputs["criteria"]) == CRITERES
    assert set(res) == set(CRITERES)
    for verdict, justification in res.values():
        assert verdict is True
        assert justification


def test_verdict_non_quand_la_reponse_s_ecarte(env: Env) -> None:
    faux = ITEM.model_copy(update={"answer_text": "rien à voir"})
    with env.ctx.scope(post="judging"):
        res = env.juge().judge(faux, ["correctness"], pass_id=0)
    assert res["correctness"][0] is False


def test_sortie_non_conforme_apres_un_nouvel_essai(env: Env) -> None:
    env.sortie = "ceci n'est pas du JSON"
    with env.ctx.scope(post="judging"), pytest.raises(NonConformantOutput):
        env.juge().judge(ITEM, CRITERES, pass_id=0)
    assert len(env.requetes) == 2  # l'appel puis un nouvel essai


def test_critere_manquant_est_non_conforme(env: Env) -> None:
    env.sortie = json.dumps(
        {"verdicts": {"correctness": {"verdict": "yes", "justification": "ok"}}}
    )
    with env.ctx.scope(post="judging"), pytest.raises(NonConformantOutput):
        env.juge().judge(ITEM, CRITERES, pass_id=0)
    assert len(env.requetes) == 2


def test_pass_id_sort_du_cache_de_reponses(env: Env) -> None:
    juge = env.juge()
    with env.ctx.scope(post="judging"):
        juge.judge(ITEM, CRITERES, pass_id=0)
        juge.judge(ITEM, CRITERES, pass_id=0)  # servi par le Cache
        assert len(env.requetes) == 1
        juge.judge(ITEM, CRITERES, pass_id=1)  # nouvelle passe : pas servi par le Cache
        assert len(env.requetes) == 2
        assert [r.pass_id for r in env.requetes] == [0, 1]


def test_faithfulness_reprend_les_textes_du_generator(env: Env) -> None:
    with env.ctx.scope(post="judging"):
        env.juge().judge(ITEM, ["faithfulness"], pass_id=0)
        env.juge().judge(ITEM, ["correctness"], pass_id=0)
    avec, sans = env.requetes
    assert avec.inputs["context_texts"] == list(ITEM.context_texts)
    corps = json.loads(avec.messages[0].content)
    assert corps["context_texts"] == list(ITEM.context_texts)
    assert "context_texts" not in sans.inputs
    assert "Texte A" not in sans.messages[0].content
