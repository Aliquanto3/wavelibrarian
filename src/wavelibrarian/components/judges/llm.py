"""Juge LLM : un appel au rôle `judge` note tous les Critères (FR-36, AD-4, contracts.md §2)."""

import json
from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, create_model

from wavelibrarian.core.types import Criterion, ModelRefMeta
from wavelibrarian.llm.roles import CriterionVerdict
from wavelibrarian.ports.components import JudgeInput
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_SYSTEM = (
    "Tu es un juge impartial. Pour chaque critère demandé, réponds par yes ou no et une "
    "justification courte. correctness : la réponse est exacte au regard de la référence. "
    "completeness : elle couvre tous les points de la référence. faithfulness : tout ce qu'elle "
    "affirme se trouve dans le contexte fourni au générateur. Réponds en JSON : "
    '{"verdicts": {"<critère>": {"verdict": "yes"|"no", "justification": "..."}}}.'
)
_MAX_TOKENS_PAR_CRITERE = 120


def _schema(criteres: Sequence[str]) -> type[BaseModel]:
    """Schéma de sortie qui exige un verdict pour chaque Critère demandé (nouvel essai sinon)."""
    champs: dict[str, Any] = {str(c): (CriterionVerdict, ...) for c in criteres}
    verdicts = create_model("Verdicts", __config__=ConfigDict(extra="ignore"), **champs)
    return create_model("JudgeCriteriaOutput", verdicts=(verdicts, ...))


@register("judge", "llm")
class LLMJudge:
    """Juge : un appel `judge` par (item, Critères, pass_id) ; `pass_id` sort du Cache (FR-34)."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        model: Annotated[str | None, ModelRefMeta("judge_pool[0]")] = None
        # False : les passes `pass_id` >= 1 ne lisent pas le Cache (calibration, story 5.2).
        cache_later_passes: bool = True

    def __init__(self, params: "LLMJudge.Params", ctx: Any) -> None:
        self._ctx = ctx
        self.model_id: str = params.model or ctx.profile.defaults.judge_pool[0]
        self._cache_later_passes = params.cache_later_passes

    def judge(
        self, item: JudgeInput, criteria: Sequence[Criterion], pass_id: int
    ) -> dict[Criterion, tuple[bool, str]]:
        """Verdict booléen et justification par Critère ; `NonConformantOutput` après un essai."""
        criteres = list(dict.fromkeys(criteria))
        corps: dict[str, Any] = {
            "question": item.question,
            "reference_answer": item.reference_answer,
            "reference_texts": list(item.reference_texts),
            "answer": item.answer_text,
            "criteria": criteres,
        }
        inputs: dict[str, Any] = dict(corps)
        if "faithfulness" in criteres:  # AD-6 : les textes réellement fournis au Generator
            corps["context_texts"] = list(item.context_texts)
            inputs["context_texts"] = list(item.context_texts)
        requete = LLMRequest(
            model_id=self.model_id,
            role="judge",
            step="judge",
            system=_SYSTEM,
            messages=(Message(role="user", content=json.dumps(corps, ensure_ascii=False)),),
            max_tokens=_MAX_TOKENS_PAR_CRITERE * max(len(criteres), 1) + 60,
            seed=self._ctx.seed,
            pass_id=pass_id,
            inputs=inputs,
        )
        sortie, _ = self._ctx.gateway.complete_structured(
            requete, _schema(criteres), use_cache=pass_id == 0 or self._cache_later_passes
        )
        verdicts: Any = getattr(sortie, "verdicts")  # noqa: B009
        resultat: dict[Criterion, tuple[bool, str]] = {}
        for c in criteres:
            v: CriterionVerdict = getattr(verdicts, c)
            resultat[c] = (v.verdict == "yes", v.justification)
        return resultat
