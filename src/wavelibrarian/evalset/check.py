"""Contrôle des Questions : Ancrages résolus, forme des Réponses (FR-9, FR-11, FR-36)."""

from collections import Counter
from dataclasses import dataclass, field

from wavelibrarian.core.types import AnchorRef, ParsedCorpus, Question
from wavelibrarian.evalset.io import QuestionsFile
from wavelibrarian.scoring.answer import is_short_form

STATUTS = ("generated", "validated", "corrected", "rejected")
UTILISABLES = ("validated", "corrected")  # seules servent aux Exécutions
ETATS_SCENARIO = ("before", "after")


@dataclass(frozen=True)
class Signalement:
    question_id: str
    message: str
    bloquant: bool  # un signalement bloquant fait sortir `wl questions controler` en code 2


@dataclass(frozen=True)
class Controle:
    par_statut: dict[str, int]
    par_type: dict[str, int]
    utilisables: int
    target_count: int
    signalements: tuple[Signalement, ...] = field(default=())

    @property
    def ecart(self) -> int:
        """Questions utilisables manquantes pour atteindre `target_count` (négatif = surplus)."""
        return self.target_count - self.utilisables

    @property
    def echec(self) -> bool:
        return any(s.bloquant for s in self.signalements)


def _decrire(a: AnchorRef) -> str:
    titres = " > ".join(a.headings)
    if a.page is None:
        cible = titres or "(vide)"
    else:
        cible = f"page {a.page}" + (f", {titres}" if titres else "")
    return f"{a.doc} ({cible})"


def controler(
    doc: QuestionsFile, corpus: ParsedCorpus, corpus_apres: ParsedCorpus | None = None
) -> Controle:
    """Contrôle `doc` contre `corpus` ; `corpus_apres` (Scénario) résout les `state: after`.

    Anomalie d'une Question `validated` ou `corrected` : bloquante. Pour `generated` ou
    `rejected` : simple signalement. Sans `corpus_apres`, une Question `scenario_target`
    à l'état `after` est « non vérifiable », sans échec.
    """
    signaux: list[Signalement] = []
    for q in doc.questions:
        utilisable = q.status in UTILISABLES
        signaux.extend(_structure(q, utilisable))
        signaux.extend(_ancrages(q, utilisable, corpus, corpus_apres))
        if (
            q.answer_form == "short"
            and q.reference_answer
            and not is_short_form(q.reference_answer)
        ):
            signaux.append(
                Signalement(
                    q.id,
                    f"Réponse de référence incohérente avec answer_form: short "
                    f"({q.reference_answer!r} : plus de 5 mots, ni nombre ni date)",
                    False,
                )
            )
    statuts = Counter(q.status for q in doc.questions)
    types = Counter(q.type for q in doc.questions)
    return Controle(
        par_statut={s: statuts.get(s, 0) for s in STATUTS},
        par_type=dict(sorted(types.items())),
        utilisables=sum(statuts.get(s, 0) for s in UTILISABLES),
        target_count=doc.target_count,
        signalements=tuple(signaux),
    )


def _structure(q: Question, bloquant: bool) -> list[Signalement]:
    if q.type == "unanswerable" and q.reference_anchors:
        return [Signalement(q.id, "Question unanswerable avec des reference_anchors", bloquant)]
    if q.type != "unanswerable" and not q.reference_anchors:
        return [Signalement(q.id, f"Question {q.type} sans reference_anchors", bloquant)]
    return []


def _ancrages(
    q: Question, bloquant: bool, base: ParsedCorpus, apres: ParsedCorpus | None
) -> list[Signalement]:
    cible = q.scenario_target
    etat = None
    if cible is not None:
        etat = cible.get("state")
        if etat not in ETATS_SCENARIO or "operation" not in cible:
            return [
                Signalement(
                    q.id,
                    f"scenario_target invalide {cible!r} (operation et state before|after)",
                    bloquant,
                )
            ]
    corpus = base
    if etat == "after" and q.reference_anchors:
        if apres is None:
            return [
                Signalement(
                    q.id,
                    "Ancrages non vérifiables sans --scenario (scenario_target: state after)",
                    False,
                )
            ]
        corpus = apres
    sortie: list[Signalement] = []
    for a in q.reference_anchors:
        if a.page is not None and a.headings:
            message = f"Ancrage ambigu : page et headings sont exclusifs ({_decrire(a)})"
            sortie.append(Signalement(q.id, message, bloquant))
        elif corpus.resolve(a.doc, a.page, a.headings) is None:
            sortie.append(Signalement(q.id, f"Ancrage introuvable : {_decrire(a)}", bloquant))
    return sortie
