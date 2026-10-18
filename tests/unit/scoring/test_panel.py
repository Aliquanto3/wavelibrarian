"""Story 4.9 : majorité, égalité et reprise du Panel (Juges factices, sans Exécution)."""

from collections.abc import Sequence
from typing import Any

from wavelibrarian.core.types import Answer, Citation, Criterion, Question, Verdict
from wavelibrarian.ports.components import JudgeInput
from wavelibrarian.scoring.panel import (
    PanelVerdict,
    criteres_juges,
    juger_reponse,
    majorite,
    verdicts_automatiques,
)


class _Liste:
    def __init__(self) -> None:
        self.lignes: list[dict[str, Any]] = []

    def append(self, obj: Any) -> None:
        self.lignes.append(obj)


class _Juge:
    """Juge factice : `reponses` donne son verdict par passe ; compte ses appels."""

    def __init__(self, model_id: str, *votes: bool) -> None:
        self.model_id = model_id
        self.votes = votes
        self.appels: list[tuple[tuple[str, ...], int]] = []

    def judge(
        self, item: JudgeInput, criteria: Sequence[Criterion], pass_id: int
    ) -> dict[Criterion, tuple[bool, str]]:
        self.appels.append((tuple(criteria), pass_id))
        oui = self.votes[pass_id % len(self.votes)]
        return {c: (oui, f"{self.model_id}:{c}") for c in criteria}


def _question(forme: str = "free", type_: str = "factual") -> Question:
    return Question.model_validate(
        {
            "id": "q-1",
            "type": type_,
            "text": "Q ?",
            "lang": "fr",
            "reference_answer": "42",
            "answer_form": forme,
            "status": "validated",
            "origin": {"kind": "human", "name": "t"},
        }
    )


def _answer(
    texte: str = "42", abstained: bool = False, cites: tuple[str, ...] = ("d#a",)
) -> Answer:
    return Answer.model_validate(
        {
            "text": texte,
            "abstained": abstained,
            "citations": [Citation(anchor_id=c) for c in cites],
            "answer_id": "r/c/standard/all/base/q-1",
            "question_id": "q-1",
            "config_id": "c",
            "status": "ok",
            "context_texts": ["ctx"],
        }
    )


def _juger(
    juges: list[_Juge], passes: int = 1, question: Question | None = None
) -> tuple[Any, Any]:
    verdicts, panel = _Liste(), _Liste()
    juger_reponse(
        _answer(),
        question or _question(),
        reference_texts=["texte"],
        reference_anchor_ids={"d#a"},
        corpus_anchor_ids={"d#a"},
        juges={j.model_id: j for j in juges},
        passes=passes,
        deja={},
        deja_panel=set(),
        verdicts=verdicts,
        panel=panel,
    )
    return verdicts.lignes, {(p["criterion"]): p for p in panel.lignes}


def test_majorite_et_egalite() -> None:
    assert majorite("a", "correctness", [True, True, False], ["x", "y", "z"]).verdict
    egalite = majorite("a", "correctness", [True, False], ["x", "y"])
    assert egalite == PanelVerdict(
        answer_id="a", criterion="correctness", verdict=False, tie=True, judges=("x", "y")
    )
    assert not majorite("a", "correctness", [False, False], ["x", "y"]).tie


def test_panel_de_deux_juges_en_desaccord_egalite_donne_non_et_tie() -> None:
    verdicts, panel = _juger([_Juge("j1", True), _Juge("j2", False)])
    assert panel["correctness"]["verdict"] is False and panel["correctness"]["tie"] is True
    assert panel["completeness"]["judges"] == ["j1", "j2"]
    # 2 Juges x 3 Critères jugés + 2 Critères automatiques.
    assert len(verdicts) == 8
    assert {v["judge_model"] for v in verdicts} == {"j1", "j2", "auto"}
    assert panel["citation_correctness"] == {
        "answer_id": "r/c/standard/all/base/q-1",
        "criterion": "citation_correctness",
        "verdict": True,
        "tie": False,
        "judges": [],
    }


def test_trois_juges_majorite_un_appel_chacun_tous_les_criteres() -> None:
    juges = [_Juge("j1", True), _Juge("j2", True), _Juge("j3", False)]
    _, panel = _juger(juges)
    assert all(p["verdict"] for k, p in panel.items() if k in {"correctness", "faithfulness"})
    assert [j.appels for j in juges] == [[(("correctness", "completeness", "faithfulness"), 0)]] * 3


def test_reponse_courte_correctness_exact_match_et_juges_sur_les_deux_autres() -> None:
    juge = _Juge("j1", False)
    verdicts, panel = _juger([juge, _Juge("j2", False)], question=_question("short"))
    assert juge.appels == [(("completeness", "faithfulness"), 0)]
    auto = [v for v in verdicts if v["criterion"] == "correctness"]
    assert [(v["judge_model"], v["verdict"]) for v in auto] == [("auto", True)]  # « 42 » ⊂ « 42 »
    assert panel["correctness"]["verdict"] is True and panel["correctness"]["judges"] == []


def test_passes_multiples_une_voix_par_passe() -> None:
    verdicts, panel = _juger([_Juge("j1", True, False), _Juge("j2", True, True)], passes=2)
    jugees = [v for v in verdicts if v["judge_model"] == "j1"]
    assert sorted({v["pass_id"] for v in jugees}) == [0, 1]
    assert (
        panel["completeness"]["verdict"] is True and not panel["completeness"]["tie"]
    )  # 3 oui / 1 non


def test_reprise_ne_demande_que_les_cles_absentes_et_n_ecrit_pas_deux_fois() -> None:
    verdicts, panel = _Liste(), _Liste()
    j1, j2 = _Juge("j1", True), _Juge("j2", True)

    def appeler(juges: dict[str, Any], deja: dict[Any, Verdict], deja_panel: set[Any]) -> int:
        return juger_reponse(
            _answer(),
            _question(),
            reference_texts=["t"],
            reference_anchor_ids={"d#a"},
            corpus_anchor_ids={"d#a"},
            juges=juges,
            passes=1,
            deja=deja,
            deja_panel=deja_panel,
            verdicts=verdicts,
            panel=panel,
        )

    # Premier passage interrompu : seul j1 a répondu (j2 en échec -> aucune voix, panel absent).
    class Panne(_Juge):
        def judge(self, item: JudgeInput, criteria: Sequence[Criterion], pass_id: int) -> Any:
            raise RuntimeError("panne")

    manque = appeler({"j1": j1, "j2": Panne("j2", True)}, {}, set())
    assert manque == 3 and len(verdicts.lignes) == 5  # 3 voix de j1 + 2 automatiques
    deja = {
        (v["answer_id"], v["judge_model"], v["criterion"], v["pass_id"]): Verdict.model_validate(v)
        for v in verdicts.lignes
    }
    deja_panel = {(p["answer_id"], p["criterion"]) for p in panel.lignes}
    j1.appels.clear()
    manque = appeler({"j1": j1, "j2": j2}, deja, deja_panel)
    assert manque == 0 and j1.appels == [] and len(j2.appels) == 1
    assert len(verdicts.lignes) == 8  # 3 voix de j2 en plus, aucun doublon
    assert len({(p["answer_id"], p["criterion"]) for p in panel.lignes}) == len(panel.lignes) == 5


def test_critere_automatique_unanswerable() -> None:
    q = _question(type_="unanswerable")
    muette = _answer("Le Corpus ne le dit pas.", abstained=True, cites=())
    v = {x.criterion: x.verdict for x in verdicts_automatiques(muette, q, set(), {"d#a"})}
    assert v == {"citation_correctness": True, "abstention_correctness": True}
    bavarde = _answer("42", abstained=False, cites=("d#a",))
    v = {x.criterion: x.verdict for x in verdicts_automatiques(bavarde, q, set(), {"d#a"})}
    assert v == {"citation_correctness": False, "abstention_correctness": False}
    assert criteres_juges(q) == ("correctness", "completeness", "faithfulness")
