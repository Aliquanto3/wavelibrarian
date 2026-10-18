"""Generator `llm` : rôle `generate`, étiquettes converties en Citations (AD-4, AD-6, AD-7)."""

import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import Citation, ModelRefMeta, QuestionInput
from wavelibrarian.llm.roles import GenerateOutput
from wavelibrarian.ports.components import Context, GenerationResult
from wavelibrarian.ports.gateway import LLMRequest, LLMResult, Message
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
        # Contexte long : le Contexte entre dans le system, mis en cache de prompt (FR-16).
        cache_system: bool = False

    def __init__(self, params: "LLMGenerator.Params", ctx: Any) -> None:
        self._ctx = ctx
        self._max_tokens = params.max_tokens
        self.max_tokens: int = params.max_tokens  # lu par `long_context.check` (fenêtre)
        self._cache_system = params.cache_system
        self.model_id: str = params.model or ctx.profile.defaults.generator_models[0]

    @staticmethod
    def _contexte_texte(context: Context) -> str:
        return context.text if context.blocks else "(aucun passage)"

    @staticmethod
    def _system_avec_contexte(contexte: str) -> str:
        return f"{_SYSTEM}\n\nContexte :\n{contexte}"

    def preload(self, context: Context) -> LLMResult:
        """Appel de préchargement du cache de prompt (CAG) : même system que `generate`.

        Texte libre (`complete`), sans schéma : la sortie est ignorée et ne peut pas être
        « non conforme ». Exige `cache_system: true`.
        """
        if not self._cache_system:
            raise WlError("`preload` exige `cache_system: true`")
        requete = LLMRequest(
            model_id=self.model_id,
            role="generate",
            step="cag.preload",
            system=self._system_avec_contexte(self._contexte_texte(context)),
            cache_system=True,
            messages=(Message(role="user", content="Préchargement du cache : réponds « ok »."),),
            max_tokens=16,
            seed=self._ctx.seed,
            inputs={"question": "", "blocks": {}},
        )
        return self._ctx.gateway.complete(requete)

    def generate(self, question: QuestionInput, context: Context) -> GenerationResult:
        blocs = {
            etiquette: _PREFIXE.sub("", bloc, count=1)
            for etiquette, bloc in zip(context.labels, context.blocks, strict=True)
        }
        contexte = self._contexte_texte(context)
        messages = [Message(role=t.role, content=t.text) for t in question.history]
        if self._cache_system:
            systeme = f"{_SYSTEM}\n\nContexte :\n{contexte}"
            messages.append(Message(role="user", content=f"Question : {question.text}"))
        else:
            systeme = _SYSTEM
            messages.append(
                Message(
                    role="user", content=f"Contexte :\n{contexte}\n\nQuestion : {question.text}"
                )
            )
        requete = LLMRequest(
            model_id=self.model_id,
            role="generate",
            step="generate",
            system=systeme,
            cache_system=self._cache_system,
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
