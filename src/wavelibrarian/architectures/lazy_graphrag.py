"""Architecture `lazy_graphrag` : GraphRAG sans LLM à l'indexation, le travail est reporté à la
requête (FR-27), d'après l'idée de LazyGraphRAG (Microsoft Research, 2024), en version simplifiée.

Indexation (aucun appel LLM, aucun embedding) : découpage en Passages (feuilles), concepts de chaque
Passage par l'heuristique hors ligne `corpus/entities.py` (séquences capitalisées hors début de
phrase), graphe de cooccurrence dans le GraphStore `networkx` (un concept est un nœud rattaché aux
Passages qui le citent ; deux concepts d'un même Passage sont reliés), communautés Louvain
déterministes (graine de l'Expérience) sur ce graphe, où le poids d'une arête est le nombre de
Passages qui réunissent ses deux concepts. Dossier d'index : `passages.jsonl` (feuilles),
`graph/` (GraphStore), `communities.json`.

Requête : les concepts de la Question (même heuristique, la Question étant précédée d'un mot
neutre pour que son premier mot compte) classent les communautés par nombre de concepts de la
Question qu'elles contiennent (deux concepts se correspondent si les mots de l'un sont inclus dans
ceux de l'autre, mots outils et interrogatifs exclus) ; les Passages des meilleures communautés,
un Passage une seule fois, sont notés par le Decider (rôle `grade_relevance`, step
`lazygraphrag.grade.<n>`) dans la limite de `relevance_budget` Passages au total, borne vérifiée
avant chaque appel. Les Passages notés strictement au-dessus de `relevance_threshold` (0.1 : une
note nulle ou quasi nulle écarte le Passage) passent au Generator (`k` au plus, les mieux notés
d'abord). Aucun Passage pertinent, ou aucune communauté qui touche la Question : abstention sans
appel `generate`.

Simplifications documentées : concepts par heuristique (rate les noms en début de phrase et les
noms communs), un seul niveau de communautés, pas de rapport de communauté ; les Passages au-delà
du budget ne sont jamais lus.

Mise à jour incrémentale (Poste `update`) : `remove_passages` retire les Passages des Documents
supprimés ou remplacés, les concepts des Passages nouveaux sont ajoutés, Louvain est relancé
(gratuit). Aucun appel LLM.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.architectures._fenetre import borner_passages
from wavelibrarian.architectures._passages import ecrire_passages, lire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.components.deciders.llm import SYSTEM
from wavelibrarian.components.graph._texte import MARGE, borner, reserve_schema
from wavelibrarian.components.graph.communities import detect_communities, louvain_seed
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.ids import slug_entite
from wavelibrarian.core.types import (
    ArchAnswer,
    ParsedCorpus,
    Passage,
    QuestionInput,
    ScoredPassage,
)
from wavelibrarian.corpus.entities import extraire_entites
from wavelibrarian.llm.roles import GradeRelevanceOutput
from wavelibrarian.ports.architecture import ArchCapabilities, ArchitectureBase, CorpusChange
from wavelibrarian.ports.components import ComponentSpec, GenerationResult
from wavelibrarian.registry import register

_log = logging.getLogger(__name__)

_GRAPHE = "graph"
_COMMUNAUTES = "communities.json"
_KIND = "concept"
# Mots outils et interrogatifs : un concept réduit à eux (« Que », « Le ») ne rattache rien, et
# « Pourquoi Port Ysel » se lit « Port Ysel ».
_OUTILS = frozenset(
    "que qui quoi quel quelle quels quelles lequel laquelle lesquels lesquelles pourquoi comment "
    "combien quand où est sont le la les l un une des du de d au aux et ou en the a an of and or "
    "what who whom which why how when where is are".split()
)


def _spec(nom: str) -> Any:
    return Field(default_factory=lambda: ComponentSpec(name=nom))


def _mots(nom: str) -> frozenset[str]:
    """Mots d'un concept (espaces, traits d'union et apostrophes séparent), sans mots outils."""
    return frozenset(m for m in re.split(r"[\s'-]+", nom.casefold()) if m and m not in _OUTILS)


def _correspond(a: frozenset[str], b: frozenset[str]) -> bool:
    """Deux concepts se correspondent si les mots de l'un sont inclus dans ceux de l'autre."""
    return bool(a) and bool(b) and (a <= b or b <= a)


def _numerotes(textes: list[str]) -> str:
    return "\n\n".join(f"[{i}] {t}" for i, t in enumerate(textes, start=1))


def _ecrire_json(chemin: Path, contenu: Any) -> None:
    chemin.write_bytes(json.dumps(contenu, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _lire_json(chemin: Path) -> Any:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WlError(f"index illisible : {chemin} absent ou illisible") from exc


@register("architecture", "lazy_graphrag")
class LazyGraphRag(ArchitectureBase):
    """LazyGraphRAG maison : graphe de cooccurrence sans LLM, notation à la requête."""

    name = "lazy_graphrag"
    capabilities = ArchCapabilities(incremental_update=True, retrieval_method="ranked")
    query_params: ClassVar[frozenset[str]] = frozenset(
        {
            "relevance_budget",
            "relevance_threshold",
            "k",
            "grade_batch",
            "decider",
        }
    )

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        chunker: ComponentSpec = _spec("fixed_tokens")
        graph_store: ComponentSpec = _spec("networkx")
        context_builder: ComponentSpec = _spec("labeled")
        generator: ComponentSpec = _spec("llm")
        decider: ComponentSpec = _spec("llm")  # notation `grade_relevance` (modèle, max_tokens)
        min_community_size: int = Field(default=1, ge=1)
        # -- paramètres de requête ------------------------------------------------------------
        relevance_budget: int = Field(default=20, gt=0)  # Passages notés au plus, par Question
        relevance_threshold: float = Field(default=0.1, ge=0.0, le=1.0)  # pertinent : note >
        k: int = Field(default=5, gt=0)  # Passages pertinents envoyés au Generator
        grade_batch: int = Field(default=5, gt=0)  # Passages par appel `grade_relevance`

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.p: Any = params
        self.chunker = ctx.build("chunker", params.chunker)
        self.context_builder = ctx.build("context_builder", params.context_builder)
        self.generator = ctx.build("generator", params.generator)
        self.decider = ctx.build("decider", params.decider)
        self._grade_model: str = self.decider.model_id or ctx.profile.defaults.generator_models[0]
        self._grade_max_tokens = int(getattr(self.decider, "max_tokens", 256))
        self._passages: dict[str, Passage] = {}
        self._graphe: Any = None
        self._communautes: list[dict[str, Any]] = []
        self._charge = False

    def _fenetre(self, modele: str) -> int | None:
        fenetre: int | None = self.ctx.catalog.get(modele).context_window  # type: ignore[attr-defined]
        return fenetre

    def _nouveau_graphe(self) -> Any:
        return self.ctx.build("graph_store", self.p.graph_store)  # type: ignore[attr-defined]

    # -- indexation -----------------------------------------------------------------------------

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        feuilles = [p for doc in corpus.documents for p in self.chunker.chunk(doc)]
        graphe = self._nouveau_graphe()
        self._verser(graphe, feuilles)
        self._finaliser(directory, feuilles, graphe)

    def update(
        self,
        change: CorpusChange,
        corpus_after: ParsedCorpus,
        old_directory: Path,
        new_directory: Path,
    ) -> None:
        """Retire les Passages des Documents supprimés ou remplacés, ajoute les concepts des
        Passages nouveaux ; aucun appel LLM."""
        retires = set(change.removed) | {ancien for ancien, _ in change.modified}
        nouveaux_docs = [*change.added, *(doc for _, doc in change.modified)]
        anciens = [p for p in lire_passages(old_directory) if p.level == 0]
        nouveaux = [p for doc in nouveaux_docs for p in self.chunker.chunk(doc)]  # type: ignore[attr-defined]
        graphe = self._nouveau_graphe()
        graphe.load(old_directory / _GRAPHE)
        graphe.remove_passages([p.passage_id for p in anciens if p.doc_id in retires])
        self._verser(graphe, nouveaux)
        rang = {d.doc_id: i for i, d in enumerate(corpus_after.documents)}
        feuilles = sorted(
            [*(p for p in anciens if p.doc_id not in retires), *nouveaux],
            key=lambda p: rang.get(p.doc_id or "", len(rang)),
        )  # tri stable : l'ordre d'une indexation complète
        self._finaliser(new_directory, feuilles, graphe)

    @staticmethod
    def _verser(graphe: Any, feuilles: list[Passage]) -> None:
        """Concepts de chaque Passage, puis cooccurrences (toutes les paires du Passage)."""
        for p in feuilles:
            trouves = sorted({(slug_entite(c), c) for c in extraire_entites(p.text)})
            concepts = [(i, c) for i, c in trouves if i]
            for eid, nom in concepts:
                graphe.upsert_entity(eid, nom, _KIND, "", [p.passage_id])
            for a in range(len(concepts)):
                for b in range(a + 1, len(concepts)):
                    graphe.upsert_relation(
                        concepts[a][0], concepts[b][0], "cooccurrence", 1.0, [p.passage_id]
                    )

    def _finaliser(self, directory: Path, feuilles: list[Passage], graphe: Any) -> None:
        ponderee = graphe.graph().copy()  # poids d'une arête : Passages qui réunissent ses concepts
        for _, _, d in ponderee.edges(data=True):
            d["weight"] = float(len(d["passage_ids"]))
        communautes = detect_communities(
            ponderee,
            louvain_seed(self.ctx.seed),  # type: ignore[attr-defined]
            self.p.min_community_size,
        )
        ecrire_passages(directory, feuilles)
        graphe.save(directory / _GRAPHE)
        fiches = [{"community_id": c.community_id, "members": list(c.members)} for c in communautes]
        _ecrire_json(directory / _COMMUNAUTES, {"communities": fiches})

    # -- chargement -----------------------------------------------------------------------------

    def load(self, directory: Path) -> None:
        self._passages = {p.passage_id: p for p in lire_passages(directory)}
        self._graphe = self._nouveau_graphe()
        self._graphe.load(directory / _GRAPHE)
        self._communautes = _lire_json(directory / _COMMUNAUTES)["communities"]
        self._charge = True

    # -- requête --------------------------------------------------------------------------------

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if not self._charge:
            raise RuntimeError("`load` doit précéder `answer`")
        notes = self._noter(question, self._candidats(question))
        pertinents = sorted(
            ((p, s) for p, s in notes if s > self.p.relevance_threshold),
            key=lambda t: (-t[1], t[0].passage_id),
        )[: self.p.k]
        if not pertinents:
            return self._vide()
        classes = [
            ScoredPassage(passage=p, score=float(s), rank=r)
            for r, (p, s) in enumerate(pertinents, start=1)
        ]
        return self._generer(question, classes)

    def _candidats(self, question: QuestionInput) -> list[Passage]:
        """Passages des communautés qui touchent la Question, meilleure communauté d'abord, dans la
        limite de `relevance_budget`."""
        g = self._graphe.graph()
        # « — » : mot neutre qui laisse compter le premier mot de la Question
        questions = [_mots(c) for c in sorted(extraire_entites(f"— {question.text}"))]
        classees: list[tuple[int, int, str, list[str], set[str]]] = []
        for c in self._communautes:
            membres = [m for m in c["members"] if m in g]
            mots = {m: _mots(g.nodes[m]["name"]) for m in membres}
            touches = {m for m in membres if any(_correspond(mots[m], q) for q in questions)}
            score = sum(1 for q in questions if any(_correspond(mots[m], q) for m in membres))
            if score:
                classees.append((score, len(membres), c["community_id"], membres, touches))
        classees.sort(key=lambda t: (-t[0], -t[1], t[2]))
        vus: set[str] = set()
        candidats: list[Passage] = []
        for _, _, _, membres, touches in classees:
            poids: dict[str, tuple[int, int]] = {}
            for m in membres:
                for i in g.nodes[m]["passage_ids"]:
                    if i in self._passages and i not in vus:
                        a, b = poids.get(i, (0, 0))
                        poids[i] = (a + (m in touches), b + 1)
            for i in sorted(poids, key=lambda i: (-poids[i][0], -poids[i][1], i)):
                vus.add(i)
                candidats.append(self._passages[i])
            if len(candidats) >= self.p.relevance_budget:
                break
        return candidats[: self.p.relevance_budget]

    def _noter(
        self, question: QuestionInput, candidats: list[Passage]
    ) -> list[tuple[Passage, float]]:
        """Rôle `grade_relevance` par lots ; `relevance_budget` est vérifié avant chaque appel."""
        p = self.p
        notes: list[tuple[Passage, float]] = []
        n = 0
        while len(notes) < len(candidats):
            restant = p.relevance_budget - len(notes)
            if restant <= 0:  # borne vérifiée avant l'appel
                break
            lot = self._lot(question, candidats[len(notes) :], min(p.grade_batch, restant))
            n += 1
            scores = self._appeler(question, n, lot)
            notes.extend(zip(lot, scores, strict=True))
        return notes

    def _lot(self, question: QuestionInput, suite: list[Passage], taille: int) -> list[Passage]:
        """Au plus `taille` Passages dont la notation tient dans la fenêtre du modèle ; au moins
        un (un Passage seul trop long est tronqué avec avertissement par `_appeler`)."""
        fenetre = self._fenetre(self._grade_model)
        lot = suite[:taille]
        if fenetre is None:
            return lot
        tok = self.ctx.tokenizer_for(self._grade_model)  # type: ignore[attr-defined]
        libre = (
            fenetre
            - int(tok.count(SYSTEM))
            - int(tok.count(question.text))
            - self._grade_max_tokens
            - reserve_schema(self.ctx, self._grade_model, GradeRelevanceOutput)
            - MARGE
        )
        while len(lot) > 1 and int(tok.count(_numerotes([q.text for q in lot]))) > libre:
            lot = lot[:-1]
        return lot

    def _appeler(self, question: QuestionInput, n: int, lot: list[Passage]) -> list[float]:
        if len(lot) == 1:
            texte = borner(
                self.ctx,
                self._grade_model,
                f"{SYSTEM}\nQuestion : {question.text}",
                lot[0].text,
                self._grade_max_tokens,
                "lazy_graphrag.grade",
                reserve=reserve_schema(self.ctx, self._grade_model, GradeRelevanceOutput),
            )
            lot = [lot[0].model_copy(update={"text": texte})]
        return list(self.decider.grade(question, lot, step=f"lazygraphrag.grade.{n}"))

    def _vide(self) -> ArchAnswer:
        tokenizer = self.ctx.tokenizer_for(self.generator.model_id)  # type: ignore[attr-defined]
        contexte = self.context_builder.build([])
        vide = GenerationResult(text="", abstained=True, citations=(), invalid_citations=0)
        return build_arch_answer(contexte, vide, [], "ranked", tokenizer=tokenizer)

    def _generer(self, question: QuestionInput, classes: list[ScoredPassage]) -> ArchAnswer:
        """Generator sur les Passages que la fenêtre garde (les écartés quittent `retrieved`)."""
        tokenizer = self.ctx.tokenizer_for(self.generator.model_id)  # type: ignore[attr-defined]
        gardes = borner_passages(self, question, [s.passage for s in classes], "lazy_graphrag")
        ids = {p.passage_id for p in gardes}
        classes = [
            s.model_copy(update={"rank": i})
            for i, s in enumerate((s for s in classes if s.passage.passage_id in ids), start=1)
        ]
        contexte = self.context_builder.build(gardes)
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(contexte, resultat, classes, "ranked", tokenizer=tokenizer)
