"""Architecture `corrective_rag` : recherche dense, notation des Passages, reformulation (FR-21)."""

from typing import Any, ClassVar

from pydantic import Field

from wavelibrarian.architectures.naive_rag import NaiveRag
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import ArchAnswer, QuestionInput, ScoredPassage
from wavelibrarian.ports.components import ComponentSpec, GenerationResult
from wavelibrarian.registry import register


@register("architecture", "corrective_rag")
class CorrectiveRag(NaiveRag):
    """Même index que `naive_rag`. Le Decider note les Passages retrouvés ; seuls ceux notés au
    seuil ou au-dessus entrent dans le Contexte. Sinon la Question est reformulée et la recherche
    relancée, au plus `max_loops` fois, puis l'Architecture s'abstient sans appel `generate`."""

    name = "corrective_rag"
    query_params: ClassVar[frozenset[str]] = frozenset(
        {"k", "threshold", "max_loops", "decider", "query_rewriter"}
    )

    class Params(NaiveRag.Params):
        decider: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="llm"))
        query_rewriter: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="llm"))
        threshold: float = Field(default=0.5, ge=0.0, le=1.0)
        max_loops: int = Field(default=2, ge=0)

    def __init__(self, params: Any, ctx: Any) -> None:
        if params.retriever.name != "dense":
            # `lexical` et `hybrid` exigent un index lexical que l'index de `naive_rag` n'a pas.
            raise ConfigError(
                "retriever",
                f"`corrective_rag` cherche dans l'index dense de `naive_rag` : retriever `dense` "
                f"seul, pas `{params.retriever.name}`",
            )
        super().__init__(params, ctx)
        self.decider = ctx.build("decider", params.decider)
        self.query_rewriter = ctx.build("query_rewriter", params.query_rewriter)

    def _chercher_et_noter(
        self, question: QuestionInput, requete: QuestionInput, boucle: int
    ) -> tuple[list[ScoredPassage], list[ScoredPassage]]:
        """Recherche par `requete`, notation au regard de la Question d'origine ; renvoie la
        liste classée et le sous-ensemble noté au seuil ou au-dessus (ordre conservé)."""
        assert self._index is not None
        k: int = self.params.k  # type: ignore[attr-defined]
        classes = self.retriever.retrieve(requete.text, k, self._index)  # type: ignore[attr-defined]
        scores = self.decider.grade(question, [s.passage for s in classes], loop=boucle)
        seuil: float = self.params.threshold  # type: ignore[attr-defined]
        gardes = [s for s, note in zip(classes, scores, strict=True) if note >= seuil]
        return classes, gardes

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if self._index is None:
            raise RuntimeError("`load` doit précéder `answer`")
        max_loops: int = self.params.max_loops  # type: ignore[attr-defined]
        requete = question
        classes, gardes = self._chercher_et_noter(question, requete, 0)
        boucle = 0
        while not gardes and boucle < max_loops:  # borne vérifiée avant chaque reformulation
            boucle += 1
            requete = question.model_copy(
                update={"text": self.query_rewriter.rewrite(requete, loop=boucle)}
            )
            classes, gardes = self._chercher_et_noter(question, requete, boucle)
        tokenizer = self.ctx.tokenizer_for(self.generator.model_id)  # type: ignore[attr-defined]
        contexte = self.context_builder.build([s.passage for s in gardes])
        if not gardes:
            vide = GenerationResult(text="", abstained=True, citations=(), invalid_citations=0)
            return build_arch_answer(contexte, vide, classes, "ranked", tokenizer=tokenizer)
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(contexte, resultat, classes, "ranked", tokenizer=tokenizer)
