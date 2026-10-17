"""Generator `llm` : rôle `generate`, étiquettes converties en Citations (AD-4, AD-6, AD-7)."""

import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.core.types import Citation, ModelRefMeta, QuestionInput
from wavelibrarian.llm.roles import GenerateOutput
from wavelibrarian.ports.components import Context, GenerationResult
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_SYSTEM = (
    "Réponds à la question uniquement à partir des blocs de contexte fournis, dans la langue de "
    "la question. Chaque bloc est précédé d'une étiquette [S1], [S2]… Cite les étiquettes des "
    "blocs qui fondent ta réponse. Si le contexte ne permet pas de répondre, ne devine pas : "
    "abstiens-toi (abstain: true). Réponds en JSON : "
    '{"answer": "...", "citations": ["S1"], "abstain": false}.'
)
_PREFIXE = re.compile(r"^\[S\d+\] \(.*?\) ", re.DOTALL)
_ETIQUETTE = re.compile(r"^(?:\[(S[1-9]\d*)\]|(S[1-9]\d*))$")  # `[S1]` ou `S1`, rien d'autre


@register("generator", "llm")
class LLMGenerator:
    """Un appel `generate` par Question ; les étiquettes citées deviennent des Citations."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        model: Annotated[str | None, ModelRefMeta("generator_models[0]", answer_producer=True)] = (
            None
        )
        max_tokens: int = Field(default=1024, gt=0)

    def __init__(self, params: "LLMGenerator.Params", ctx: Any) -> None:
        self._ctx = ctx
        self._max_tokens = params.max_tokens
        self.model_id: str = params.model or ctx.profile.defaults.generator_models[0]

    def generate(self, question: QuestionInput, context: Context) -> GenerationResult:
        blocs = {
            etiquette: _PREFIXE.sub("", bloc, count=1)
            for etiquette, bloc in zip(context.labels, context.blocks, strict=True)
        }
        contexte = context.text if context.blocks else "(aucun passage)"
        messages = [Message(role=t.role, content=t.text) for t in question.history]
        messages.append(
            Message(role="user", content=f"Contexte :\n{contexte}\n\nQuestion : {question.text}")
        )
        requete = LLMRequest(
            model_id=self.model_id,
            role="generate",
            step="generate",
            system=_SYSTEM,
            messages=tuple(messages),
            max_tokens=self._max_tokens,
            seed=self._ctx.seed,
            inputs={"question": question.text, "blocks": blocs},
        )
        sortie, _ = self._ctx.gateway.complete_structured(requete, GenerateOutput)
        citations: dict[str, None] = {}
        invalides: set[str] = set()
        for brut in sortie.citations:
            m = _ETIQUETTE.match(brut.strip())
            etiquette = (m.group(1) or m.group(2)) if m else brut.strip()
            if etiquette in context.labels:
                for anchor_id in context.labels[etiquette]:
                    citations[anchor_id] = None
            else:
                invalides.add(etiquette)
        return GenerationResult(
            text=sortie.answer,
            abstained=sortie.abstain,
            citations=tuple(Citation(anchor_id=a) for a in citations),
            invalid_citations=len(invalides),
        )
