"""Architecture `hyde` : recherche dense avec le vecteur d'une réponse hypothétique (FR-20)."""

import logging
from typing import Annotated, Any, ClassVar

import numpy as np
from pydantic import Field

from wavelibrarian.architectures.naive_rag import NaiveRag
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import ArchAnswer, ModelRefMeta, QuestionInput
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_log = logging.getLogger(__name__)

_SYSTEM = (
    "Écris un court passage de documentation qui répondrait à la question, dans la langue de la "
    "question, comme si tu le citais d'un document. Ne dis pas que tu n'es pas sûr : le texte ne "
    "sert qu'à retrouver de vrais passages."
)


def _unitaire(v: Any) -> Any:
    norme = float(np.linalg.norm(v))
    return v / norme if norme > 0.0 else v


@register("architecture", "hyde")
class Hyde(NaiveRag):
    """Même index que `naive_rag` ; seule la requête change : le rôle `hyde` écrit une réponse
    hypothétique, son embedding (`embed_queries`) interroge le store. Le texte hypothétique ne
    quitte jamais `answer` : il n'entre ni dans le Contexte ni dans le prompt de `generate`."""

    name = "hyde"
    query_params: ClassVar[frozenset[str]] = frozenset(
        {"k", "mix_question", "hyde_model", "hyde_max_tokens"}
    )

    class Params(NaiveRag.Params):
        # Sans effet sur l'index : change de modèle ou de mélange sans réindexer.
        mix_question: bool = False
        hyde_model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        hyde_max_tokens: int = Field(default=256, gt=0)

    def __init__(self, params: Any, ctx: Any) -> None:
        if params.retriever.name != "dense":
            # `lexical` ignorerait le vecteur ; `hybrid` exige un index lexical que l'index
            # dense de `naive_rag` ne construit pas (échec à chaque Question, après l'appel hyde).
            raise ConfigError(
                "retriever",
                f"`hyde` cherche dans l'index dense de `naive_rag` : retriever `dense` seul, "
                f"pas `{params.retriever.name}`",
            )
        super().__init__(params, ctx)
        self._hyde_model: str = params.hyde_model or ctx.profile.defaults.generator_models[0]

    def _hypothese(self, question: QuestionInput) -> str:
        requete = LLMRequest(
            model_id=self._hyde_model,
            role="hyde",
            step="hyde",
            system=_SYSTEM,
            messages=(Message(role="user", content=question.text),),
            max_tokens=self.params.hyde_max_tokens,  # type: ignore[attr-defined]
            seed=self.ctx.seed,  # type: ignore[attr-defined]
            inputs={"text": question.text},
        )
        return str(self.ctx.gateway.complete(requete).text)  # type: ignore[attr-defined]

    def _vecteur_de_recherche(self, question: QuestionInput, hypothese: str) -> Any:
        """Vecteur de la réponse hypothétique ; avec `mix_question`, moyenne renormalisée avec
        celui de la Question. Une réponse vide se rabat sur la Question."""
        texte = hypothese.strip()
        if not texte:
            _log.warning(
                "hyde : réponse hypothétique vide pour %s, recherche par la Question",
                question.question_id,
            )
            return self.embedder.embed_queries([question.text])[0]
        if not self.params.mix_question:  # type: ignore[attr-defined]
            return self.embedder.embed_queries([texte])[0]
        hyp, quest = self.embedder.embed_queries([texte, question.text])
        moyenne = _unitaire((hyp + quest) / 2.0)
        return _unitaire(hyp) if not np.any(moyenne) else moyenne.astype(np.float32)

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if self._index is None:
            raise RuntimeError("`load` doit précéder `answer`")
        hypothese = self._hypothese(question)
        vecteur = self._vecteur_de_recherche(question, hypothese)
        k: int = self.params.k  # type: ignore[attr-defined]
        classes = self.retriever.retrieve(  # type: ignore[attr-defined]
            question.text, k, self._index, query_vector=vecteur
        )
        contexte = self.context_builder.build([s.passage for s in classes])
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(
            contexte,
            resultat,
            classes,
            "ranked",
            tokenizer=self.ctx.tokenizer_for(self.generator.model_id),  # type: ignore[attr-defined]
        )
