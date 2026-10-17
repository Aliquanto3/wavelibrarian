"""Les 15 rôles LLM : clés obligatoires d'`inputs` et schéma de sortie (contracts.md §3, AD-4).

Ajouter un rôle modifie ce module et `llm/providers/fake.py` dans la même story.
"""

from dataclasses import dataclass
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavelibrarian.core.errors import WlError
from wavelibrarian.ports.gateway import LLMRequest, LLMRole


class _Sortie(BaseModel):
    model_config = ConfigDict(frozen=True)


class GenerateOutput(_Sortie):
    answer: str
    citations: list[str]
    abstain: bool


class CriterionVerdict(_Sortie):
    verdict: Literal["yes", "no"]
    justification: str


class JudgeOutput(_Sortie):
    verdicts: dict[str, CriterionVerdict]


class Entity(_Sortie):
    name: str
    kind: str
    description: str


class Relation(_Sortie):
    source: str
    target: str
    description: str
    weight: float


class ExtractEntitiesOutput(_Sortie):
    entities: list[Entity]
    relations: list[Relation]


class SelectNodesOutput(_Sortie):
    node_ids: list[str]
    done: bool


class AgentStepOutput(_Sortie):
    action: Literal["search", "read", "list", "answer"]
    args: dict[str, Any]


class GradeRelevanceOutput(_Sortie):
    scores: list[float]

    @model_validator(mode="after")
    def _dans_unite(self) -> "GradeRelevanceOutput":
        if any(not 0.0 <= s <= 1.0 for s in self.scores):
            raise ValueError("chaque score doit être dans [0, 1]")
        return self


class WikiPage(_Sortie):
    title: str
    body: str
    anchor_ids: list[str]


class WikiCompileOutput(_Sortie):
    pages: list[WikiPage]


class WikiFidelityOutput(_Sortie):
    claims: int = Field(ge=0)
    supported: int = Field(ge=0)

    @model_validator(mode="after")
    def _coherent(self) -> "WikiFidelityOutput":
        if self.supported > self.claims:
            raise ValueError("`supported` ne peut dépasser `claims`")
        return self


class GeneratedQuestion(_Sortie):
    type: str
    text: str
    reference_answer: str
    answer_form: Literal["short", "free"]
    anchor_ids: list[str]


class QuestionGenOutput(_Sortie):
    questions: list[GeneratedQuestion]


@dataclass(frozen=True)
class RoleSpec:
    """`output` vaut `None` pour un rôle en texte libre (`complete`)."""

    role: LLMRole
    required_inputs: tuple[str, ...]
    output: type[BaseModel] | None


ROLES: dict[LLMRole, RoleSpec] = {
    s.role: s
    for s in (
        RoleSpec("generate", ("question", "blocks"), GenerateOutput),
        RoleSpec("judge", ("question", "reference_answer", "answer", "criteria"), JudgeOutput),
        RoleSpec("rewrite", ("text",), None),
        RoleSpec("hyde", ("text",), None),
        RoleSpec("summarize", ("text",), None),
        RoleSpec("extract_entities", ("text",), ExtractEntitiesOutput),
        RoleSpec("select_nodes", ("question", "nodes", "max"), SelectNodesOutput),
        RoleSpec("agent_step", ("question", "step", "last_results"), AgentStepOutput),
        RoleSpec("grade_relevance", ("question", "passages"), GradeRelevanceOutput),
        RoleSpec("wiki_compile", ("documents",), WikiCompileOutput),
        RoleSpec("wiki_fidelity", ("page", "sources"), WikiFidelityOutput),
        RoleSpec("community_report", ("text",), None),
        RoleSpec("global_map", ("text",), None),
        RoleSpec("closed_book", ("text",), None),
        RoleSpec("question_gen", ("anchors", "types"), QuestionGenOutput),
    )
}

assert set(ROLES) == set(get_args(LLMRole)), "ROLES doit couvrir exactement `LLMRole`"


def check_inputs(request: LLMRequest) -> None:
    """Refuse (`WlError`) une requête sans l'une des clés obligatoires d'`inputs` de son rôle."""
    manquantes = [k for k in ROLES[request.role].required_inputs if k not in request.inputs]
    if manquantes:
        raise WlError(
            f"requête {request.step!r} (rôle {request.role}) : "
            f"clés d'`inputs` manquantes : {', '.join(manquantes)}"
        )
