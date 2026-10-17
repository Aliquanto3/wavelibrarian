"""Faux LLM (AD-4, contracts.md §3) : une sortie valide et déterministe par rôle, sans réseau.

Il ne lit que `LLMRequest.inputs`, jamais le texte du prompt, sauf pour compter les mots
(tokens) et reconnaître un préfixe déjà vu (`cache_read_tokens`). Latence nulle.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

from pydantic import BaseModel

from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import Usage
from wavelibrarian.llm.providers.base import ProviderResponse
from wavelibrarian.llm.roles import (
    ROLES,
    AgentStepOutput,
    CriterionVerdict,
    Entity,
    ExtractEntitiesOutput,
    GeneratedQuestion,
    GenerateOutput,
    GradeRelevanceOutput,
    JudgeOutput,
    QuestionGenOutput,
    Relation,
    SelectNodesOutput,
    WikiCompileOutput,
    WikiFidelityOutput,
    WikiPage,
    check_inputs,
)
from wavelibrarian.ports.gateway import LLMRequest

ScriptOutput = str | Callable[[LLMRequest], str]

_PHRASE = re.compile(r"(?<=[.!?])\s+")
_MOT = re.compile(r"\w+")
_CAPITALISEE = re.compile(r"\b[^\W\d_a-z][\w'-]*(?:[ \t]+[^\W\d_a-z][\w'-]*)*")
_ABSTENTION = "Information introuvable dans les sources."


def _mots(texte: str) -> set[str]:
    return {m.lower() for m in _MOT.findall(texte)}


def _phrases(texte: str) -> list[str]:
    return [p for p in _PHRASE.split(texte.strip()) if p]


def _premiere_phrase(texte: str) -> str:
    phrases = _phrases(texte)
    return phrases[0] if phrases else ""


def _generate(inputs: dict[str, Any]) -> BaseModel:
    bloc = inputs["blocks"].get("S1")
    if not bloc:  # `blocks` vide (ou sans S1) : rien à citer
        return GenerateOutput(answer=_ABSTENTION, citations=[], abstain=True)
    return GenerateOutput(answer=_premiere_phrase(bloc), citations=["S1"], abstain=False)


def _judge(inputs: dict[str, Any]) -> BaseModel:
    reference = _mots(inputs["reference_answer"])
    partages = len(reference & _mots(inputs["answer"]))
    oui = bool(reference) and partages * 2 >= len(reference)
    verdict = CriterionVerdict(
        verdict="yes" if oui else "no",
        justification=f"{partages}/{len(reference)} mots de la référence présents",
    )
    return JudgeOutput(verdicts={str(c): verdict for c in inputs["criteria"]})


def _extract_entities(inputs: dict[str, Any]) -> BaseModel:
    noms = list(dict.fromkeys(m.group(0) for m in _CAPITALISEE.finditer(inputs["text"])))
    entites = [Entity(name=n, kind="entity", description=f"Entité citée : {n}") for n in noms]
    relations = [
        Relation(source=a, target=b, description=f"{a} et {b} sont voisines", weight=1.0)
        for a, b in zip(noms, noms[1:], strict=False)
    ]
    return ExtractEntitiesOutput(entities=entites, relations=relations)


def _select_nodes(inputs: dict[str, Any]) -> BaseModel:
    question = _mots(inputs["question"])
    choisis = [
        str(n["id"])
        for n in inputs["nodes"]
        if question & _mots(f"{n.get('title', '')} {n.get('summary', '')}")
    ][: int(inputs["max"])]
    return SelectNodesOutput(node_ids=choisis, done=True)


def _agent_step(inputs: dict[str, Any]) -> BaseModel:
    etape = int(inputs["step"])
    resultats = inputs["last_results"]
    if etape <= 1:
        return AgentStepOutput(action="search", args={"query": inputs["question"]})
    if not resultats:
        return AgentStepOutput(
            action="answer", args={"answer": _ABSTENTION, "citations": [], "abstain": True}
        )
    premier = resultats[0]
    if etape == 2:
        return AgentStepOutput(action="read", args={"id": premier["id"]})
    return AgentStepOutput(
        action="answer",
        args={
            "answer": _premiere_phrase(premier["text"]),
            "citations": [premier["id"]],
            "abstain": False,
        },
    )


def _grade_relevance(inputs: dict[str, Any]) -> BaseModel:
    question = _mots(inputs["question"])
    scores = [
        len(question & _mots(p)) / len(question) if question else 0.0 for p in inputs["passages"]
    ]
    return GradeRelevanceOutput(scores=scores)


def _wiki_compile(inputs: dict[str, Any]) -> BaseModel:
    pages = []
    for doc in inputs["documents"]:
        blocs = doc["blocks"][:3]
        pages.append(
            WikiPage(
                title=doc["source_path"],
                body="\n\n".join(b["text"] for b in blocs),
                anchor_ids=[b["anchor_id"] for b in blocs],
            )
        )
    return WikiCompileOutput(pages=pages)


def _wiki_fidelity(inputs: dict[str, Any]) -> BaseModel:
    sources: set[str] = set()
    for s in inputs["sources"]:
        sources |= _mots(s)
    phrases = _phrases(inputs["page"])
    soutenues = 0
    for p in phrases:
        mots = _mots(p)
        if mots and len(mots & sources) * 2 >= len(mots):
            soutenues += 1
    return WikiFidelityOutput(claims=len(phrases), supported=soutenues)


def _question_gen(inputs: dict[str, Any]) -> BaseModel:
    return QuestionGenOutput(
        questions=[
            GeneratedQuestion(
                type="factual",
                text=f"Que dit le passage {a['anchor_id']} ?",
                reference_answer=_premiere_phrase(a["text"]),
                answer_form="free",
                anchor_ids=[a["anchor_id"]],
            )
            for a in inputs["anchors"]
        ]
    )


_STRUCTUREES: dict[str, Callable[[dict[str, Any]], BaseModel]] = {
    "generate": _generate,
    "judge": _judge,
    "extract_entities": _extract_entities,
    "select_nodes": _select_nodes,
    "agent_step": _agent_step,
    "grade_relevance": _grade_relevance,
    "wiki_compile": _wiki_compile,
    "wiki_fidelity": _wiki_fidelity,
    "question_gen": _question_gen,
}
_INCHANGES = frozenset({"rewrite", "closed_book"})  # la question n'est jamais contaminée


def default_output(role: str, inputs: dict[str, Any]) -> str:
    """Sortie par défaut du rôle (texte libre, ou JSON valide pour son schéma)."""
    fabrique = _STRUCTUREES.get(role)
    if fabrique is not None:
        return fabrique(inputs).model_dump_json()
    texte = str(inputs["text"])
    if role in _INCHANGES:
        return texte
    return " ".join(texte.split()[:30])


@dataclass(frozen=True)
class _Scenario:
    role: str
    step_glob: str
    output: ScriptOutput


class FakeProvider:
    """Implémente le protocole `Provider` ; un exemplaire garde sa mémoire de préfixes vus."""

    def __init__(self) -> None:
        self._scenarios: list[_Scenario] = []
        self._prefixes_vus: set[str] = set()

    def script(self, role: str, step_glob: str, output: ScriptOutput) -> None:
        """Sortie scénarisée (FR-52) pour le rôle et les étapes qui correspondent au glob.

        Elle prime sur la sortie par défaut ; à égalité, le premier scénario déclaré l'emporte.
        """
        if role not in ROLES:
            raise WlError(f"rôle inconnu {role!r} ; rôles : {', '.join(sorted(ROLES))}")
        self._scenarios.append(_Scenario(role, step_glob, output))

    def complete(
        self,
        request: LLMRequest,
        *,
        timeout_s: float,
        output_schema: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        texte = self._sortie(request)
        return ProviderResponse(text=texte, usage=self._usage(request, texte), latency_s=0.0)

    def _sortie(self, request: LLMRequest) -> str:
        for s in self._scenarios:
            if s.role == request.role and fnmatchcase(request.step, s.step_glob):
                return s.output(request) if callable(s.output) else s.output
        check_inputs(request)
        return default_output(request.role, request.inputs)

    def _usage(self, request: LLMRequest, sortie: str) -> Usage:
        """Tokens = mots. Le plus long préfixe en cache déjà vu compte en `cache_read_tokens`."""
        segments = [request.system, *(m.content for m in request.messages)]
        points: list[str] = []  # préfixes qui se terminent à un point de cache
        if request.cache_system:
            points.append(segments[0])
        for i, m in enumerate(request.messages, start=1):
            if m.cache:
                points.append("\n".join(segments[: i + 1]))
        lus = max((len(p.split()) for p in points if p in self._prefixes_vus), default=0)
        self._prefixes_vus.update(points)
        total = len("\n".join(segments).split())
        return Usage(
            input_tokens=total - lus, output_tokens=len(sortie.split()), cache_read_tokens=lus
        )
