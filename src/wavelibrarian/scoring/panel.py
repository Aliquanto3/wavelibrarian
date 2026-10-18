"""Verdicts d'une Réponse : Critères automatiques et Panel de Juges (FR-36, FR-37, AD-14).

Ce module écrit, par l'intermédiaire de deux `Sink` fournis par le runner (seul écrivain des
JSONL), `verdicts.jsonl` (un `Verdict` par (answer_id, judge_model, criterion, pass_id)) et
`panel.jsonl` (verdict majoritaire par (answer_id, criterion)). Un Juge note tous ses Critères
en un seul appel par Réponse et par passe. La reprise ne demande que les clés absentes (AD-11).
"""

import logging
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.errors import BudgetExceeded
from wavelibrarian.core.types import (
    JUDGED_CRITERIA,
    Answer,
    Criterion,
    Question,
    Verdict,
)
from wavelibrarian.ports.components import ComponentSpec, Judge, JudgeInput
from wavelibrarian.scoring.answer import (
    JUGE_AUTO,
    abstention_correctness,
    citation_correctness,
    exact_match,
)

log = logging.getLogger(__name__)

AUTO_CRITERIA: tuple[Criterion, ...] = ("citation_correctness", "abstention_correctness")


class Sink(Protocol):
    def append(self, obj: Any) -> None: ...


class PanelVerdict(BaseModel):
    """Ligne de `panel.jsonl`. `judges` : Juges admissibles dont les voix comptent (vide pour un
    Critère automatique). Égalité : `verdict` faux et `tie` vrai."""

    model_config = ConfigDict(frozen=True)

    answer_id: str
    criterion: Criterion
    verdict: bool
    tie: bool = False
    judges: tuple[str, ...] = ()


CleVerdict = tuple[str, str, Criterion, int]  # (answer_id, judge_model, criterion, pass_id)


def cle(v: Verdict) -> CleVerdict:
    return (v.answer_id, v.judge_model, v.criterion, v.pass_id)


def criteres_juges(question: Question) -> tuple[Criterion, ...]:
    """Critères notés par un Juge : `correctness` est exclu d'une réponse courte (exact_match)."""
    if question.answer_form == "short":
        return tuple(c for c in JUDGED_CRITERIA if c != "correctness")
    return JUDGED_CRITERIA


def verdicts_automatiques(
    answer: Answer,
    question: Question,
    reference_anchor_ids: Collection[str],
    corpus_anchor_ids: Collection[str],
) -> list[Verdict]:
    """Critères sans Juge d'une Réponse `ok` : `citation_correctness`, `abstention_correctness`
    et, pour `answer_form: short`, `correctness` par `exact_match`."""
    inconnue = question.type == "unanswerable"
    cites = [c.anchor_id for c in answer.citations]
    oui: dict[Criterion, bool] = {
        "citation_correctness": citation_correctness(
            cites,
            reference_anchor_ids,
            corpus_anchor_ids,
            unanswerable=inconnue,
            invalid=answer.invalid_citations,
        ),
        "abstention_correctness": abstention_correctness(answer.abstained, unanswerable=inconnue),
    }
    if question.answer_form == "short":
        oui["correctness"] = exact_match(question.reference_answer, answer.text)
    return [
        Verdict(answer_id=answer.answer_id, judge_model=JUGE_AUTO, criterion=c, verdict=v)
        for c, v in oui.items()
    ]


def majorite(
    answer_id: str, criterion: Criterion, votes: Sequence[bool], judges: Sequence[str]
) -> PanelVerdict:
    """Majorité des voix (Juges et passes confondus) ; égalité = `no` et `tie`."""
    oui = sum(votes)
    non = len(votes) - oui
    return PanelVerdict(
        answer_id=answer_id,
        criterion=criterion,
        verdict=oui > non,
        tie=oui == non,
        judges=tuple(judges),
    )


def juger_reponse(
    answer: Answer,
    question: Question,
    *,
    reference_texts: Sequence[str],
    reference_anchor_ids: Collection[str],
    corpus_anchor_ids: Collection[str],
    juges: Mapping[str, Judge],
    passes: int,
    deja: Mapping[CleVerdict, Verdict],
    deja_panel: Collection[tuple[str, str]],
    verdicts: Sink,
    panel: Sink,
) -> int:
    """Note une Réponse `ok` et écrit ses lignes absentes ; rend le nombre de Critères sans
    verdict de panel faute de voix (appel d'un Juge en échec). `BudgetExceeded` remonte.

    `deja` : verdicts déjà écrits (reprise) ; `juges` : le Panel admissible, par modèle, appelé
    dans l'ordre. Aucun Juge n'est appelé pour une clé déjà présente."""
    connus = dict(deja)

    def ecrire(v: Verdict) -> None:
        if cle(v) not in connus:
            verdicts.append(v.model_dump(mode="json"))
            connus[cle(v)] = v

    for v in verdicts_automatiques(answer, question, reference_anchor_ids, corpus_anchor_ids):
        ecrire(v)
    criteres: tuple[Criterion, ...] = criteres_juges(question)
    item = JudgeInput(
        question=question.text,
        reference_answer=question.reference_answer,
        reference_texts=tuple(reference_texts),
        answer_text=answer.text,
        context_texts=answer.context_texts,
    )
    for modele, juge in juges.items():
        for passe in range(passes):
            manquants: list[Criterion] = [
                c for c in criteres if (answer.answer_id, modele, c, passe) not in connus
            ]
            if not manquants:
                continue
            try:
                notes = juge.judge(item, manquants, passe)
            except BudgetExceeded:
                raise
            except Exception as exc:  # AD-11 : la Réponse suivante est jugée
                log.warning("Juge %s en échec sur %s : %s", modele, answer.answer_id, exc)
                continue
            for c in manquants:
                if c not in notes:  # Critère absent de la sortie : clé laissée absente (reprise)
                    log.warning("Juge %s sans verdict %s sur %s", modele, c, answer.answer_id)
                    continue
                oui, justification = notes[c]
                ecrire(
                    Verdict(
                        answer_id=answer.answer_id,
                        judge_model=modele,
                        criterion=c,
                        pass_id=passe,
                        verdict=oui,
                        justification=justification,
                    )
                )
    return ecrire_panel(answer.answer_id, criteres, list(juges), passes, connus, deja_panel, panel)


def ecrire_panel(
    answer_id: str,
    criteres_juges_: Iterable[Criterion],
    modeles: Sequence[str],
    passes: int,
    verdicts: Mapping[CleVerdict, Verdict],
    deja_panel: Collection[tuple[str, str]],
    panel: Sink,
) -> int:
    """Écrit les lignes de `panel.jsonl` absentes. Un Critère automatique prend sa voix unique ;
    un Critère jugé n'est agrégé que si chaque Juge du Panel a voté à chaque passe. Rend le nombre
    de Critères jugés laissés sans verdict de panel."""
    manquants = 0
    automatiques: list[Criterion] = [
        c for (a, j, c, _) in verdicts if a == answer_id and j == JUGE_AUTO
    ]
    for c in dict.fromkeys(automatiques):
        if (answer_id, c) not in deja_panel:
            v = verdicts[(answer_id, JUGE_AUTO, c, 0)]
            panel.append(majorite(answer_id, c, [v.verdict], []).model_dump(mode="json"))
    jugees: list[Criterion] = list(criteres_juges_)
    for c in jugees:
        if (answer_id, c) in deja_panel:
            continue
        cles: list[CleVerdict] = [(answer_id, m, c, p) for m in modeles for p in range(passes)]
        if any(k not in verdicts for k in cles):
            manquants += 1
            continue
        ligne = majorite(answer_id, c, [verdicts[k].verdict for k in cles], modeles)
        panel.append(ligne.model_dump(mode="json"))
    return manquants


def construire_juges(
    ctx: Any, modeles: Iterable[str], *, cache_later_passes: bool = True
) -> dict[str, Judge]:
    """Un Juge `llm` par modèle du Panel, construit par le contexte (AD-2) ;
    `cache_later_passes=False` (calibration) : passes >= 1 hors Cache de réponses."""
    params: dict[str, Any] = {} if cache_later_passes else {"cache_later_passes": False}
    return {
        m: ctx.build("judge", ComponentSpec(name="llm", params={"model": m, **params}))
        for m in modeles
    }
