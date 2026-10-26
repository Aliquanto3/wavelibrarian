"""Passerelle de modèles (contracts.md §2.2). Aucune entrée-sortie."""

from decimal import Decimal
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel

from wavelibrarian.core.types import Usage

T = TypeVar("T", bound=BaseModel)

LLMRole = Literal[
    "generate",
    "judge",
    "rewrite",
    "hyde",
    "summarize",
    "extract_entities",
    "select_nodes",
    "agent_step",
    "grade_relevance",
    "wiki_compile",
    "wiki_fidelity",
    "community_report",
    "global_map",
    "closed_book",
    "question_gen",
]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    cache: bool = False  # point de cache de prompt après ce message (CAG)


class LLMRequest(BaseModel):
    model_id: str
    role: LLMRole
    step: str  # nom d'étape de la Trace, ex. "generate", "crag.grade.loop1"
    system: str
    messages: tuple[Message, ...]
    max_tokens: int
    temperature: float | None = 0.0  # None : non envoyée (modèle qui la refuse, AD-20)
    seed: int | None = None
    # Ollama : `think` envoyé tel quel, `None` = champ omis. La passerelle y pose la valeur du
    # Catalogue (`ModelEntry.think`) ; les autres providers l'ignorent.
    think: bool | None = False
    # Anthropic : `False` envoie l'outil de sortie en `tool_choice: auto` (posé par la passerelle
    # depuis `ModelEntry.forced_tool_choice`) ; les autres providers l'ignorent.
    forced_tool: bool = True
    cache_system: bool = False  # met le system en cache de prompt
    pass_id: int = 0  # entre dans la clé du Cache de réponses (FR-34)
    timeout_s: float | None = None
    inputs: dict[str, Any] = {}  # données structurées du rôle ; lues par le Faux LLM seul


class LLMResult(BaseModel):
    text: str
    usage: Usage
    cost: Decimal  # 0 si servi depuis le Cache de réponses
    cost_uncached: Decimal
    currency: str
    latency_s: float
    from_cache: bool
    # coût hors cache de la tentative non conforme réessayée par `complete_structured`
    # (tracée à part ; 0 sans nouvel essai), à ajouter à `cost_uncached` pour une borne
    retry_cost_uncached: Decimal = Decimal(0)


class ModelGateway(Protocol):
    def complete(self, request: LLMRequest, *, use_cache: bool = True) -> LLMResult: ...

    def complete_structured(
        self, request: LLMRequest, schema: type[T], *, use_cache: bool = True
    ) -> tuple[T, LLMResult]:
        """Lève `NonConformantOutput` après un nouvel essai si la sortie ne valide pas le schéma ;
        `use_cache=False` : ne lit pas le Cache de réponses."""
        ...
