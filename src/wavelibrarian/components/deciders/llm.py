"""Decider `llm` : rôle `grade_relevance`, un score dans [0, 1] par Passage (FR-21, AD-4)."""

from collections.abc import Sequence
from functools import cache
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, create_model

from wavelibrarian.core.types import ModelRefMeta, Passage, QuestionInput
from wavelibrarian.llm.roles import GradeRelevanceOutput
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_SYSTEM = (
    "Pour chaque passage numéroté, donne un score de pertinence entre 0 (sans rapport) et 1 "
    "(répond directement) au regard de la question. Réponds en JSON, un score par passage, dans "
    "l'ordre reçu : "
    '{"scores": [0.0, 0.0]}.'
)


@cache
def _schema_pour(n: int) -> type[GradeRelevanceOutput]:
    """Schéma du rôle borné à `n` scores : la passerelle refuse un autre nombre comme toute
    sortie non conforme (second essai sans cache, aucune mise en cache). `minItems`/`maxItems`
    partent aussi au provider (outil imposé, `format` d'Ollama)."""
    return create_model(
        "GradeRelevanceOutput",
        __base__=GradeRelevanceOutput,
        scores=(list[float], Field(min_length=n, max_length=n)),
    )


@register("decider", "llm")
class LLMDecider:
    """Un appel `grade_relevance` par lot de Passages. L'étape de la Trace est `crag.grade.loopN`
    (`loop` passé par l'Architecture) ; le nombre de scores doit égaler celui des Passages."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        max_tokens: int = Field(default=256, gt=0)

    def __init__(self, params: "LLMDecider.Params", ctx: Any) -> None:
        self._ctx = ctx
        self._max_tokens = params.max_tokens
        self.model_id: str | None = params.model or ctx.profile.defaults.generator_models[0]

    def grade(
        self, question: QuestionInput, passages: Sequence[Passage], loop: int = 0
    ) -> list[float]:
        if not passages:
            return []
        textes = [p.text for p in passages]
        numerotes = "\n\n".join(f"[{i}] {t}" for i, t in enumerate(textes, start=1))
        requete = LLMRequest(
            model_id=self.model_id or "",
            role="grade_relevance",
            step=f"crag.grade.loop{loop}",
            system=_SYSTEM,
            messages=(Message(role="user", content=f"Question : {question.text}\n\n{numerotes}"),),
            max_tokens=self._max_tokens,
            seed=self._ctx.seed,
            inputs={"question": question.text, "passages": textes},
        )
        schema = _schema_pour(len(textes))
        sortie, _ = self._ctx.gateway.complete_structured(requete, schema)
        return [float(s) for s in sortie.scores]
