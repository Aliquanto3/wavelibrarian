"""Architecture `lightrag` : graphe de connaissances à recherche sur deux niveaux, entités et
relations, avec mise à jour incrémentale par union de graphes (FR-27), d'après Guo et al. (2024),
en version simplifiée.

Indexation (Poste `indexing` fixé par le runner) : découpage en Passages, un appel
`extract_entities` par Passage (step `graph.extract.<passage_id>`), fusion dans le GraphStore
`networkx`, puis deux index denses séparés (`numpy_exact`) : `vectors_entities/` (« nom :
description » de chaque entité) et `vectors_relations/` (« nom - nom : description » de chaque
relation). Le texte embarqué réunit toutes les descriptions distinctes extraites pour l'entité ou
la paire d'entités (triées, séparées par « ; »), comme LightRAG concatène les descriptions de ses
fusions ; pas de résumé LLM d'une description trop longue, que l'embedder tronque. Aucun rapport de
communauté, aucune détection de communautés. Dossier d'index :
`passages.jsonl` (feuilles seules), `graph/` (GraphStore), `entities.json` et `relations.json`
(empreinte du texte embarqué), `extractions.json` (cache d'extraction par texte).

Recherche : le niveau bas prend les `k_entities` entités les plus proches de la Question, le niveau
haut les `k_relations` relations les plus proches. Le contexte réunit les Passages sources des deux
résultats, dédoublonnés, les `k` mieux placés (score = somme des proximités des entités et des
relations qui citent le Passage ; ex æquo par id). Aucun appel avant le Generator ; aucun résultat :
abstention sans appel.

Simplification documentée (FR-27) : LightRAG demande au LLM des mots-clés de bas et de haut niveau ;
ici le mot-clé de la Question est son embedding direct, utilisé pour les deux niveaux. Pas de
fusion des listes de mots-clés, pas de réécriture de la Question.

Mise à jour incrémentale (Poste `update`) : `remove_passages` retire les Passages des Documents
supprimés ou remplacés (le GraphStore rejoue son journal des apports), le sous-graphe des Passages
ajoutés ou modifiés est uni au graphe existant. Un Passage dont le texte figure au cache
d'extraction y reprend son extraction sans appel, même si son id a changé ; aucun appel ne porte sur
un Passage inchangé. Seuls les embeddings des entités et des relations dont le texte change sont
recalculés.
"""

import json
import logging
from pathlib import Path
from typing import Annotated, Any, ClassVar

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.architectures._fenetre import borner_passages
from wavelibrarian.architectures._passages import ecrire_passages, lire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.components.graph.cache import cle_extraction, extraire_avec_cache
from wavelibrarian.components.graph.extraction import EntityExtractor
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.ids import sha16, slug_entite
from wavelibrarian.core.types import (
    ArchAnswer,
    ModelRefMeta,
    ParsedCorpus,
    Passage,
    QuestionInput,
    ScoredPassage,
)
from wavelibrarian.ports.architecture import ArchCapabilities, ArchitectureBase, CorpusChange
from wavelibrarian.ports.components import ComponentSpec, GenerationResult
from wavelibrarian.registry import register

_log = logging.getLogger(__name__)

_VEC_ENTITES = "vectors_entities"
_VEC_RELATIONS = "vectors_relations"
_GRAPHE = "graph"
_ENTITES = "entities.json"
_RELATIONS = "relations.json"
_EXTRACTIONS = "extractions.json"
_LOT = 64


def _spec(nom: str) -> Any:
    return Field(default_factory=lambda: ComponentSpec(name=nom))


_SEP = " ; "


def _descriptions(
    feuilles: list[Passage], extractions: dict[str, Any]
) -> tuple[dict[str, set[str]], dict[tuple[str, str], set[str]]]:
    """Descriptions distinctes extraites des Passages actuels, par entité et par paire (a < b).

    Le GraphStore ne garde que la plus longue ; LightRAG les encode toutes."""
    entites: dict[str, set[str]] = {}
    relations: dict[tuple[str, str], set[str]] = {}
    for p in feuilles:
        x = extractions.get(cle_extraction(p))
        if x is None:
            continue
        for eid, nom, _, d in x["entities"]:
            cle = slug_entite(str(eid)) or slug_entite(str(nom))
            if cle and d:
                entites.setdefault(cle, set()).add(str(d))
        for src, cib, d, _ in x["relations"]:
            a, b = slug_entite(str(src)), slug_entite(str(cib))
            if a and b and a != b and d:
                relations.setdefault((min(a, b), max(a, b)), set()).add(str(d))
    return entites, relations


def _texte(nom: str, descriptions: set[str] | None, defaut: str) -> str:
    return f"{nom} : {_SEP.join(sorted(descriptions)) if descriptions else defaut}"


def _id_relation(a: str, b: str) -> str:
    return sha16("relation", min(a, b), max(a, b))


def _ecrire_json(chemin: Path, contenu: Any) -> None:
    chemin.write_bytes(json.dumps(contenu, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _lire_json(chemin: Path) -> Any:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WlError(f"index illisible : {chemin} absent ou illisible") from exc


def _relations(g: Any) -> dict[str, tuple[str, str, str]]:
    """Relations du graphe : id -> (a, b, texte embarqué), a < b."""
    sortie: dict[str, tuple[str, str, str]] = {}
    for u, v, d in g.edges(data=True):
        a, b = min(u, v), max(u, v)
        texte = f"{g.nodes[a]['name']} - {g.nodes[b]['name']} : {d['description']}"
        sortie[_id_relation(a, b)] = (a, b, texte)
    return sortie


@register("architecture", "lightrag")
class LightRag(ArchitectureBase):
    """LightRAG maison : deux index denses (entités, relations), Passages sources dédoublonnés."""

    name = "lightrag"
    capabilities = ArchCapabilities(incremental_update=True, retrieval_method="ranked")
    query_params: ClassVar[frozenset[str]] = frozenset({"k", "k_entities", "k_relations"})

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        chunker: ComponentSpec = _spec("fixed_tokens")
        embedder: ComponentSpec = _spec("sentence_transformers")
        store: ComponentSpec = _spec("numpy_exact")
        graph_store: ComponentSpec = _spec("networkx")
        context_builder: ComponentSpec = _spec("labeled")
        generator: ComponentSpec = _spec("llm")
        extract_model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        extract_max_tokens: int = Field(default=1024, gt=0)
        # -- paramètres de requête ------------------------------------------------------------
        k: int = Field(default=5, gt=0)  # Passages sources du contexte
        k_entities: int = Field(default=5, gt=0)  # niveau bas
        k_relations: int = Field(default=5, gt=0)  # niveau haut

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.p: Any = params
        self.chunker = ctx.build("chunker", params.chunker)
        self.embedder = ctx.build("embedder", params.embedder)
        self.context_builder = ctx.build("context_builder", params.context_builder)
        self.generator = ctx.build("generator", params.generator)
        self._extract_model: str = params.extract_model or ctx.profile.defaults.generator_models[0]
        self._passages: dict[str, Passage] = {}
        self._graphe: Any = None
        self._vec_entites: Any = None
        self._vec_relations: Any = None
        self._relations: dict[str, tuple[str, str, str]] = {}
        self._charge = False

    def embedder_dim(self) -> int | None:
        return int(self.embedder.dim)

    def _fenetre(self, modele: str) -> int | None:
        fenetre: int | None = self.ctx.catalog.get(modele).context_window  # type: ignore[attr-defined]
        return fenetre

    def _nouveau_vecteurs(self) -> Any:
        spec = self.p.store
        avec_dim = ComponentSpec(name=spec.name, params={"dim": self.embedder.dim, **spec.params})
        return self.ctx.build("vector_store", avec_dim)  # type: ignore[attr-defined]

    def _nouveau_graphe(self) -> Any:
        return self.ctx.build("graph_store", self.p.graph_store)  # type: ignore[attr-defined]

    def _extracteur(self) -> EntityExtractor:
        return EntityExtractor(self.ctx, self._extract_model, self.p.extract_max_tokens)

    # -- indexation -----------------------------------------------------------------------------

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        feuilles = [p for doc in corpus.documents for p in self.chunker.chunk(doc)]
        graphe = self._nouveau_graphe()
        cache: dict[str, Any] = {}
        extraire_avec_cache(self._extracteur(), graphe, feuilles, cache)
        self._finaliser(
            directory,
            feuilles,
            graphe,
            (self._nouveau_vecteurs(), self._nouveau_vecteurs()),
            ({}, {}),
            cache,
        )

    def update(
        self,
        change: CorpusChange,
        corpus_after: ParsedCorpus,
        old_directory: Path,
        new_directory: Path,
    ) -> None:
        """Union du sous-graphe des Passages ajoutés ou modifiés au graphe existant."""
        retires = set(change.removed) | {ancien for ancien, _ in change.modified}
        nouveaux_docs = [*change.added, *(doc for _, doc in change.modified)]
        anciens = lire_passages(old_directory)
        nouveaux = [p for doc in nouveaux_docs for p in self.chunker.chunk(doc)]
        chemin_cache = old_directory / _EXTRACTIONS
        cache: dict[str, Any] = _lire_json(chemin_cache) if chemin_cache.exists() else {}
        graphe = self._nouveau_graphe()
        graphe.load(old_directory / _GRAPHE)
        graphe.remove_passages([p.passage_id for p in anciens if p.doc_id in retires])
        extraire_avec_cache(self._extracteur(), graphe, nouveaux, cache)
        vec_e, vec_r = self._nouveau_vecteurs(), self._nouveau_vecteurs()
        vec_e.load(old_directory / _VEC_ENTITES)
        vec_r.load(old_directory / _VEC_RELATIONS)
        rang = {d.doc_id: i for i, d in enumerate(corpus_after.documents)}
        feuilles = sorted(
            [*(p for p in anciens if p.doc_id not in retires), *nouveaux],
            key=lambda p: rang.get(p.doc_id or "", len(rang)),
        )  # tri stable : l'ordre d'une indexation complète
        empreintes = (
            _lire_json(old_directory / _ENTITES),
            _lire_json(old_directory / _RELATIONS),
        )
        self._finaliser(new_directory, feuilles, graphe, (vec_e, vec_r), empreintes, cache)

    def _synchroniser(
        self, vecteurs: Any, textes: dict[str, str], anciennes: dict[str, str]
    ) -> dict[str, str]:
        """Supprime les vecteurs disparus, encode ceux dont le texte a changé."""
        nouvelles = {i: sha16(t) for i, t in textes.items()}
        disparus = sorted(set(anciennes) - set(nouvelles))
        if disparus:
            vecteurs.delete(disparus)
        a_encoder = sorted(i for i, h in nouvelles.items() if anciennes.get(i) != h)
        for debut in range(0, len(a_encoder), _LOT):
            lot = a_encoder[debut : debut + _LOT]
            v = np.asarray(
                self.embedder.embed_passages([textes[i] for i in lot]), dtype=np.float32
            ).reshape(len(lot), -1)
            vecteurs.add(lot, v)
        return nouvelles

    def _finaliser(
        self,
        directory: Path,
        feuilles: list[Passage],
        graphe: Any,
        vecteurs: tuple[Any, Any],
        empreintes: tuple[dict[str, str], dict[str, str]],
        extractions: dict[str, Any],
    ) -> None:
        g = graphe.graph()
        desc_e, desc_r = _descriptions(feuilles, extractions)
        textes_e = {
            n: _texte(d["name"], desc_e.get(n), d["description"]) for n, d in g.nodes(data=True)
        }
        textes_r = {
            i: _texte(
                f"{g.nodes[a]['name']} - {g.nodes[b]['name']}",
                desc_r.get((a, b)),
                g.edges[a, b]["description"],
            )
            for i, (a, b, _) in _relations(g).items()
        }
        entites = self._synchroniser(vecteurs[0], textes_e, empreintes[0])
        relations = self._synchroniser(vecteurs[1], textes_r, empreintes[1])
        ecrire_passages(directory, feuilles)
        vecteurs[0].save(directory / _VEC_ENTITES)
        vecteurs[1].save(directory / _VEC_RELATIONS)
        graphe.save(directory / _GRAPHE)
        _ecrire_json(directory / _ENTITES, entites)
        _ecrire_json(directory / _RELATIONS, relations)
        cles = {cle_extraction(p) for p in feuilles}
        _ecrire_json(directory / _EXTRACTIONS, {k: v for k, v in extractions.items() if k in cles})

    # -- chargement -----------------------------------------------------------------------------

    def load(self, directory: Path) -> None:
        self._passages = {p.passage_id: p for p in lire_passages(directory)}
        self._vec_entites = self._nouveau_vecteurs()
        self._vec_entites.load(directory / _VEC_ENTITES)
        self._vec_relations = self._nouveau_vecteurs()
        self._vec_relations.load(directory / _VEC_RELATIONS)
        self._graphe = self._nouveau_graphe()
        self._graphe.load(directory / _GRAPHE)
        self._relations = _relations(self._graphe.graph())
        self._charge = True

    # -- requête --------------------------------------------------------------------------------

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if not self._charge:
            raise RuntimeError("`load` doit précéder `answer`")
        p = self.p
        g = self._graphe.graph()
        requete = np.asarray(self.embedder.embed_queries([question.text]), dtype=np.float32)
        requete = requete.reshape(-1)  # mot-clé = embedding direct de la Question (FR-27)
        bas = [(n, s) for n, s in self._vec_entites.search(requete, p.k_entities) if n in g]
        haut = [
            (i, s)
            for i, s in self._vec_relations.search(requete, p.k_relations)
            if i in self._relations
        ]
        poids: dict[str, float] = {}
        for n, s in bas:
            for i in g.nodes[n]["passage_ids"]:
                poids[i] = poids.get(i, 0.0) + s
        for rid, s in haut:
            a, b, _ = self._relations[rid]
            for i in g.edges[a, b]["passage_ids"]:
                poids[i] = poids.get(i, 0.0) + s
        sources = sorted((i for i in poids if i in self._passages), key=lambda i: (-poids[i], i))
        sources = sources[: p.k]
        tokenizer = self.ctx.tokenizer_for(self.generator.model_id)  # type: ignore[attr-defined]
        if not sources:
            contexte = self.context_builder.build([])
            vide = GenerationResult(text="", abstained=True, citations=(), invalid_citations=0)
            return build_arch_answer(contexte, vide, [], "ranked", tokenizer=tokenizer)
        lus = borner_passages(self, question, [self._passages[i] for i in sources], "lightrag")
        gardes = {x.passage_id for x in lus}
        classes = [
            ScoredPassage(passage=self._passages[i], score=float(poids[i]), rank=r)
            for r, i in enumerate((i for i in sources if i in gardes), start=1)
        ]  # rangs contigus après la borne de fenêtre
        contexte = self.context_builder.build(lus)
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(contexte, resultat, classes, "ranked", tokenizer=tokenizer)
