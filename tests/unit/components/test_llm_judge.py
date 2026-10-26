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
        assert verdict == "yes"
        assert justification


def test_verdict_non_quand_la_reponse_s_ecarte(env: Env) -> None:
    faux = ITEM.model_copy(update={"answer_text": "rien à voir"})
    with env.ctx.scope(post="judging"):
        res = env.juge().judge(faux, ["correctness"], pass_id=0)
    assert res["correctness"][0] == "no"


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


def test_prompt_demande_decision_puis_une_phrase_de_200_caracteres() -> None:
    from wavelibrarian.components.judges.llm import _SYSTEM

    assert "décide d'abord" in _SYSTEM
    assert "une seule phrase de 200 caractères au plus" in _SYSTEM
    assert "sans délibération" in _SYSTEM


def _sortie_longue(criteres: list[str], longueur: int) -> str:
    return json.dumps(
        {
            "verdicts": {
                c: {"verdict": "no", "justification": "Hmm, voyons. " * longueur} for c in criteres
            }
        }
    )


@pytest.mark.parametrize(
    "cas",
    [
        ("q-044", "rag-naif", ["correctness", "completeness", "faithfulness"]),
        ("q-044", "raptor", ["correctness", "completeness", "faithfulness"]),
        ("q-017", "pageindex", ["correctness", "completeness"]),
    ],
)
def test_rejeu_8_8_justification_longue_complete_tronquee_et_conforme(
    env: Env, cas: tuple[str, str, list[str]]
) -> None:
    """Rejeu des 3 cas 8.8 au sens de l'AC : un JSON complet à justification longue est tronqué,
    conforme, et la troncature est comptée sur le span. La panne réelle de la 8.8 était une
    coupure au budget (JSON incomplet) : ce test ne la rejoue pas ; il prouve la troncature (cas
    Anthropic, sans grammaire). Côté Ollama, la grammaire `maxLength` empêche la justification de
    s'étendre (borne ci-dessous) ; la preuve réelle viendra des runs du lot (9.9, 9.10)."""
    question_id, _config, criteres = cas
    env.sortie = _sortie_longue(criteres, 100)  # ~1300 caractères par justification
    with env.ctx.scope(post="judging", question_id=question_id):
        res = env.juge().judge(ITEM, criteres, pass_id=0)  # type: ignore[arg-type]
    assert len(env.requetes) == 1  # pas de nouvel essai
    assert set(res) == set(criteres)
    for verdict, justification in res.values():
        assert verdict == "no"
        assert len(justification) == 200 and justification.endswith("…")
        assert justification.startswith("Hmm, voyons. Hmm")
    traces = env.ctx.run_dir / "traces.jsonl"
    spans = [json.loads(x) for x in traces.read_text(encoding="utf-8").splitlines()]
    (span,) = [s for s in spans if s.get("wl.kind") == "llm"]
    assert span["wl.status"] == "ok" and span["wl.justification_truncated"] == len(criteres)


def test_justification_courte_sans_attribut_de_troncature(env: Env) -> None:
    with env.ctx.scope(post="judging", question_id="q-001"):
        env.juge().judge(ITEM, CRITERES, pass_id=0)
    traces = env.ctx.run_dir / "traces.jsonl"
    spans = [json.loads(x) for x in traces.read_text(encoding="utf-8").splitlines()]
    assert spans and all("wl.justification_truncated" not in s for s in spans)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_borne_la_justification_bornee_ne_peut_plus_atteindre_le_budget(n: int) -> None:
    """Calcul de borne (Ollama, grammaire `maxLength`) : la plus longue sortie conforme compacte,
    justifications de 200 caractères comprises, tient dans `200 × n + 100` tokens même à 1,5
    caractère par token (le français tokenisé en BPE est plutôt à 3-4). Hypothèses : sans
    échappements JSON ni blancs de mise en forme. La coupure de la 8.8 (délibération sans fin
    dans `justification`) n'est donc plus atteignable par la justification seule."""
    from wavelibrarian.components.judges.llm import budget_sortie

    criteres = ["completeness", "faithfulness", "correctness"][:n]
    pire = {"verdicts": {c: {"verdict": "yes", "justification": "x" * 200} for c in criteres}}
    caracteres = len(json.dumps(pire, ensure_ascii=False))
    assert caracteres / 1.5 < budget_sortie(n)


def test_troncature_bornes_exactes() -> None:
    from wavelibrarian.llm.roles import JUSTIFICATION_MAX, CriterionVerdict

    assert JUSTIFICATION_MAX == 200
    exact = "a" * 200
    assert CriterionVerdict(verdict="yes", justification=exact).justification == exact
    tronque = CriterionVerdict(verdict="yes", justification="a" * 201).justification
    assert tronque == "a" * 199 + "…" and len(tronque) == 200


def test_budget_de_sortie_couvre_les_sorties_observees(env: Env) -> None:
    from wavelibrarian.components.judges.llm import budget_sortie

    # Run 8.8 : sorties conformes jusqu'à 414 tokens (3 Critères), coupées à 300 et 420 avant.
    assert budget_sortie(2) == 500 and budget_sortie(3) == 700 and budget_sortie(0) == 300
    assert budget_sortie(3) > 414 * 1.5
    assert budget_sortie(3, max_output_tokens=512) == 512  # borné par le Catalogue
    assert budget_sortie(1, max_output_tokens=2048) == 300
    assert budget_sortie(20, max_output_tokens=2048) == 2048 and budget_sortie(20) == 4100
    with env.ctx.scope(post="judging", question_id="q-001"):
        env.juge().judge(ITEM, CRITERES, pass_id=0)
    assert env.requetes[0].max_tokens == 700


# --- Story 9.3 : `na` (sans objet) permis en faithfulness seulement ------------------------------


def _sortie(verdicts: dict[str, str]) -> str:
    return json.dumps(
        {"verdicts": {c: {"verdict": v, "justification": "court"} for c, v in verdicts.items()}}
    )


def test_juge_peut_dire_na_en_faithfulness(env: Env) -> None:
    env.sortie = _sortie({"correctness": "no", "completeness": "no", "faithfulness": "na"})
    with env.ctx.scope(post="judging"):
        res = env.juge().judge(ITEM, CRITERES, pass_id=0)
    assert res["faithfulness"] == ("na", "court")
    assert res["correctness"] == ("no", "court")
    assert len(env.requetes) == 1


@pytest.mark.parametrize("critere", ["correctness", "completeness"])
def test_na_sur_un_autre_critere_est_non_conforme(env: Env, critere: str) -> None:
    verdicts = {"correctness": "yes", "completeness": "yes", "faithfulness": "yes", critere: "na"}
    env.sortie = _sortie(verdicts)
    with env.ctx.scope(post="judging"), pytest.raises(NonConformantOutput):
        env.juge().judge(ITEM, CRITERES, pass_id=0)
    assert len(env.requetes) == 2  # l'appel puis un nouvel essai


def test_schema_enum_par_critere_et_prompt_na() -> None:
    from wavelibrarian.components.judges.llm import _SYSTEM, _schema

    schema = _schema(CRITERES).model_json_schema()
    defs = schema["$defs"]
    assert defs["CriterionVerdict"]["properties"]["verdict"]["enum"] == ["yes", "no"]
    assert defs["FaithfulnessVerdict"]["properties"]["verdict"]["enum"] == ["yes", "no", "na"]
    assert list(defs["FaithfulnessVerdict"]["properties"]) == ["verdict", "justification"]
    assert defs["FaithfulnessVerdict"]["properties"]["justification"]["maxLength"] == 200
    proprietes = defs["Verdicts"]["properties"]
    assert proprietes["faithfulness"]["$ref"].endswith("/FaithfulnessVerdict")
    assert proprietes["correctness"]["$ref"].endswith("/CriterionVerdict")
    assert "réponds na si la réponse n'affirme rien de vérifiable" in _SYSTEM
    assert "na n'est permis que pour faithfulness" in _SYSTEM


def test_sortie_generique_du_role_refuse_na_hors_faithfulness() -> None:
    from pydantic import ValidationError

    from wavelibrarian.llm.roles import JudgeOutput

    ok = JudgeOutput.model_validate_json(_sortie({"faithfulness": "na", "correctness": "yes"}))
    assert ok.verdicts["faithfulness"].verdict == "na"
    with pytest.raises(ValidationError, match="permis pour faithfulness seulement : completeness"):
        JudgeOutput.model_validate_json(_sortie({"completeness": "na"}))
