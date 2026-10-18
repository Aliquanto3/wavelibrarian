"""Architecture `llm_wiki` : le Corpus compilé en pages de wiki par un LLM (FR-25).

Indexation : pour chaque Document, un ou plusieurs appels `wiki_compile` (step `wiki.compile`,
Poste courant, `indexing` sous le runner) rendent des pages `{title, body, anchor_ids}`. Chaque
page devient un Passage de `level` 1 dont les `anchor_ids` sont les Ancrages déclarés qui existent
dans le Corpus ; une page sans Ancrage valide est écartée, comptée et journalisée. Les pages vont
dans `passages.jsonl`, dans un index lexical (BM25, dossier `lexical/`) et dans `wiki.json`
(pages avec leur Document source, Documents compilés, nombre de pages écartées).

Fidélité : en fin d'indexation (et de mise à jour), `fidelity_sample` pages sont tirées de façon
déterministe (graine de l'Expérience, pages triées par id) et vérifiées par le rôle
`wiki_fidelity` (step `wiki.fidelity`) contre le texte de leurs Ancrages. `wiki_fidelity.json`
(pages, `claims`, `supported`) est écrit dans le dossier d'index ; le runner le copie.

Requête : les `k` pages les mieux classées par l'index lexical vont au Generator
(`retrieval_method: provided`) ; une Citation d'une page remonte à ses Ancrages par la table
`labels` (AD-7). Aucune page trouvée : abstention sans appel `generate`.

Fenêtre : le contenu d'un appel `wiki_compile` qui dépasse la fenêtre du modèle est découpé en
lots de Blocks consécutifs (un appel par lot) ; un Block seul trop long est tronqué avec un
avertissement. Pour la fidélité, les sources qui ne tiennent pas sont écartées depuis la
dernière, la page seule trop longue est tronquée, chaque fois avec un avertissement. Les pages
fournies au Generator sont bornées par la fenêtre de celui-ci (`_fenetre.borner_passages`).

Mise à jour incrémentale : seuls les Documents ajoutés ou modifiés sont recompilés (Poste
`update` fixé par le runner) ; les pages des Documents supprimés ou modifiés sont retirées, les
autres gardent leurs Ancrages filtrés sur le Corpus après mise à jour (une page qui n'en garde
aucun est écartée). La fidélité est remesurée sur les pages résultantes.
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian.architectures._fenetre import borner_passages, couper
from wavelibrarian.architectures._passages import ecrire_passages, lire_passages
from wavelibrarian.components.context import build_arch_answer
from wavelibrarian.core.errors import ConfigError, WlError
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import (
    ArchAnswer,
    ModelRefMeta,
    ParsedCorpus,
    ParsedDocument,
    Passage,
    QuestionInput,
)
from wavelibrarian.llm.roles import WikiCompileOutput, WikiFidelityOutput
from wavelibrarian.ports.arch_answer import passages_fournis
from wavelibrarian.ports.architecture import ArchCapabilities, ArchitectureBase, CorpusChange
from wavelibrarian.ports.components import ComponentSpec, GenerationResult, SearchIndex
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_log = logging.getLogger(__name__)

FICHIER_WIKI = "wiki.json"
FICHIER_FIDELITE = "wiki_fidelity.json"
_SOUS_DOSSIER = "lexical"
_SYSTEM_COMPILE = (
    "Tu compiles des documents en pages de wiki. Pour les documents fournis, écris des pages "
    "courtes et fidèles, sans rien inventer. Réponds en JSON : "
    '{"pages": [{"title": "...", "body": "...", "anchor_ids": ["..."]}]}. '
    "`anchor_ids` liste les identifiants d'Ancrage des Blocks dont la page tire ses affirmations."
)
_SYSTEM_FIDELITE = (
    "Compte les affirmations (phrases) de la page et celles que les sources soutiennent. "
    'Réponds en JSON : {"claims": 0, "supported": 0}.'
)


@dataclass
class _Page:
    passage_id: str
    source_doc_id: str
    title: str
    body: str
    anchor_ids: list[str]

    @property
    def text(self) -> str:
        return f"{self.title}\n\n{self.body}"


def _texte_ancrages(corpus: ParsedCorpus) -> dict[str, str]:
    """Texte de chaque Ancrage du Corpus (Blocks joints), pour la fidélité."""
    morceaux: dict[str, list[str]] = {}
    for doc in corpus.documents:
        for bloc in doc.blocks:
            morceaux.setdefault(bloc.anchor_id, []).append(bloc.text)
    return {a: "\n\n".join(t) for a, t in morceaux.items()}


@register("architecture", "llm_wiki")
class LlmWiki(ArchitectureBase):
    """Corpus compilé en pages de wiki (Passages de `level` 1), retrouvées par BM25."""

    name = "llm_wiki"
    capabilities = ArchCapabilities(incremental_update=True, retrieval_method="provided")
    query_params: ClassVar[frozenset[str]] = frozenset({"k"})

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        lexical_index: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="bm25"))
        retriever: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="lexical"))
        context_builder: ComponentSpec = Field(
            default_factory=lambda: ComponentSpec(name="labeled")
        )
        generator: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="llm"))
        k: int = Field(default=5, gt=0)
        fidelity_sample: int = Field(default=5, ge=0)
        compile_model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        compile_max_tokens: int = Field(default=1024, gt=0)
        fidelity_model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        fidelity_max_tokens: int = Field(default=64, gt=0)

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.retriever = ctx.build("retriever", params.retriever)
        self.context_builder = ctx.build("context_builder", params.context_builder)
        self.generator = ctx.build("generator", params.generator)
        defaut = ctx.profile.defaults.generator_models[0]
        self._compile_model: str = params.compile_model or defaut
        self._fidelity_model: str = params.fidelity_model or defaut
        self._index: SearchIndex | None = None

    # -- fenêtre --------------------------------------------------------------------------------

    def _fenetre(self, modele: str) -> int | None:
        fenetre: int | None = self.ctx.catalog.get(modele).context_window  # type: ignore[attr-defined]
        return fenetre

    # -- compilation ----------------------------------------------------------------------------

    def _lots_de_blocks(self, doc: ParsedDocument) -> list[list[dict[str, str]]]:
        """Blocks non vides du Document, en lots consécutifs qui tiennent dans la fenêtre."""
        blocks = [{"anchor_id": b.anchor_id, "text": b.text} for b in doc.blocks if b.text.strip()]
        fenetre = self._fenetre(self._compile_model)
        if fenetre is None:
            return [blocks] if blocks else []
        p: Any = self.params
        tokenizer = self.ctx.tokenizer_for(self._compile_model)  # type: ignore[attr-defined]
        fixe = tokenizer.count(_SYSTEM_COMPILE + doc.source_path) + p.compile_max_tokens + 64
        if fixe >= fenetre:
            raise ConfigError(
                "compile_max_tokens",
                f"`llm_wiki` : le system et la sortie réservée ({fixe} tokens) ne laissent "
                f"aucune place dans la fenêtre de {fenetre} tokens de `{self._compile_model}`",
            )
        lots: list[list[dict[str, str]]] = []
        lot: list[dict[str, str]] = []
        taille = fixe
        for bloc in blocks:
            cout = tokenizer.count(json.dumps(bloc, ensure_ascii=False)) + 2
            if fixe + cout > fenetre:  # un Block seul qui n'y tient pas : tronqué
                vide = tokenizer.count(json.dumps({**bloc, "text": ""}, ensure_ascii=False)) + 2
                texte = couper(bloc["text"], tokenizer, max(fenetre - fixe - vide, 0))
                _log.warning(
                    "llm_wiki : Block tronqué avant compilation (fenêtre de %d tokens)", fenetre
                )
                bloc = {**bloc, "text": texte}
                cout = tokenizer.count(json.dumps(bloc, ensure_ascii=False)) + 2
            if lot and taille + cout > fenetre:
                lots.append(lot)
                lot, taille = [], fixe
            lot.append(bloc)
            taille += cout
        if lot:
            lots.append(lot)
        return lots

    def _compiler(self, doc: ParsedDocument, existants: set[str]) -> tuple[list[_Page], int]:
        """Pages d'un Document (Ancrages filtrés sur `existants`) et nombre de pages écartées."""
        pages: list[_Page] = []
        ecartees = 0
        p: Any = self.params
        for lot in self._lots_de_blocks(doc):
            documents = [{"source_path": doc.source_path, "blocks": lot}]
            requete = LLMRequest(
                model_id=self._compile_model,
                role="wiki_compile",
                step="wiki.compile",
                system=_SYSTEM_COMPILE,
                messages=(Message(role="user", content=json.dumps(documents, ensure_ascii=False)),),
                max_tokens=p.compile_max_tokens,
                seed=self.ctx.seed,  # type: ignore[attr-defined]
                inputs={"documents": documents},
            )
            sortie, _ = self.ctx.gateway.complete_structured(requete, WikiCompileOutput)  # type: ignore[attr-defined]
            for page in sortie.pages:
                valides = [a for a in dict.fromkeys(page.anchor_ids) if a in existants]
                if not valides:
                    ecartees += 1
                    _log.warning("llm_wiki : page « %s » écartée, aucun Ancrage valide", page.title)
                    continue
                pages.append(
                    _Page(
                        passage_id=sha16("page", "llm_wiki", doc.doc_id, str(len(pages))),
                        source_doc_id=doc.doc_id,
                        title=page.title,
                        body=page.body,
                        anchor_ids=valides,
                    )
                )
        return pages, ecartees

    # -- fidélité -------------------------------------------------------------------------------

    def _tenir(self, page: str, sources: list[str]) -> tuple[str, list[str]]:
        """Page et sources ramenées à ce que la fenêtre du modèle de fidélité laisse."""
        fenetre = self._fenetre(self._fidelity_model)
        if fenetre is None:
            return page, sources
        p: Any = self.params
        tokenizer = self.ctx.tokenizer_for(self._fidelity_model)  # type: ignore[attr-defined]
        fixe = tokenizer.count(_SYSTEM_FIDELITE) + p.fidelity_max_tokens + 64
        if fixe >= fenetre:
            raise ConfigError(
                "fidelity_max_tokens",
                f"`llm_wiki` : le system et la sortie réservée ({fixe} tokens) ne laissent "
                f"aucune place dans la fenêtre de {fenetre} tokens de `{self._fidelity_model}`",
            )
        libre = fenetre - fixe
        tronque = False
        if tokenizer.count(page) > libre // 2:
            page = couper(page, tokenizer, libre // 2)
            tronque = True
        libre -= tokenizer.count(page)
        gardees: list[str] = []
        for source in sources:
            cout = tokenizer.count(source)
            if cout > libre:
                if gardees:
                    tronque = True
                    break
                source = couper(source, tokenizer, libre)
                cout = tokenizer.count(source)
                tronque = True
            gardees.append(source)
            libre -= cout
        if tronque:
            _log.warning(
                "llm_wiki : page ou sources écartées ou tronquées avant fidélité "
                "(fenêtre de %d tokens)",
                fenetre,
            )
        return page, gardees

    def _mesurer(self, pages: list[_Page], corpus: ParsedCorpus) -> dict[str, Any]:
        """Tire `fidelity_sample` pages (déterministe) et fait vérifier chacune par le LLM."""
        p: Any = self.params
        triees = sorted(pages, key=lambda x: x.passage_id)
        tirage = self.ctx.rng("llm_wiki", "fidelity").sample(  # type: ignore[attr-defined]
            triees, min(p.fidelity_sample, len(triees))
        )
        textes = _texte_ancrages(corpus)
        mesures: list[dict[str, Any]] = []
        for page in sorted(tirage, key=lambda x: x.passage_id):
            sources = [textes[a] for a in page.anchor_ids if a in textes]
            texte, sources = self._tenir(page.text, sources)
            requete = LLMRequest(
                model_id=self._fidelity_model,
                role="wiki_fidelity",
                step="wiki.fidelity",
                system=_SYSTEM_FIDELITE,
                messages=(
                    Message(
                        role="user",
                        content=json.dumps({"page": texte, "sources": sources}, ensure_ascii=False),
                    ),
                ),
                max_tokens=p.fidelity_max_tokens,
                seed=self.ctx.seed,  # type: ignore[attr-defined]
                inputs={"page": texte, "sources": sources},
            )
            sortie, _ = self.ctx.gateway.complete_structured(requete, WikiFidelityOutput)  # type: ignore[attr-defined]
            mesures.append(
                {
                    "passage_id": page.passage_id,
                    "title": page.title,
                    "anchor_ids": page.anchor_ids,
                    "claims": sortie.claims,
                    "supported": sortie.supported,
                }
            )
        return {
            "fidelity_sample": p.fidelity_sample,
            "pages": mesures,
            "claims": sum(m["claims"] for m in mesures),
            "supported": sum(m["supported"] for m in mesures),
        }

    # -- écriture et lecture --------------------------------------------------------------------

    @staticmethod
    def _passage(page: _Page, ancrage_doc: dict[str, str]) -> Passage:
        docs = {ancrage_doc[a] for a in page.anchor_ids if a in ancrage_doc}
        return Passage(
            passage_id=page.passage_id,
            doc_id=next(iter(docs)) if len(docs) == 1 else None,
            text=page.text,
            anchor_ids=tuple(page.anchor_ids),
            level=1,
        )

    def _ecrire(
        self,
        directory: Path,
        pages: list[_Page],
        compiles: list[str],
        ecartees: int,
        corpus: ParsedCorpus,
    ) -> None:
        mesure = self._mesurer(pages, corpus)  # avant toute écriture : un échec n'en laisse pas
        ancrage_doc = {a: d.doc_id for d in corpus.documents for a in d.anchors}
        passages = [self._passage(p, ancrage_doc) for p in pages]
        lexical = self.ctx.build("lexical_index", self.params.lexical_index)  # type: ignore[attr-defined]
        lexical.add(passages)
        ecrire_passages(directory, passages)
        lexical.save(directory / _SOUS_DOSSIER)
        wiki = {
            "compiled_docs": compiles,
            "discarded_pages": ecartees,
            "pages": [asdict(p) for p in pages],
        }
        for nom, contenu in ((FICHIER_WIKI, wiki), (FICHIER_FIDELITE, mesure)):
            texte = json.dumps(contenu, ensure_ascii=False, indent=1, sort_keys=True)
            (directory / nom).write_bytes((texte + "\n").encode("utf-8"))

    @staticmethod
    def _lire_wiki(directory: Path) -> dict[str, Any]:
        chemin = directory / FICHIER_WIKI
        try:
            brut: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WlError(f"index illisible : {chemin} absent ou illisible") from exc
        return brut

    # -- cycle de vie ---------------------------------------------------------------------------

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        existants = {a for d in corpus.documents for a in d.anchors}
        pages: list[_Page] = []
        ecartees = 0
        for doc in corpus.documents:
            faites, ecart = self._compiler(doc, existants)
            pages.extend(faites)
            ecartees += ecart
        if ecartees:
            _log.warning("llm_wiki : %d page(s) écartée(s) faute d'Ancrage valide", ecartees)
        self._ecrire(directory, pages, [d.doc_id for d in corpus.documents], ecartees, corpus)

    def update(
        self,
        change: CorpusChange,
        corpus_after: ParsedCorpus,
        old_directory: Path,
        new_directory: Path,
    ) -> None:
        """Ne recompile que les Documents ajoutés ou modifiés ; retire les pages des autres."""
        ancien = self._lire_wiki(old_directory)
        retires = set(change.removed) | {a for a, _ in change.modified}
        nouveaux = {d.doc_id for d in change.added} | {d.doc_id for _, d in change.modified}
        existants = {a for d in corpus_after.documents for a in d.anchors}
        compiles = set(ancien["compiled_docs"])
        # Un Document dit inchangé mais jamais compilé est compilé, pas perdu.
        absents = {
            d.doc_id
            for d in corpus_after.documents
            if d.doc_id not in nouveaux and d.doc_id not in compiles and d.blocks
        }
        if absents:
            _log.warning(
                "llm_wiki : %d Document(s) inchangé(s) hors de l'ancien index, compilé(s)",
                len(absents),
            )
        ecartees = 0
        gardees: dict[str, list[_Page]] = {}
        for brut in ancien["pages"]:
            page = _Page(**brut)
            if page.source_doc_id in retires or page.source_doc_id in nouveaux:
                continue
            page.anchor_ids = [a for a in page.anchor_ids if a in existants]
            if not page.anchor_ids:
                ecartees += 1
                _log.warning("llm_wiki : page « %s » écartée, plus d'Ancrage valide", page.title)
                continue
            gardees.setdefault(page.source_doc_id, []).append(page)
        for doc in corpus_after.documents:
            if doc.doc_id in nouveaux | absents:
                faites, ecart = self._compiler(doc, existants)
                gardees[doc.doc_id] = faites
                ecartees += ecart
        pages = [p for d in corpus_after.documents for p in gardees.get(d.doc_id, [])]
        self._ecrire(
            new_directory, pages, [d.doc_id for d in corpus_after.documents], ecartees, corpus_after
        )

    def load(self, directory: Path) -> None:
        lexical = self.ctx.build("lexical_index", self.params.lexical_index)  # type: ignore[attr-defined]
        lexical.load(directory / _SOUS_DOSSIER)
        passages = {p.passage_id: p for p in lire_passages(directory)}
        self._index = SearchIndex(passages=passages, lexical=lexical)

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if self._index is None:
            raise RuntimeError("`load` doit précéder `answer`")
        tokenizer = self.ctx.tokenizer_for(self.generator.model_id)  # type: ignore[attr-defined]
        classes = self.retriever.retrieve(question.text, self.params.k, self._index)  # type: ignore[attr-defined]
        pages = borner_passages(self, question, [s.passage for s in classes], "llm_wiki")
        contexte = self.context_builder.build(pages)
        if not pages:
            vide = GenerationResult(text="", abstained=True, citations=(), invalid_citations=0)
            return build_arch_answer(contexte, vide, [], "provided", tokenizer=tokenizer)
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(
            contexte, resultat, passages_fournis(pages), "provided", tokenizer=tokenizer
        )
