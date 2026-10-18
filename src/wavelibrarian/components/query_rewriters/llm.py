"""QueryRewriter `llm` : rôle `rewrite`, Question reformulée pour une nouvelle recherche (FR-21)."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.core.types import ModelRefMeta, QuestionInput
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_SYSTEM = (
    "Reformule la question pour retrouver de meilleurs passages dans une base documentaire : "
    "mots-clés précis, termes synonymes, même langue. Réponds par la seule question reformulée."
)


@register("query_rewriter", "llm")
class LLMQueryRewriter:
    """Un appel `rewrite` ; l'étape de la Trace est `crag.rewrite.loopN` (`loop` de l'Architecture).
    Une reformulation vide rend la Question inchangée."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        max_tokens: int = Field(default=128, gt=0)

    def __init__(self, params: "LLMQueryRewriter.Params", ctx: Any) -> None:
        self._ctx = ctx
        self._max_tokens = params.max_tokens
        self.model_id: str = params.model or ctx.profile.defaults.generator_models[0]

    def rewrite(self, question: QuestionInput, loop: int = 1) -> str:
        requete = LLMRequest(
            model_id=self.model_id,
            role="rewrite",
            step=f"crag.rewrite.loop{loop}",
            system=_SYSTEM,
            messages=(Message(role="user", content=question.text),),
            max_tokens=self._max_tokens,
            seed=self._ctx.seed,
            inputs={"text": question.text},
        )
        texte = str(self._ctx.gateway.complete(requete).text).strip()
        return texte or question.text
