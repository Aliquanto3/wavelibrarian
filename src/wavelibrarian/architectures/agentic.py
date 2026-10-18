"""Architecture `agentic` : un agent qui cherche, lit et liste le Corpus jusqu'à répondre (FR-26).

Outils (fonctions Python en lecture seule, limitées au Corpus indexé) :
- `search(query)` : les `k` meilleurs Passages par BM25, un résultat `{id, text}` par Ancrage
  (l'`id` est l'`anchor_id` du Passage) ;
- `read(id)` : le texte de l'Ancrage ; un Ancrage inconnu renvoie un message d'erreur à l'agent,
  jamais une exception ;
- `list()` : les Documents du Corpus, `{id: doc_id, text: chemin}`.

Boucle : à chaque étape `n` (de 1 à `max_steps`), un appel `agent_step` (step `agent.step<n>`)
rend `{action, args}`. `answer` clôt la boucle. Protocole JSON, sans tool calling natif (AD-4).
Une action inconnue ou des `args` invalides rendent la sortie non conforme : la passerelle
réessaie une fois, puis `NonConformantOutput` remonte et le runner passe la Question en `error`.

Bornes, vérifiées avant chaque appel : `max_steps` ; `max_cost_per_question` sur la somme des
`cost_uncached` des appels déjà engagés (identique avec ou sans Cache de réponses, FR-4) :
borne atteinte, l'agent s'abstient sans émettre l'appel suivant. Le coût d'une première
tentative non conforme (`retry_cost_uncached`) entre dans la somme.
Fenêtre : avant chaque appel, les résultats de l'étape précédente puis l'historique les plus
anciens sont réduits (avertissement) jusqu'à tenir dans la fenêtre du modèle de l'agent ;
`ConfigError` si la question seule, ou les identifiants des résultats, n'y tiennent pas.

Réponse : les Passages retrouvés sont les extraits lus (`read`), dans l'ordre de lecture
(`retrieval_method: provided`). Une Citation de l'agent est un `anchor_id` lu ; les autres sont
retirées et comptées dans `invalid_citations`.
"""

import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from wavelibrarian.architectures._fenetre import couper
from wavelibrarian.architectures._passages import ecrire_passages, lire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.config.experiment import Amount
from wavelibrarian.core.errors import ConfigError, WlError
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import (
    ArchAnswer,
    Citation,
    ModelRefMeta,
    ParsedCorpus,
    Passage,
    QuestionInput,
)
from wavelibrarian.llm.roles import AgentStepOutput
from wavelibrarian.ports.arch_answer import passages_fournis
from wavelibrarian.ports.architecture import ArchCapabilities, ArchitectureBase
from wavelibrarian.ports.components import ComponentSpec, GenerationResult, SearchIndex
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_log = logging.getLogger(__name__)

FICHIER = "agentic.json"
_SOUS_DOSSIER = "lexical"
_SYSTEM = (
    "Tu réponds à une question en explorant un corpus de documents avec des outils. À chaque "
    "étape, choisis une action et réponds en JSON : "
    '{"action": "search|read|list|answer", "args": {...}}. '
    'Outils : search {"query": "..."} cherche des extraits ; read {"id": "<id d\'un résultat>"} '
    "lit un extrait en entier ; list {} liste les documents ; "
    'answer {"answer": "...", "citations": ["<id lu>"], "abstain": false} termine. '
    "Cite uniquement des identifiants que tu as lus ; abstiens-toi (abstain: true) si le corpus "
    "ne permet pas de répondre."
)
_MARGE = 64  # habillage du message et arrondis du tokenizer
_TEXTE_MAX = 400  # caractères d'un extrait de résultat gardés dans l'historique


class _Search(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1)


class _Read(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)


class _Vide(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    citations: list[str] = []
    abstain: bool = False


_ARGS: dict[str, type[BaseModel]] = {
    "search": _Search,
    "read": _Read,
    "list": _Vide,
    "answer": _Answer,
}


class AgentStep(AgentStepOutput):
    """`agent_step` dont les `args` sont validés selon l'action (AD-4 : sinon non conforme)."""

    @model_validator(mode="after")
    def _args_valides(self) -> "AgentStep":
        try:
            _ARGS[self.action].model_validate(self.args)
        except ValidationError as exc:
            raise ValueError(f"args invalides pour `{self.action}` : {exc}") from exc
        return self


def _resultat(identifiant: str, texte: str) -> dict[str, str]:
    return {"id": identifiant, "text": texte}


@register("architecture", "agentic")
class Agentic(ArchitectureBase):
    """Agent à outils `search`, `read`, `list` sous bornes de pas et de coût."""

    name = "agentic"
    capabilities = ArchCapabilities(incremental_update=False, retrieval_method="provided")
    query_params: ClassVar[frozenset[str]] = frozenset(
        {"k", "max_steps", "max_cost_per_question", "agent_model", "agent_max_tokens"}
    )

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        chunker: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="fixed_tokens"))
        lexical_index: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="bm25"))
        context_builder: ComponentSpec = Field(
            default_factory=lambda: ComponentSpec(name="labeled")
        )
        generator: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="llm"))
        k: int = Field(default=5, gt=0)
        max_steps: int = Field(default=8, gt=0)
        max_cost_per_question: Amount = Field(
            default_factory=lambda: Amount(amount=Decimal("0.05"), currency="USD")
        )
        agent_model: Annotated[
            str | None, ModelRefMeta("generator_models[0]", answer_producer=True)
        ] = None
        agent_max_tokens: int = Field(default=512, gt=0)

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.chunker = ctx.build("chunker", params.chunker)
        self.retriever = ctx.build("retriever", ComponentSpec(name="lexical"))
        self.context_builder = ctx.build("context_builder", params.context_builder)
        self.generator = ctx.build("generator", params.generator)
        defaut = ctx.profile.defaults.generator_models[0]
        self._modele: str = params.agent_model or defaut
        self._index: SearchIndex | None = None
        self._ancrages: dict[str, dict[str, str]] = {}
        self._documents: list[dict[str, str]] = []
        self._sans_fenetre = False

    # -- indexation -----------------------------------------------------------------------------

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        passages = [p for doc in corpus.documents for p in self.chunker.chunk(doc)]
        lexical = self.ctx.build("lexical_index", self.params.lexical_index)  # type: ignore[attr-defined]
        lexical.add(passages)
        ecrire_passages(directory, passages)
        lexical.save(directory / _SOUS_DOSSIER)
        ancrages = {
            a: {"doc_id": d.doc_id, "text": corpus.anchor_text(a)}
            for d in corpus.documents
            for a in d.anchors
        }
        documents = [{"doc_id": d.doc_id, "source_path": d.source_path} for d in corpus.documents]
        texte = json.dumps(
            {"anchors": ancrages, "documents": documents}, ensure_ascii=False, indent=1
        )
        (directory / FICHIER).write_bytes((texte + "\n").encode("utf-8"))

    def load(self, directory: Path) -> None:
        lexical = self.ctx.build("lexical_index", self.params.lexical_index)  # type: ignore[attr-defined]
        lexical.load(directory / _SOUS_DOSSIER)
        passages = {p.passage_id: p for p in lire_passages(directory)}
        self._index = SearchIndex(passages=passages, lexical=lexical)
        try:
            brut = json.loads((directory / FICHIER).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WlError(f"index illisible : {directory / FICHIER} absent ou illisible") from exc
        try:
            self._ancrages = {
                a: {"doc_id": str(v["doc_id"]), "text": str(v["text"])}
                for a, v in brut["anchors"].items()
            }
            self._documents = [
                {"doc_id": str(d["doc_id"]), "source_path": str(d["source_path"])}
                for d in brut["documents"]
            ]
        except (KeyError, TypeError, AttributeError) as exc:
            raise WlError(f"index illisible : {directory / FICHIER} malformé") from exc

    # -- outils (lecture seule, limités au Corpus indexé) ---------------------------------------

    def _outil_search(self, query: str) -> list[dict[str, str]]:
        assert self._index is not None
        k: int = self.params.k  # type: ignore[attr-defined]
        vus: set[str] = set()
        resultats: list[dict[str, str]] = []
        for scored in self.retriever.retrieve(query, k, self._index):  # type: ignore[attr-defined]
            ancrage = scored.passage.anchor_ids[0]
            if ancrage not in vus:
                vus.add(ancrage)
                resultats.append(_resultat(ancrage, scored.passage.text))
        return resultats

    def _outil_read(self, identifiant: str) -> list[dict[str, str]]:
        ancrage = self._ancrages.get(identifiant)
        if ancrage is None:
            return [_resultat(identifiant, f"Erreur : Ancrage inconnu `{identifiant}`.")]
        return [_resultat(identifiant, ancrage["text"])]

    def _outil_list(self) -> list[dict[str, str]]:
        return [_resultat(d["doc_id"], d["source_path"]) for d in self._documents]

    # -- fenêtre --------------------------------------------------------------------------------

    def _fenetre(self) -> int | None:
        fenetre: int | None = self.ctx.catalog.get(self._modele).context_window  # type: ignore[attr-defined]
        if fenetre is None and not self._sans_fenetre:
            self._sans_fenetre = True
            _log.warning(
                "agentic : `context_window` absent du Catalogue pour `%s`, aucun contrôle de "
                "fenêtre",
                self._modele,
            )
        return fenetre

    def _contenu(
        self,
        question: QuestionInput,
        etape: int,
        historique: list[str],
        resultats: list[dict[str, str]],
    ) -> str:
        borne: int = self.params.max_steps  # type: ignore[attr-defined]
        lignes = "\n".join(historique) if historique else "(aucune)"
        derniers = json.dumps(resultats, ensure_ascii=False)
        consigne = "\nDernière étape : réponds avec l'action answer." if etape >= borne else ""
        return (
            f"Question : {question.text}\nÉtape : {etape}/{borne}\nHistorique :\n{lignes}\n"
            f"Résultats de l'étape précédente : {derniers}{consigne}"
        )

    def _tenir(
        self,
        question: QuestionInput,
        etape: int,
        historique: list[str],
        resultats: list[dict[str, str]],
    ) -> tuple[list[str], list[dict[str, str]]]:
        """Historique et résultats ramenés à ce que la fenêtre laisse (avertissement)."""
        fenetre = self._fenetre()
        if fenetre is None:
            return historique, resultats
        tokenizer = self.ctx.tokenizer_for(self._modele)  # type: ignore[attr-defined]
        p: Any = self.params
        # le schéma compte : un fournisseur `schema_in_prompt` l'ajoute au prompt
        schema = json.dumps(AgentStep.model_json_schema(), ensure_ascii=False, sort_keys=True)
        libre = (
            fenetre
            - tokenizer.count(_SYSTEM)
            - tokenizer.count(schema)
            - p.agent_max_tokens
            - _MARGE
        )

        def taille(h: list[str], r: list[dict[str, str]]) -> int:
            return int(tokenizer.count(self._contenu(question, etape, h, r)))

        if libre <= taille([], []):
            raise ConfigError(
                "agent_max_tokens",
                f"`agentic` : la question, le system et la sortie réservée ne tiennent pas dans "
                f"la fenêtre de {fenetre} tokens de `{self._modele}`",
            )
        if taille(historique, resultats) <= libre:
            return historique, resultats
        _log.warning(
            "agentic : contexte de l'étape %d réduit pour tenir dans la fenêtre de %d tokens",
            etape,
            fenetre,
        )
        resultats = [dict(r) for r in resultats]
        while taille(historique, resultats) > libre and any(r["text"] for r in resultats):
            for r in resultats:
                r["text"] = couper(r["text"], tokenizer, tokenizer.count(r["text"]) // 2)
        historique = list(historique)
        while taille(historique, resultats) > libre and historique:
            historique.pop(0)
        if taille(historique, resultats) > libre:
            raise ConfigError(
                "agent_max_tokens",
                f"`agentic` : les identifiants des {len(resultats)} résultat(s) de l'étape "
                f"{etape - 1} ne tiennent pas dans la fenêtre de {fenetre} tokens de "
                f"`{self._modele}`",
            )
        return historique, resultats

    # -- boucle ---------------------------------------------------------------------------------

    def _appeler(
        self,
        question: QuestionInput,
        etape: int,
        historique: list[str],
        resultats: list[dict[str, str]],
    ) -> tuple[AgentStep, Decimal, str]:
        p: Any = self.params
        requete = LLMRequest(
            model_id=self._modele,
            role="agent_step",
            step=f"agent.step{etape}",
            system=_SYSTEM,
            messages=(
                Message(role="user", content=self._contenu(question, etape, historique, resultats)),
            ),
            max_tokens=p.agent_max_tokens,
            seed=self.ctx.seed,  # type: ignore[attr-defined]
            inputs={"question": question.text, "step": etape, "last_results": resultats},
        )
        sortie, res = self.ctx.gateway.complete_structured(requete, AgentStep)  # type: ignore[attr-defined]
        # la tentative non conforme réessayée par la passerelle a aussi été payée
        return sortie, res.cost_uncached + res.retry_cost_uncached, res.currency

    @staticmethod
    def _passage_lu(identifiant: str, doc_id: str, texte: str) -> Passage:
        return Passage(
            passage_id=sha16(doc_id, "agentic", identifiant),
            doc_id=doc_id,
            text=texte,
            anchor_ids=(identifiant,),
        )

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if self._index is None:
            raise RuntimeError("`load` doit précéder `answer`")
        p: Any = self.params
        budget: Amount = p.max_cost_per_question
        engage = Decimal(0)
        historique: list[str] = []
        resultats: list[dict[str, str]] = []
        lus: dict[str, Passage] = {}
        lecture: str | None = None  # Ancrage lu à l'étape précédente
        final: _Answer | None = None
        for etape in range(1, p.max_steps + 1):
            if engage >= budget.amount:  # borne vérifiée avant chaque appel
                _log.warning(
                    "agentic : budget de %s %s atteint à l'étape %d (%s engagés), abstention",
                    budget.amount,
                    budget.currency,
                    etape,
                    engage,
                )
                break
            historique, resultats = self._tenir(question, etape, historique, resultats)
            if lecture is not None and lecture in lus and resultats:
                lus[lecture] = lus[lecture].model_copy(update={"text": resultats[0]["text"]})
            sortie, cout, devise = self._appeler(question, etape, historique, resultats)
            if devise != budget.currency:
                raise WlError(
                    f"`agentic` : coût en {devise}, borne `max_cost_per_question` en "
                    f"{budget.currency}"
                )
            engage += cout
            args = _ARGS[sortie.action].model_validate(sortie.args)
            lecture = None
            if isinstance(args, _Answer):
                final = args
                break
            if isinstance(args, _Search):
                resultats = self._outil_search(args.query)
                resume = f"{len(resultats)} résultat(s)"
            elif isinstance(args, _Read):
                resultats = self._outil_read(args.id)
                connu = args.id in self._ancrages
                if connu and args.id not in lus:
                    doc_id = self._ancrages[args.id]["doc_id"]
                    lus[args.id] = self._passage_lu(args.id, doc_id, resultats[0]["text"])
                if connu:
                    lecture = args.id
                resume = "lu" if connu else "Ancrage inconnu"
            else:
                resultats = self._outil_list()
                resume = f"{len(resultats)} document(s)"
            historique.append(
                f"étape {etape} : {sortie.action} "
                f"{json.dumps(sortie.args, ensure_ascii=False)[:_TEXTE_MAX]} -> {resume}"
            )
        passages = list(lus.values())
        tokenizer = self.ctx.tokenizer_for(self.generator.model_id)  # type: ignore[attr-defined]
        contexte = self.context_builder.build(passages)
        if final is None:
            vide = GenerationResult(text="", abstained=True, citations=(), invalid_citations=0)
            return build_arch_answer(
                contexte, vide, passages_fournis(passages), "provided", tokenizer=tokenizer
            )
        cites = dict.fromkeys(c for c in final.citations if c in lus)
        resultat = GenerationResult(
            text=final.answer,
            abstained=final.abstain,
            citations=tuple(Citation(anchor_id=a) for a in cites),
            invalid_citations=len(set(final.citations) - set(cites)),
        )
        return build_arch_answer(
            contexte, resultat, passages_fournis(passages), "provided", tokenizer=tokenizer
        )
