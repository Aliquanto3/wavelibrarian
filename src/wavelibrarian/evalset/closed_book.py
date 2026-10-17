"""Filtre closed-book (FR-12, AD-8 Poste `judging`, AD-14, AD-15).

Chaque Question `validated` ou `corrected` (hors `unanswerable`) est posée sans contexte à chaque
modèle, au rôle `closed_book`. Réponse courte : correspondance exacte normalisée, sans Juge.
Réponse libre : verdict `correctness` du Juge `closed_book_judge`, d'une autre Famille que le
modèle testé. Un modèle qui trouve la Réponse de référence va dans `contaminated_by`.
Seul `contaminated_by` change : l'empreinte du Gel l'exclut (AD-15). Rien n'est écrit ici.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from wavelibrarian.config.panel import closed_book_judge
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import Question
from wavelibrarian.evalset.generate import ContexteGeneration
from wavelibrarian.evalset.io import QuestionsFile
from wavelibrarian.ports.components import ComponentSpec, Judge, JudgeInput
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.scoring.answer import exact_match

STATUTS = frozenset({"validated", "corrected"})
_SYSTEM = "Réponds à la question de mémoire, sans document, en une ou deux phrases."
_MAX_TOKENS = 256


@dataclass(frozen=True)
class Verdict:
    question_id: str
    modele: str
    contaminee: bool
    methode: str  # "exact" (réponse courte) ou "juge:<modèle>"


@dataclass(frozen=True)
class Filtrage:
    fichier: QuestionsFile
    verdicts: tuple[Verdict, ...]
    exclues: tuple[str, ...]  # `unanswerable` : ne passent pas le filtre
    ignorees: int  # Questions hors statut validated / corrected

    @property
    def contaminees(self) -> dict[str, tuple[str, ...]]:
        res: dict[str, list[str]] = {}
        for v in self.verdicts:
            if v.contaminee:
                res.setdefault(v.question_id, []).append(v.modele)
        return {k: tuple(m) for k, m in res.items()}


def valider_modeles(modeles: Sequence[str], catalog: Any) -> tuple[str, ...]:
    """Modèles au Catalogue, sans doublon, au moins un ; `ConfigError` sinon (hors réseau)."""
    if not modeles:
        raise ConfigError("--modeles", "au moins un modèle est attendu")
    if len(set(modeles)) != len(modeles):
        raise ConfigError("--modeles", f"modèle répété : {', '.join(modeles)}")
    for m in modeles:
        catalog.get(m)
    return tuple(modeles)


def filtrer(ctx: ContexteGeneration, fichier: QuestionsFile, modeles: Sequence[str]) -> Filtrage:
    """Pose les Questions sans contexte à `modeles` ; `BudgetExceeded` si le Plafond l'interdit."""
    modeles = valider_modeles(modeles, ctx.catalog)
    retenues = [q for q in fichier.questions if q.status in STATUTS and q.type != "unanswerable"]
    juges: dict[str, str] = {}
    if any(q.answer_form == "free" for q in retenues):  # échec avant tout appel payant
        pool = ctx.profile.defaults.judge_pool
        juges = {m: closed_book_judge(m, pool, ctx.catalog) for m in modeles}
    instances: dict[str, Judge] = {}
    verdicts: list[Verdict] = []
    for q in retenues:
        for modele in modeles:
            with ctx.scope(post="judging", question_id=q.id):
                reponse = sans_question(_poser(ctx, q, modele), q.text)
                if q.answer_form == "short":
                    contaminee, methode = exact_match(q.reference_answer, reponse), "exact"
                else:
                    jm = juges[modele]
                    if jm not in instances:
                        spec = ComponentSpec(name="llm", params={"model": jm})
                        instances[jm] = ctx.build("judge", spec)
                    item = JudgeInput(
                        question=q.text,
                        reference_answer=q.reference_answer,
                        reference_texts=(),
                        answer_text=reponse,
                        context_texts=(),
                    )
                    # la justification n'est pas exigée (contracts §2 : `justification = ""`)
                    note = instances[jm].judge(item, ["correctness"], 0)
                    contaminee, methode = note["correctness"][0], f"juge:{jm}"
            verdicts.append(Verdict(q.id, modele, contaminee, methode))
    nouveaux = _appliquer(fichier, verdicts, modeles, {q.id for q in retenues})
    return Filtrage(
        fichier=nouveaux,
        verdicts=tuple(verdicts),
        exclues=tuple(
            q.id for q in fichier.questions if q.status in STATUTS and q.type == "unanswerable"
        ),
        ignorees=sum(1 for q in fichier.questions if q.status not in STATUTS),
    )


def sans_question(reponse: str, question: str) -> str:
    """Réponse privée de la question qu'elle recopie (casse et espaces ignorés).

    Une réponse qui répète la question, comme le Faux LLM au rôle `closed_book` (contracts §3),
    ne doit pas passer pour contaminée parce que la question partage des mots avec la référence.
    """
    mots = question.split()
    if not mots:
        return reponse
    motif = r"\s+".join(re.escape(m) for m in mots)
    return re.sub(motif, " ", reponse, flags=re.IGNORECASE).strip()


def _poser(ctx: ContexteGeneration, q: Question, modele: str) -> str:
    requete = LLMRequest(
        model_id=modele,
        role="closed_book",
        step="closed_book",
        system=_SYSTEM,
        messages=(Message(role="user", content=q.text),),
        max_tokens=min(_MAX_TOKENS, ctx.catalog.get(modele).max_output_tokens or _MAX_TOKENS),
        seed=ctx.seed,
        inputs={"text": q.text},
    )
    return ctx.gateway.complete(requete).text


def _appliquer(
    fichier: QuestionsFile, verdicts: Sequence[Verdict], modeles: Sequence[str], testees: set[str]
) -> QuestionsFile:
    """Remplace les entrées des modèles testés ; celles des autres modèles sont conservées."""
    questions: list[Question] = []
    for q in fichier.questions:
        if q.id not in testees:
            questions.append(q)
            continue
        trouves = [v.modele for v in verdicts if v.question_id == q.id and v.contaminee]
        # ordre stable : les entrées confirmées gardent leur place, les nouvelles vont à la fin
        gardes = [m for m in q.contaminated_by if m not in modeles or m in trouves]
        nouveaux = tuple((*gardes, *(m for m in trouves if m not in gardes)))
        questions.append(q.model_copy(update={"contaminated_by": nouveaux}))
    return fichier.model_copy(update={"questions": tuple(questions)})
