"""Génération de Questions candidates (FR-10, AD-4 rôle `question_gen`, AD-8 Poste `evalset`).

Un seul appel de passerelle par génération : le modèle reçoit un échantillon d'Ancrages du Corpus
(tiré par `ctx.rng`, AD-20) et la répartition demandée. Chaque Question retenue est `generated`,
ancrée sur des Ancrages qui se résolvent dans le Corpus (sauf `unanswerable`), avec un `id` neuf.
Rien n'est écrit par ce module : l'appelant sauvegarde le fichier une fois la génération terminée,
donc un plafond atteint ne laisse aucune écriture partielle.
"""

import json
import re
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Protocol, get_args

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import (
    AnchorRef,
    CostPost,
    ParsedCorpus,
    Question,
    QuestionType,
)
from wavelibrarian.evalset.io import QuestionsFile
from wavelibrarian.llm.roles import QuestionGenOutput
from wavelibrarian.ports.context import RunContext
from wavelibrarian.ports.gateway import LLMRequest, Message

TYPES = frozenset(get_args(QuestionType))
_ID = re.compile(r"q-(\d+)")
_TEXTE_MAX = 1500  # caractères d'un Ancrage présentés au modèle
_SYSTEM = (
    "Tu rédiges des Questions d'évaluation pour un système de recherche documentaire. "
    "Pour chaque Question : un type parmi ceux demandés, un texte, une réponse de référence "
    "courte, `answer_form` (`short` ou `free`) et les `anchor_ids` des passages qui la fondent "
    "(aucun pour `unanswerable`). N'utilise que les `anchor_id` fournis. "
    "Respecte le nombre de Questions demandé pour chaque type."
)


class ContexteGeneration(RunContext, Protocol):
    """`RunContext` plus `scope`, que le contexte concret du runner fournit."""

    def scope(
        self, *, post: CostPost = ..., question_id: str | None = ...
    ) -> AbstractContextManager[None]: ...


@dataclass(frozen=True)
class Rejet:
    type: str
    motif: str


@dataclass(frozen=True)
class Generation:
    """Résultat d'une génération : le fichier complété et le détail du tri."""

    fichier: QuestionsFile
    ajoutees: tuple[Question, ...]
    rejetees: tuple[Rejet, ...]  # écartées à la génération (Ancrage absent, type inconnu…)
    en_trop: int  # au-delà de la répartition demandée
    manquantes: Mapping[str, int] = field(default_factory=dict)  # type -> Questions non obtenues
    cout: str = "0"
    depuis_cache: bool = False
    ancrages: tuple[str, ...] = ()  # échantillon présenté au modèle


def parse_repartition(texte: str) -> dict[str, int]:
    """`factual=3,multi_hop=1` -> `{"factual": 3, "multi_hop": 1}` ; `ConfigError` sinon."""
    resultat: dict[str, int] = {}
    for morceau in texte.split(","):
        nom, sep, nombre = morceau.partition("=")
        nom = nom.strip()
        if not sep or not nom:
            raise ConfigError("--repartition", f"entrée mal formée : {morceau.strip()!r}")
        if nom not in TYPES:
            raise ConfigError(
                "--repartition", f"Type inconnu : {nom!r} (connus : {', '.join(sorted(TYPES))})"
            )
        if nom in resultat:
            raise ConfigError("--repartition", f"Type répété : {nom!r}")
        if not nombre.strip().isdigit() or int(nombre) < 1:
            raise ConfigError("--repartition", f"{nom} : un entier au moins égal à 1 est attendu")
        resultat[nom] = int(nombre)
    return resultat


def _prochain_numero(ids: set[str]) -> int:
    nums = [int(m.group(1)) for i in ids if (m := _ID.fullmatch(i))]
    return max(nums, default=0) + 1


def _ref(corpus: ParsedCorpus, anchor_id: str) -> AnchorRef | None:
    """Forme YAML de l'Ancrage, seulement si elle se résout sur le même `anchor_id`."""
    for doc in corpus.documents:
        a = doc.anchors.get(anchor_id)
        if a is None:
            continue
        ref = (
            AnchorRef(doc=a.source_path, page=a.page)
            if a.page is not None
            else AnchorRef(doc=a.source_path, headings=a.heading_path)
        )
        if corpus.resolve(ref.doc, ref.page, ref.headings) == anchor_id:
            return ref
        return None
    return None


def echantillon_ancrages(ctx: RunContext, corpus: ParsedCorpus, n: int) -> list[str]:
    """`n` Ancrages au texte non vide, tirés par `ctx.rng` (même graine, même échantillon)."""
    candidats = sorted(
        a for d in corpus.documents for a in d.anchors if corpus.anchor_text(a).strip()
    )
    if not candidats:
        raise ConfigError("corpus", "aucun Ancrage exploitable dans le Corpus")
    tirage = ctx.rng("questions", "ancrages", corpus.corpus_id).sample(
        candidats, min(n, len(candidats))
    )
    return sorted(tirage)


def generer(
    ctx: ContexteGeneration,
    corpus: ParsedCorpus,
    existant: QuestionsFile,
    repartition: Mapping[str, int],
    modele: str,
) -> Generation:
    """Génère les Questions de `repartition` ; `BudgetExceeded` si le Plafond l'interdit.

    Les Questions existantes sont reprises telles quelles, les nouvelles sont ajoutées à la fin.
    """
    if not repartition:
        raise ConfigError("--repartition", "répartition vide")
    total = sum(repartition.values())
    ancrages = echantillon_ancrages(ctx, corpus, total)
    requete = LLMRequest(
        model_id=modele,
        role="question_gen",
        step="question_gen",
        system=_SYSTEM,
        messages=(
            Message(
                role="user",
                content=(
                    f"Répartition demandée : {json.dumps(dict(repartition))}\n"
                    f"Passages : {json.dumps(_passages(corpus, ancrages), ensure_ascii=False)}"
                ),
            ),
        ),
        max_tokens=min(600 * total + 400, ctx.catalog.get(modele).max_output_tokens or 4096),
        seed=ctx.seed,
        inputs={"anchors": _passages(corpus, ancrages), "types": dict(repartition)},
    )
    with ctx.scope(post="evalset", question_id=None):
        sortie, res = ctx.gateway.complete_structured(requete, QuestionGenOutput)

    langue = _langue(corpus, ancrages)
    ids = {q.id for q in existant.questions}
    numero = _prochain_numero(ids)
    presentes = set(ancrages)
    vues = {_cle(q.text, q.reference_anchors): q.id for q in existant.questions}
    restant = dict(repartition)
    ajoutees: list[Question] = []
    rejetees: list[Rejet] = []
    en_trop = 0
    for brute in sortie.questions:
        motif = _motif_rejet(brute.type, brute.text, brute.anchor_ids)
        refs: list[AnchorRef] = []
        if motif is None and brute.type != "unanswerable":
            for aid in brute.anchor_ids:
                ref = _ref(corpus, aid)
                if ref is None:
                    motif = f"Ancrage inconnu du Corpus : {aid!r}"
                    break
                if aid not in presentes:
                    motif = f"Ancrage hors de l'échantillon présenté : {aid!r}"
                    break
                refs.append(ref)
        cle = _cle(brute.text, refs)
        if motif is None:
            if cle in vues:
                motif = f"doublon de {vues[cle]}"
        if motif is not None:
            rejetees.append(Rejet(brute.type, motif))
            continue
        if restant.get(brute.type, 0) <= 0:
            en_trop += 1
            continue
        restant[brute.type] -= 1
        while f"q-{numero:03d}" in ids:
            numero += 1
        ident = f"q-{numero:03d}"
        ids.add(ident)
        vues[cle] = ident
        ajoutees.append(
            Question(
                id=ident,
                type=brute.type,  # pyright: ignore[reportArgumentType]  # validé par TYPES
                text=brute.text.strip(),
                lang=langue,
                reference_answer=brute.reference_answer.strip(),
                answer_form=brute.answer_form,
                reference_anchors=tuple(refs),
                status="generated",
                split=None,
                origin={"kind": "model", "name": modele},
            )
        )
    fichier = existant.model_copy(update={"questions": (*existant.questions, *ajoutees)})
    return Generation(
        fichier=fichier,
        ajoutees=tuple(ajoutees),
        rejetees=tuple(rejetees),
        en_trop=en_trop,
        manquantes={t: n for t, n in restant.items() if n > 0},
        cout=f"{res.cost:f}",
        depuis_cache=res.from_cache,
        ancrages=tuple(ancrages),
    )


def _motif_rejet(type_: str, texte: str, anchor_ids: list[str]) -> str | None:
    if type_ not in TYPES:
        return f"Type inconnu : {type_!r}"
    if not texte.strip():
        return "texte de Question vide"
    if type_ != "unanswerable" and not anchor_ids:
        return "aucun Ancrage cité"
    return None  # une `unanswerable` n'a pas d'Ancrage : ceux que le modèle cite sont ignorés


def _cle(texte: str, refs: Iterable[AnchorRef]) -> tuple[str, frozenset[str]]:
    """Même texte (casse et espaces normalisés) et mêmes Ancrages : même Question."""
    return (
        " ".join(texte.split()).casefold(),
        frozenset(r.model_dump_json() for r in refs),
    )


def _passages(corpus: ParsedCorpus, ancrages: list[str]) -> list[dict[str, str]]:
    return [{"anchor_id": a, "text": corpus.anchor_text(a)[:_TEXTE_MAX]} for a in ancrages]


def _langue(corpus: ParsedCorpus, ancrages: list[str]) -> str:
    """Langue du Document du premier Ancrage présenté (`fr` par défaut)."""
    for doc in corpus.documents:
        if ancrages and ancrages[0] in doc.anchors:
            return doc.lang
    return corpus.documents[0].lang if corpus.documents else "fr"
