"""Story 4.9 : majorité, égalité et reprise du Panel (Juges factices, sans Exécution)."""

from collections.abc import Sequence
from typing import Any

from wavelibrarian.core.types import Answer, Citation, Criterion, Question, Verdict, VerdictValue
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
    """Juge factice : `votes` donne son verdict par passe (booléen : `yes` / `no`) ; compte ses
    appels."""

    def __init__(self, model_id: str, *votes: bool | VerdictValue) -> None:
        self.model_id = model_id
        self.votes = votes
        self.appels: list[tuple[tuple[str, ...], int]] = []

    def judge(
        self, item: JudgeInput, criteria: Sequence[Criterion], pass_id: int
    ) -> dict[Criterion, tuple[VerdictValue, str]]:
        self.appels.append((tuple(criteria), pass_id))
        vote = self.votes[pass_id % len(self.votes)]
        v: VerdictValue = vote if isinstance(vote, str) else ("yes" if vote else "no")
        return {c: (v, f"{self.model_id}:{c}") for c in criteria}


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
    juges: list[_Juge],
    passes: int = 1,
    question: Question | None = None,
    answer: Answer | None = None,
) -> tuple[Any, Any]:
    verdicts, panel = _Liste(), _Liste()
    juger_reponse(
        answer or _answer(),
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
    assert majorite("a", "correctness", ["yes", "yes", "no"], ["x", "y", "z"]).verdict == "yes"
    egalite = majorite("a", "correctness", ["yes", "no"], ["x", "y"])
    assert egalite == PanelVerdict(
        answer_id="a", criterion="correctness", verdict="no", tie=True, judges=("x", "y")
    )
    assert not majorite("a", "correctness", ["no", "no"], ["x", "y"]).tie


def test_panel_de_deux_juges_en_desaccord_egalite_donne_non_et_tie() -> None:
    verdicts, panel = _juger([_Juge("j1", True), _Juge("j2", False)])
    assert panel["correctness"]["verdict"] == "no" and panel["correctness"]["tie"] is True
    assert panel["completeness"]["judges"] == ["j1", "j2"]
    # 2 Juges x 3 Critères jugés + 2 Critères automatiques.
    assert len(verdicts) == 8
    assert {v["judge_model"] for v in verdicts} == {"j1", "j2", "auto"}
    assert panel["citation_correctness"] == {
        "answer_id": "r/c/standard/all/base/q-1",
        "criterion": "citation_correctness",
        "verdict": "yes",
        "tie": False,
        "judges": [],
    }


def test_trois_juges_majorite_un_appel_chacun_tous_les_criteres() -> None:
    juges = [_Juge("j1", True), _Juge("j2", True), _Juge("j3", False)]
    _, panel = _juger(juges)
    assert all(
        p["verdict"] == "yes" for k, p in panel.items() if k in {"correctness", "faithfulness"}
    )
    assert [j.appels for j in juges] == [[(("correctness", "completeness", "faithfulness"), 0)]] * 3


def test_reponse_courte_correctness_exact_match_et_juges_sur_les_deux_autres() -> None:
    juge = _Juge("j1", False)
    verdicts, panel = _juger([juge, _Juge("j2", False)], question=_question("short"))
    assert juge.appels == [(("completeness", "faithfulness"), 0)]
    auto = [v for v in verdicts if v["criterion"] == "correctness"]
    assert [(v["judge_model"], v["verdict"]) for v in auto] == [("auto", "yes")]  # « 42 » ⊂ « 42 »
    assert panel["correctness"]["verdict"] == "yes" and panel["correctness"]["judges"] == []


def test_passes_multiples_une_voix_par_passe() -> None:
    verdicts, panel = _juger([_Juge("j1", True, False), _Juge("j2", True, True)], passes=2)
    jugees = [v for v in verdicts if v["judge_model"] == "j1"]
    assert sorted({v["pass_id"] for v in jugees}) == [0, 1]
    assert (
        panel["completeness"]["verdict"] == "yes" and not panel["completeness"]["tie"]
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
    assert v == {
        "citation_correctness": "yes",
        "abstention_correctness": "yes",
        "faithfulness": "na",  # abstention : rien d'affirmé (story 9.3)
    }
    bavarde = _answer("42", abstained=False, cites=("d#a",))
    v = {x.criterion: x.verdict for x in verdicts_automatiques(bavarde, q, set(), {"d#a"})}
    assert v == {"citation_correctness": "no", "abstention_correctness": "no"}
    assert criteres_juges(q) == ("correctness", "completeness", "faithfulness")


# --- Story 9.3 : modalité « sans objet » -------------------------------------------------------


def test_majorite_na_seulement_si_plus_de_la_moitie_des_voix() -> None:
    assert majorite("a", "faithfulness", ["na", "na", "yes"], ["x"]).verdict == "na"
    # Moitié de `na` seulement : majorité des yes / no restants.
    assert majorite("a", "faithfulness", ["na", "yes"], ["x"]).verdict == "yes"
    assert majorite("a", "faithfulness", ["na", "no", "yes", "no"], ["x"]).verdict == "no"
    egalite = majorite("a", "faithfulness", ["na", "na", "yes", "no"], ["x"])
    assert (egalite.verdict, egalite.tie) == ("no", True)  # égalité inchangée : no et signalement
    toutes_na = majorite("a", "faithfulness", ["na", "na"], ["x", "y"])
    assert (toutes_na.verdict, toutes_na.tie) == ("na", False)


def test_reponse_vide_fidelite_na_sans_juge_autres_criteres_juges() -> None:
    juge = _Juge("j1", True)
    verdicts, panel = _juger([juge], answer=_answer("   ", cites=()))
    assert juge.appels == [(("correctness", "completeness"), 0)]  # un Critère de moins
    fid = [v for v in verdicts if v["criterion"] == "faithfulness"]
    assert [(v["judge_model"], v["verdict"]) for v in fid] == [("auto", "na")]
    assert panel["faithfulness"]["verdict"] == "na" and panel["faithfulness"]["judges"] == []
    assert panel["correctness"]["verdict"] == "yes"


def test_abstention_fidelite_na_sans_juge() -> None:
    juge = _Juge("j1", False)
    _, panel = _juger([juge], answer=_answer("Je ne sais pas.", abstained=True, cites=()))
    assert juge.appels == [(("correctness", "completeness"), 0)]
    assert panel["faithfulness"]["verdict"] == "na"
    assert criteres_juges(_question(), _answer("", cites=())) == ("correctness", "completeness")
    assert criteres_juges(_question("short"), _answer("")) == ("completeness",)


def test_juge_na_en_fidelite_majorite_et_na_ailleurs_non_conforme() -> None:
    verdicts, panel = _juger([_Juge("j1", "na"), _Juge("j2", "na"), _Juge("j3", "yes")])
    assert panel["faithfulness"]["verdict"] == "na"
    assert panel["faithfulness"]["judges"] == ["j1", "j2", "j3"]
    # `na` sur correctness et completeness : clés laissées absentes, pas de verdict de panel.
    assert {v["criterion"] for v in verdicts if v["judge_model"] == "j1"} == {"faithfulness"}
    assert "correctness" not in panel and "completeness" not in panel


def test_anciennes_lignes_booleennes_relues() -> None:
    """Compatibilité : `verdicts.jsonl` et `panel.jsonl` d'avant la v0.3.0 (booléens)."""
    v = Verdict.model_validate(
        {"answer_id": "a", "judge_model": "j", "criterion": "correctness", "verdict": True}
    )
    p = PanelVerdict.model_validate(
        {"answer_id": "a", "criterion": "faithfulness", "verdict": False, "tie": True}
    )
    assert (v.verdict, p.verdict) == ("yes", "no")
    assert v.model_dump(mode="json")["verdict"] == "yes"


def test_juge_unique_une_passe_verdict_du_juge_na_compris() -> None:
    """Revue 9.3 : Panel d'un seul Juge à une passe (Expériences livrées) : le verdict de panel
    de `faithfulness` est celui du Juge, `na` compris, sans égalité signalée."""
    for vote in ("yes", "no", "na"):
        _, panel = _juger([_Juge("j1", vote)], question=_question(), answer=_answer())
        fid = panel["faithfulness"]
        assert (fid["verdict"], fid["tie"], fid["judges"]) == (vote, False, ["j1"])


def test_plusieurs_passes_chaque_passe_est_une_voix() -> None:
    """Revue 9.3 : avec `passes` > 1, les voix sont confondues (Juges et passes) : un Juge qui dit
    `na` à deux passes sur trois l'emporte sur son `yes`."""
    _, panel = _juger([_Juge("j1", "na", "na", "yes")], passes=3)
    assert panel["faithfulness"]["verdict"] == "na"
    _, panel = _juger([_Juge("j1", "na", "yes", "no")], passes=3)
    assert (panel["faithfulness"]["verdict"], panel["faithfulness"]["tie"]) == ("no", True)
