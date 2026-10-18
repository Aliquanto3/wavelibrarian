"""Architecture `graphrag` : graphe de connaissances, rapports de communauté, recherche locale et
globale (FR-27), d'après Edge et al. (2024), en version simplifiée.

Indexation (Poste `indexing` fixé par le runner) : découpage en Passages (feuilles), un appel
`extract_entities` par Passage (step `graph.extract.<passage_id>`), fusion dans le GraphStore
`networkx`, communautés Louvain déterministes (graine de l'Expérience), un rapport par communauté
(rôle `community_report`, Passage de `level` 1 aux Ancrages unis), embeddings des descriptions
d'entités dans un store `numpy_exact`. Dossier d'index : `passages.jsonl` (feuilles et rapports),
`vectors/` (entités), `graph/` (GraphStore), `communities.json` (communautés, signature, rapport),
`entities.json` (empreinte du texte embarqué de chaque entité).

Recherche `local` : les `k_entities` entités les plus proches de la Question (cosinus sur
« nom : description ») donnent un contexte de trois familles de blocs, dans cet ordre : leurs
Passages sources (les plus cités par ces entités, `k` au plus), un bloc de leurs relations
(`k_relations` au plus, aux Ancrages des Passages d'où elles viennent) et les rapports de leurs
communautés (`k_reports` au plus). Aucun appel avant le Generator.

Recherche `global` : map-reduce sur les rapports. Les rapports, du plus gros au plus petit
groupe, sont réunis par lots de `map_batch` ; un appel `global_map` par lot (step
`graphrag.map.<n>`, au plus `max_map_batches` lots, borne vérifiée avant chaque appel) rend les
points utiles à la Question. Chaque sortie devient un Passage de `level` 1 aux Ancrages unis du lot
et passe au Generator (reduce, rôle `generate`) : une Citation remonte aux Ancrages des rapports
(AD-7). Aucune sortie utile : abstention sans appel `generate`. Les Architectures ne voient pas le
Type de la Question (AD-6) : le mode est le paramètre `search`, dans `query_params`, donc les deux
recherches partagent le même index.

Simplifications documentées : un seul niveau de communautés (Louvain plat, pas de hiérarchie
Leiden) ; pas de score d'utilité par réponse de map ; le contrôle de fenêtre tronque avec un
avertissement (jamais en silence).

Mise à jour incrémentale (Poste `update`) : seuls les Passages ajoutés ou dont le texte a changé
sont extraits ; `remove_passages` retire ceux des Documents supprimés ou remplacés ; seules les
embeddings des entités modifiées sont recalculés ; seuls les rapports des communautés dont la
composition change (signature : texte de leur contexte et Passages sources) sont régénérés, les
autres sont repris tels quels.
"""

import json
import logging
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.architectures._fenetre import borner_passages
from wavelibrarian.architectures._passages import ecrire_passages, lire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.components.graph._texte import borner
from wavelibrarian.components.graph.communities import detect_communities, louvain_seed
from wavelibrarian.components.graph.extraction import EntityExtractor
from wavelibrarian.components.graph.reports import CommunityReporter, community_context
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.ids import sha16
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
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_log = logging.getLogger(__name__)

_VECTEURS = "vectors"
_GRAPHE = "graph"
_COMMUNAUTES = "communities.json"
_ENTITES = "entities.json"
_LOT = 64

_SYSTEM_MAP = (
    "Tu reçois des rapports de communauté numérotés [R1], [R2]… puis une question. Résume en "
    "quelques phrases, dans la langue de la question, les points de ces rapports utiles pour y "
    "répondre. Si aucun rapport n'est utile, réponds par un texte vide."
)


def _spec(nom: str) -> Any:
    return Field(default_factory=lambda: ComponentSpec(name=nom))


def _doc_commun(passages: list[Passage]) -> str | None:
    docs = {p.doc_id for p in passages}
    return next(iter(docs)) if len(docs) == 1 else None


def _texte_entite(noeud: dict[str, Any]) -> str:
    return f"{noeud['name']} : {noeud['description']}"


def _ecrire_json(chemin: Path, contenu: Any) -> None:
    chemin.write_bytes(json.dumps(contenu, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _lire_json(chemin: Path) -> Any:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WlError(f"index illisible : {chemin} absent ou illisible") from exc


@register("architecture", "graphrag")
class GraphRag(ArchitectureBase):
    """GraphRAG maison : graphe, rapports de communauté, recherche locale ou globale."""

    name = "graphrag"
    capabilities = ArchCapabilities(incremental_update=True, retrieval_method="ranked")
    query_params: ClassVar[frozenset[str]] = frozenset(
        {
            "search",
            "k",
            "k_entities",
            "k_relations",
            "k_reports",
            "map_batch",
            "max_map_batches",
            "map_model",
            "map_max_tokens",
        }
    )

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
        report_model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        report_max_tokens: int = Field(default=512, gt=0)
        min_community_size: int = Field(default=1, ge=1)
        # -- paramètres de requête ------------------------------------------------------------
        search: Literal["local", "global"] = "local"
        k: int = Field(default=5, gt=0)  # Passages sources du contexte local
        k_entities: int = Field(default=5, gt=0)
        k_relations: int = Field(default=10, gt=0)
        k_reports: int = Field(default=3, gt=0)
        map_batch: int = Field(default=5, gt=0)  # rapports par appel `global_map`
        max_map_batches: int = Field(default=20, gt=0)
        map_model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        map_max_tokens: int = Field(default=512, gt=0)

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.p: Any = params
        self.chunker = ctx.build("chunker", params.chunker)
        self.embedder = ctx.build("embedder", params.embedder)
        self.context_builder = ctx.build("context_builder", params.context_builder)
        self.generator = ctx.build("generator", params.generator)
        defaut = ctx.profile.defaults.generator_models[0]
        self._extract_model: str = params.extract_model or defaut
        self._report_model: str = params.report_model or defaut
        self._map_model: str = params.map_model or defaut
        self._passages: dict[str, Passage] = {}
        self._graphe: Any = None
        self._vecteurs: Any = None
        self._communautes: list[dict[str, Any]] = []
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

    # -- indexation -----------------------------------------------------------------------------

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        feuilles = [p for doc in corpus.documents for p in self.chunker.chunk(doc)]
        graphe = self._nouveau_graphe()
        EntityExtractor(self.ctx, self._extract_model, self.p.extract_max_tokens).extract_into(
            graphe, feuilles
        )
        self._finaliser(directory, feuilles, graphe, self._nouveau_vecteurs(), {}, {}, {})

    def update(
        self,
        change: CorpusChange,
        corpus_after: ParsedCorpus,
        old_directory: Path,
        new_directory: Path,
    ) -> None:
        """Extrait les seuls Passages nouveaux ou modifiés, retire ceux qui disparaissent."""
        retires = set(change.removed) | {ancien for ancien, _ in change.modified}
        nouveaux_docs = [*change.added, *(doc for _, doc in change.modified)]
        anciens = [p for p in lire_passages(old_directory) if p.level == 0]
        anciens_par_id = {p.passage_id: p for p in anciens}
        nouveaux = [p for doc in nouveaux_docs for p in self.chunker.chunk(doc)]  # type: ignore[attr-defined]
        identiques = {
            p.passage_id
            for p in nouveaux
            if p.passage_id in anciens_par_id and anciens_par_id[p.passage_id].text == p.text
        }
        a_retirer = [p.passage_id for p in anciens if p.doc_id in retires]
        a_retirer = [i for i in a_retirer if i not in identiques]
        a_extraire = [p for p in nouveaux if p.passage_id not in identiques]
        graphe = self._nouveau_graphe()
        graphe.load(old_directory / _GRAPHE)
        graphe.remove_passages(a_retirer)
        EntityExtractor(self.ctx, self._extract_model, self.p.extract_max_tokens).extract_into(
            graphe, a_extraire
        )
        vecteurs = self._nouveau_vecteurs()
        vecteurs.load(old_directory / _VECTEURS)
        empreintes = _lire_json(old_directory / _ENTITES)
        anciennes_communautes = {
            c["community_id"]: c for c in _lire_json(old_directory / _COMMUNAUTES)["communities"]
        }
        anciens_rapports = {p.passage_id: p for p in lire_passages(old_directory) if p.level == 1}
        retirees = set(a_retirer)
        gardes = [p for p in anciens if p.passage_id not in retirees]
        gardes_ids = {p.passage_id for p in gardes}
        feuilles = [*gardes, *(p for p in nouveaux if p.passage_id not in gardes_ids)]
        self._finaliser(
            new_directory,
            feuilles,
            graphe,
            vecteurs,
            empreintes,
            anciennes_communautes,
            anciens_rapports,
        )

    def _finaliser(
        self,
        directory: Path,
        feuilles: list[Passage],
        graphe: Any,
        vecteurs: Any,
        empreintes: dict[str, str],
        anciennes_communautes: dict[str, dict[str, Any]],
        anciens_rapports: dict[str, Passage],
    ) -> None:
        """Embeddings des entités changées, communautés, rapports régénérés si leur composition
        change, puis écriture de l'index."""
        g = graphe.graph()
        textes = {n: _texte_entite(d) for n, d in g.nodes(data=True)}
        nouvelles = {n: sha16(t) for n, t in textes.items()}
        disparues = sorted(set(empreintes) - set(nouvelles))
        if disparues:
            vecteurs.delete(disparues)
        a_encoder = sorted(n for n, h in nouvelles.items() if empreintes.get(n) != h)
        for debut in range(0, len(a_encoder), _LOT):
            lot = a_encoder[debut : debut + _LOT]
            v = np.asarray(
                self.embedder.embed_passages([textes[n] for n in lot]), dtype=np.float32
            ).reshape(len(lot), -1)
            vecteurs.add(lot, v)

        par_id = {p.passage_id: p for p in feuilles}
        communautes = detect_communities(
            g,
            louvain_seed(self.ctx.seed),
            self.p.min_community_size,  # type: ignore[attr-defined]
        )
        reporter = CommunityReporter(self.ctx, self._report_model, self.p.report_max_tokens)
        rapports: list[Passage] = []
        fiches: list[dict[str, Any]] = []
        for c in communautes:
            sources = sorted({i for m in c.members for i in g.nodes[m]["passage_ids"]})
            signature = sha16(community_context(g, c), *sources)
            ancienne = anciennes_communautes.get(c.community_id)
            rapport: Passage | None
            if ancienne is not None and ancienne["signature"] == signature:
                rapport = anciens_rapports.get(ancienne["report_id"] or "")
            else:
                rapport = reporter.report(g, c, par_id)
            if rapport is not None:
                rapports.append(rapport)
            fiches.append(
                {
                    "community_id": c.community_id,
                    "members": list(c.members),
                    "signature": signature,
                    "report_id": rapport.passage_id if rapport else None,
                }
            )
        ecrire_passages(directory, [*feuilles, *rapports])
        vecteurs.save(directory / _VECTEURS)
        graphe.save(directory / _GRAPHE)
        _ecrire_json(directory / _COMMUNAUTES, {"communities": fiches})
        _ecrire_json(directory / _ENTITES, nouvelles)

    # -- chargement -----------------------------------------------------------------------------

    def load(self, directory: Path) -> None:
        self._passages = {p.passage_id: p for p in lire_passages(directory)}
        self._vecteurs = self._nouveau_vecteurs()
        self._vecteurs.load(directory / _VECTEURS)
        self._graphe = self._nouveau_graphe()
        self._graphe.load(directory / _GRAPHE)
        self._communautes = _lire_json(directory / _COMMUNAUTES)["communities"]
        self._charge = True

    # -- requête --------------------------------------------------------------------------------

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if not self._charge:
            raise RuntimeError("`load` doit précéder `answer`")
        if self.p.search == "global":
            return self._repondre_global(question)
        return self._repondre_local(question)

    def _vide(self, question: QuestionInput) -> ArchAnswer:
        tokenizer = self.ctx.tokenizer_for(self.generator.model_id)  # type: ignore[attr-defined]
        contexte = self.context_builder.build([])
        vide = GenerationResult(text="", abstained=True, citations=(), invalid_citations=0)
        return build_arch_answer(contexte, vide, [], "ranked", tokenizer=tokenizer)

    def _generer(
        self,
        question: QuestionInput,
        contexte_passages: list[Passage],
        classes: list[ScoredPassage],
        derives: bool = False,
    ) -> ArchAnswer:
        """Generator sur les blocs que la fenêtre garde ; `derives` : les blocs écartés
        (sorties de map) retirent aussi les rapports dont ils viennent de `retrieved`."""
        tokenizer = self.ctx.tokenizer_for(self.generator.model_id)  # type: ignore[attr-defined]
        gardes = borner_passages(self, question, contexte_passages, "graphrag")
        gardes_ids = {p.passage_id for p in gardes}
        ecartes: set[str] = set()
        for e in contexte_passages:
            if e.passage_id not in gardes_ids:
                ecartes.add(e.passage_id)
                if derives:
                    ecartes.update(e.child_ids)
        classes = [s for s in classes if s.passage.passage_id not in ecartes]
        classes = [
            s.model_copy(update={"rank": i}) for i, s in enumerate(classes, start=1)
        ]  # rangs contigus après la borne de fenêtre
        contexte = self.context_builder.build(gardes)
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(contexte, resultat, classes, "ranked", tokenizer=tokenizer)

    # recherche locale

    def _repondre_local(self, question: QuestionInput) -> ArchAnswer:
        p = self.p
        g = self._graphe.graph()
        requete = np.asarray(self.embedder.embed_queries([question.text]), dtype=np.float32)
        proches = [
            (n, s) for n, s in self._vecteurs.search(requete.reshape(-1), p.k_entities) if n in g
        ]
        if not proches:
            return self._vide(question)
        scores_entites = dict(proches)

        # Passages sources : les plus cités par les entités proches (somme des proximités)
        poids: dict[str, float] = {}
        for n, s in proches:
            for i in g.nodes[n]["passage_ids"]:
                if i in self._passages:
                    poids[i] = poids.get(i, 0.0) + s
        sources = sorted(poids, key=lambda i: (-poids[i], i))[: p.k]

        # Relations incidentes aux entités proches, les plus fortes d'abord
        aretes = sorted(
            (
                (min(u, v), max(u, v), d)
                for u, v, d in g.edges(data=True)
                if u in scores_entites or v in scores_entites
            ),
            key=lambda t: (-float(t[2].get("weight", 1.0)), t[0], t[1]),
        )[: p.k_relations]
        bloc_relations = self._bloc_relations(g, aretes, scores_entites)

        # Rapports des communautés des entités proches
        rapports: list[tuple[Passage, float]] = []
        vus: set[str] = set()
        for n, s in proches:
            for c in self._communautes:
                rid = c["report_id"]
                if n in c["members"] and rid and rid not in vus and rid in self._passages:
                    vus.add(rid)
                    rapports.append((self._passages[rid], s))
        rapports = rapports[: p.k_reports]

        elements: list[tuple[Passage, float]] = [(self._passages[i], poids[i]) for i in sources]
        if bloc_relations is not None:
            elements.append(bloc_relations)
        elements.extend(rapports)
        if not elements:
            return self._vide(question)
        contexte_passages = [e[0] for e in elements]
        classes = sorted(
            enumerate(elements), key=lambda t: (-t[1][1], t[0])
        )  # score décroissant, ex æquo dans l'ordre du contexte
        scores = [
            ScoredPassage(passage=e[0], score=float(e[1]), rank=r)
            for r, (_, e) in enumerate(classes, start=1)
        ]
        return self._generer(question, contexte_passages, scores)

    def _bloc_relations(
        self, g: Any, aretes: list[Any], scores_entites: dict[str, float]
    ) -> tuple[Passage, float] | None:
        """Un bloc unique : les relations, aux Ancrages des Passages d'où elles viennent."""
        lignes: list[str] = []
        sources: set[str] = set()
        score = 0.0
        for a, b, d in aretes:
            lignes.append(f"{g.nodes[a]['name']} - {g.nodes[b]['name']} : {d['description']}")
            sources.update(i for i in d["passage_ids"] if i in self._passages)
            score = max(score, scores_entites.get(a, 0.0), scores_entites.get(b, 0.0))
        ancrages = sorted({a for i in sources for a in self._passages[i].anchor_ids})
        if not lignes or not ancrages:
            return None
        texte = "Relations :\n" + "\n".join(lignes)
        liste = [self._passages[i] for i in sorted(sources)]
        bloc = Passage(
            passage_id=sha16("node", "graphrag", "relations", texte),
            doc_id=_doc_commun(liste),
            text=texte,
            anchor_ids=tuple(ancrages),
            level=1,
            child_ids=tuple(sorted(sources)),
        )
        return bloc, score

    # recherche globale

    def _repondre_global(self, question: QuestionInput) -> ArchAnswer:
        p = self.p
        rapports = [
            (self._passages[c["report_id"]], len(c["members"]))
            for c in self._communautes
            if c["report_id"] and c["report_id"] in self._passages
        ]  # déjà du plus gros groupe au plus petit, ex æquo par id
        if not rapports:
            return self._vide(question)
        lots = [rapports[i : i + p.map_batch] for i in range(0, len(rapports), p.map_batch)]
        if len(lots) > p.max_map_batches:
            _log.warning(
                "graphrag : %d lots de rapports, seuls les %d premiers sont lus (max_map_batches)",
                len(lots),
                p.max_map_batches,
            )
            lots = lots[: p.max_map_batches]
        sorties: list[Passage] = []
        for n, lot in enumerate(lots, start=1):
            sortie = self._map(question, n, [r for r, _ in lot])
            if sortie is not None:
                sorties.append(sortie)
        if not sorties:
            return self._vide(question)
        utiles = {i for s in sorties for i in s.child_ids}
        classes = [
            ScoredPassage(passage=r, score=float(t), rank=i)
            for i, (r, t) in enumerate(((r, t) for r, t in rapports if r.passage_id in utiles), 1)
        ]  # score = taille de la communauté, décroissant
        return self._generer(question, sorties, classes, derives=True)

    def _map(self, question: QuestionInput, n: int, lot: list[Passage]) -> Passage | None:
        """Un appel `global_map` sur un lot de rapports ; sortie vide : lot sans intérêt."""
        reserve = int(self.ctx.tokenizer_for(self._map_model).count(question.text)) + 32  # type: ignore[attr-defined]
        rapports = "\n\n".join(f"[R{i}] {r.text}" for i, r in enumerate(lot, start=1))
        texte = borner(
            self.ctx,
            self._map_model,
            _SYSTEM_MAP,
            rapports,
            self.p.map_max_tokens,
            "global_map",
            reserve=reserve,
        )
        texte = f"{texte}\n\nQuestion : {question.text}"
        requete = LLMRequest(
            model_id=self._map_model,
            role="global_map",
            step=f"graphrag.map.{n}",
            system=_SYSTEM_MAP,
            messages=(Message(role="user", content=texte),),
            max_tokens=self.p.map_max_tokens,
            seed=self.ctx.seed,  # type: ignore[attr-defined]
            inputs={"text": texte},
        )
        points = str(self.ctx.gateway.complete(requete).text).strip()  # type: ignore[attr-defined]
        if not points:
            return None
        ids = tuple(sorted(r.passage_id for r in lot))
        return Passage(
            passage_id=sha16("node", "graphrag", "map", *ids),
            doc_id=_doc_commun(lot),
            text=points,
            anchor_ids=tuple(sorted({a for r in lot for a in r.anchor_ids})),
            level=1,
            child_ids=ids,
        )
