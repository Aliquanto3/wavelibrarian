"""Architecture `pageindex` : un LLM navigue dans la table des matières, sans embedding (FR-24).

Indexation : un arbre par Document. Chaque Ancrage du Document devient un nœud ; la hiérarchie
suit `heading_path` (parent = nœud du plus long préfixe de titres déjà vu), et un PDF sans titre
donne une liste plate de nœuds « Page n ». Un nœud porte son titre, son Ancrage, le texte de sa
propre section et un résumé court (rôle `summarize`, step `pageindex.summarize`, Poste courant,
`indexing` sous le runner). Les arbres sont écrits dans `tree.json` : `load` n'appelle rien.

Navigation (`answer`) : la liste de départ réunit les nœuds de premier niveau de tous les
Documents. À chaque sélection (rôle `select_nodes`, step `pageindex.select.<n>`, entrées
`question`, `nodes` = `[{id, title, summary}]`, `max` = lectures restantes), les identifiants
valides sont lus (texte de leur section, dans l'ordre de lecture). Si `done` est faux, les enfants
des nœuds choisis forment la liste suivante ; sinon la navigation s'arrête. Un identifiant inconnu
(ou non proposé à cette étape) est ignoré et compté dans un avertissement du journal. Aucun nœud
lu : abstention sans appel `generate`. `max_nodes_read` est vérifié avant chaque appel de
sélection et avant chaque lecture. Réponse en `retrieval_method: provided`, aucun embedding.

Fenêtre : le texte envoyé au résumé est tronqué (avertissement) pour tenir dans celle du modèle.
Une liste de sélection qui n'y tient pas est découpée en lots consécutifs, un appel (et un span)
par lot, la borne vérifiée avant chacun ; un `done` vrai arrête la navigation après lecture, sans
présenter les lots suivants. Les sections lues qui ne tiennent pas dans la fenêtre du générateur
sont écartées en partant de la dernière lue (avertissement), et une section seule trop longue est
tronquée (avertissement). Une fenêtre qui ne laisse aucune place lève `ConfigError`.

Navigation : un nœud choisi est lu même si `done` est faux (ses enfants sont alors proposés à
l'étape suivante) ; la descente ne revient jamais à un niveau déjà parcouru.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

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
from wavelibrarian.llm.roles import SelectNodesOutput
from wavelibrarian.ports.arch_answer import passages_fournis
from wavelibrarian.ports.architecture import ArchCapabilities, ArchitectureBase, CorpusChange
from wavelibrarian.ports.components import ComponentSpec, GenerationResult
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_log = logging.getLogger(__name__)

# Réserve pour le system du générateur et l'habillage du message (« Contexte : », « Question : »).
_MARGE_GENERATE = 256

_FICHIER = "tree.json"
_SYSTEM_RESUME = (
    "Résume en une ou deux phrases, dans la langue du texte, la section suivante d'un document. "
    "Garde les noms, les dates et les chiffres utiles pour décider s'il faut la lire."
)
_SYSTEM_SELECTION = (
    "Tu navigues dans la table des matières de documents. Pour la question, choisis au plus `max` "
    "nœuds à lire parmi ceux proposés (identifiant, titre, résumé). Réponds en JSON : "
    '{"node_ids": ["..."], "done": true}. `done` vaut true quand les nœuds choisis suffisent, '
    "false pour descendre dans leurs sous-sections."
)


@dataclass
class _Noeud:
    node_id: str
    doc_id: str
    anchor_id: str
    title: str
    text: str
    parent: str | None
    children: list[str] = field(default_factory=list)
    summary: str = ""


def _couper(texte: str, tokenizer: Any, limite: int) -> str:
    """Raccourcit `texte` (par pas de 20 %) jusqu'à tenir dans `limite` tokens."""
    coupe = texte
    while coupe and tokenizer.count(coupe) > limite:
        coupe = coupe[: int(len(coupe) * 0.8)]
    return coupe


def _id_noeud(anchor_id: str) -> str:
    return sha16("node", "pageindex", anchor_id)


def _noeuds_du_document(doc: ParsedDocument) -> list[_Noeud]:
    """Un nœud par Ancrage, dans l'ordre du Document ; hiérarchie par `heading_path`."""
    textes: dict[str, list[str]] = {}
    for bloc in doc.blocks:
        textes.setdefault(bloc.anchor_id, []).append(bloc.text)
    noeuds: list[_Noeud] = []
    derniers: dict[tuple[str, ...], _Noeud] = {}
    for anchor_id, ancre in doc.anchors.items():
        chemin = ancre.heading_path
        if ancre.page is not None:
            titre = f"Page {ancre.page}"
        else:
            titre = chemin[-1] if chemin else Path(doc.source_path).name
        parent: _Noeud | None = None
        for taille in range(len(chemin) - 1, 0, -1):
            parent = derniers.get(chemin[:taille])
            if parent is not None:
                break
        noeud = _Noeud(
            node_id=_id_noeud(anchor_id),
            doc_id=doc.doc_id,
            anchor_id=anchor_id,
            title=titre,
            text="\n\n".join(textes.get(anchor_id, [])),
            parent=parent.node_id if parent else None,
        )
        if parent is not None:
            parent.children.append(noeud.node_id)
        if chemin and ancre.page is None:
            derniers[chemin] = noeud
        noeuds.append(noeud)
    return noeuds


@register("architecture", "pageindex")
class PageIndex(ArchitectureBase):
    """Arbre des sections par Document, navigué par le rôle `select_nodes` (sans embedding)."""

    name = "pageindex"
    capabilities = ArchCapabilities(incremental_update=True, retrieval_method="provided")
    query_params: ClassVar[frozenset[str]] = frozenset(
        {"max_nodes_read", "select_model", "select_max_tokens"}
    )

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        context_builder: ComponentSpec = Field(
            default_factory=lambda: ComponentSpec(name="labeled")
        )
        generator: ComponentSpec = Field(default_factory=lambda: ComponentSpec(name="llm"))
        max_nodes_read: int = Field(default=8, gt=0)
        summary_model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        summary_max_tokens: int = Field(default=128, gt=0)
        select_model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        select_max_tokens: int = Field(default=256, gt=0)

    def __init__(self, params: Any, ctx: Any) -> None:
        super().__init__(params, ctx)
        self.generator = ctx.build("generator", params.generator)
        self.context_builder = ctx.build("context_builder", params.context_builder)
        defaut = ctx.profile.defaults.generator_models[0]
        self._summary_model: str = params.summary_model or defaut
        self._select_model: str = params.select_model or defaut
        self._noeuds: dict[str, _Noeud] = {}
        self._racines: list[str] = []
        self._charge = False

    # -- fenêtre --------------------------------------------------------------------------------

    def _fenetre(self, modele: str) -> int | None:
        fenetre: int | None = self.ctx.catalog.get(modele).context_window  # type: ignore[attr-defined]
        return fenetre

    def _tronquer(self, texte: str) -> str:
        """Texte du résumé ramené à ce que la fenêtre du modèle laisse, sortie réservée comprise."""
        fenetre = self._fenetre(self._summary_model)
        if fenetre is None:
            return texte
        tokenizer = self.ctx.tokenizer_for(self._summary_model)  # type: ignore[attr-defined]
        reserve = self.params.summary_max_tokens + tokenizer.count(_SYSTEM_RESUME)  # type: ignore[attr-defined]
        limite = fenetre - reserve
        if limite < 1:
            raise ConfigError(
                "summary_max_tokens",
                f"`pageindex` : la sortie réservée et le system ({reserve} tokens) ne laissent "
                f"aucune place dans la fenêtre de {fenetre} tokens de `{self._summary_model}`",
            )
        coupe = _couper(texte, tokenizer, limite)
        if coupe != texte:
            _log.warning(
                "pageindex : section tronquée avant résumé (fenêtre de %d tokens)", fenetre
            )
        return coupe

    # -- indexation -----------------------------------------------------------------------------

    def _resumer(self, noeud: _Noeud) -> str:
        if not noeud.text.strip():
            return ""
        texte = self._tronquer(noeud.text)
        requete = LLMRequest(
            model_id=self._summary_model,
            role="summarize",
            step="pageindex.summarize",
            system=_SYSTEM_RESUME,
            messages=(Message(role="user", content=f"{noeud.title}\n\n{texte}"),),
            max_tokens=self.params.summary_max_tokens,  # type: ignore[attr-defined]
            seed=self.ctx.seed,  # type: ignore[attr-defined]
            inputs={"text": texte},
        )
        return str(self.ctx.gateway.complete(requete).text).strip()  # type: ignore[attr-defined]

    def _arbres(self, documents: tuple[ParsedDocument, ...]) -> list[_Noeud]:
        noeuds: list[_Noeud] = []
        for doc in documents:
            for noeud in _noeuds_du_document(doc):
                noeud.summary = self._resumer(noeud)
                noeuds.append(noeud)
        return noeuds

    @staticmethod
    def _ecrire(directory: Path, noeuds: list[_Noeud]) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        contenu = json.dumps(
            {"nodes": [vars(n) for n in noeuds]}, ensure_ascii=False, indent=1, sort_keys=True
        )
        (directory / _FICHIER).write_bytes((contenu + "\n").encode("utf-8"))

    @staticmethod
    def _lire(directory: Path) -> list[_Noeud]:
        chemin = directory / _FICHIER
        try:
            brut = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WlError(f"index illisible : {chemin} absent ou illisible") from exc
        return [_Noeud(**n) for n in brut["nodes"]]

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        self._ecrire(directory, self._arbres(corpus.documents))

    def update(
        self,
        change: CorpusChange,
        corpus_after: ParsedCorpus,
        old_directory: Path,
        new_directory: Path,
    ) -> None:
        """Garde les arbres des Documents inchangés ; ne résume que les Documents ajoutés ou
        modifiés. L'ordre final suit celui des Documents de `corpus_after`."""
        retires = set(change.removed) | {ancien for ancien, _ in change.modified}
        nouveaux = {d.doc_id for d in change.added} | {d.doc_id for _, d in change.modified}
        par_doc: dict[str, list[_Noeud]] = {}
        for n in self._lire(old_directory):
            if n.doc_id not in retires and n.doc_id not in nouveaux:
                par_doc.setdefault(n.doc_id, []).append(n)
        # Un Document dit inchangé mais absent de l'ancien index est reconstruit, pas perdu.
        absents = {
            d.doc_id
            for d in corpus_after.documents
            if d.doc_id not in nouveaux and d.doc_id not in par_doc and d.anchors
        }
        if absents:
            _log.warning(
                "pageindex : %d Document(s) inchangé(s) hors de l'ancien index, reconstruit(s)",
                len(absents),
            )
        a_faire = tuple(d for d in corpus_after.documents if d.doc_id in nouveaux | absents)
        for n in self._arbres(a_faire):
            par_doc.setdefault(n.doc_id, []).append(n)
        ordonnes = [n for d in corpus_after.documents for n in par_doc.get(d.doc_id, [])]
        self._ecrire(new_directory, ordonnes)

    def load(self, directory: Path) -> None:
        noeuds = self._lire(directory)
        self._noeuds = {n.node_id: n for n in noeuds}
        self._racines = [n.node_id for n in noeuds if n.parent is None]
        self._charge = True

    # -- navigation -----------------------------------------------------------------------------

    @staticmethod
    def _items(noeuds: list[_Noeud]) -> list[dict[str, str]]:
        return [{"id": n.node_id, "title": n.title, "summary": n.summary} for n in noeuds]

    @staticmethod
    def _contenu(question: QuestionInput, liste: list[dict[str, str]], restant: int) -> str:
        corps = json.dumps(liste, ensure_ascii=False)
        return f"Question : {question.text}\nmax : {restant}\nNoeuds : {corps}"

    def _lots(self, question: QuestionInput, proposes: list[_Noeud]) -> list[list[_Noeud]]:
        """Découpe la liste du niveau en lots consécutifs qui tiennent dans la fenêtre."""
        fenetre = self._fenetre(self._select_model)
        if fenetre is None:
            return [proposes]
        tokenizer = self.ctx.tokenizer_for(self._select_model)  # type: ignore[attr-defined]
        p: Any = self.params
        entete = _SYSTEM_SELECTION + "\n" + self._contenu(question, [], p.max_nodes_read)
        fixe = tokenizer.count(entete) + p.select_max_tokens
        lots: list[list[_Noeud]] = []
        lot: list[_Noeud] = []
        taille = fixe
        for noeud, item in zip(proposes, self._items(proposes), strict=True):
            cout = tokenizer.count(json.dumps(item, ensure_ascii=False)) + 2  # virgule, arrondi
            if lot and taille + cout > fenetre:
                lots.append(lot)
                lot, taille = [], fixe
            lot.append(noeud)
            taille += cout
        if lot:
            lots.append(lot)
        return lots

    def _selectionner(
        self, question: QuestionInput, proposes: list[_Noeud], restant: int, etape: int
    ) -> SelectNodesOutput:
        liste = self._items(proposes)
        contenu = self._contenu(question, liste, restant)
        fenetre = self._fenetre(self._select_model)
        p: Any = self.params
        if fenetre is not None:
            tokenizer = self.ctx.tokenizer_for(self._select_model)  # type: ignore[attr-defined]
            besoin = tokenizer.count(_SYSTEM_SELECTION + "\n" + contenu) + p.select_max_tokens
            if besoin > fenetre:
                raise ConfigError(
                    "select_model",
                    f"`pageindex` : la liste de {len(liste)} noeuds (environ {besoin} tokens avec "
                    f"la sortie) dépasse la fenêtre de {fenetre} tokens de `{self._select_model}`",
                )
        requete = LLMRequest(
            model_id=self._select_model,
            role="select_nodes",
            step=f"pageindex.select.{etape}",
            system=_SYSTEM_SELECTION,
            messages=(Message(role="user", content=contenu),),
            max_tokens=p.select_max_tokens,
            seed=self.ctx.seed,  # type: ignore[attr-defined]
            inputs={"question": question.text, "nodes": liste, "max": restant},
        )
        sortie, _ = self.ctx.gateway.complete_structured(requete, SelectNodesOutput)  # type: ignore[attr-defined]
        return sortie

    @staticmethod
    def _passage(noeud: _Noeud) -> Passage:
        return Passage(
            passage_id=sha16(noeud.doc_id, "pageindex", noeud.anchor_id),
            doc_id=noeud.doc_id,
            text=noeud.text,
            anchor_ids=(noeud.anchor_id,),
        )

    def _naviguer(self, question: QuestionInput) -> list[Passage]:
        borne: int = self.params.max_nodes_read  # type: ignore[attr-defined]
        proposes = [self._noeuds[i] for i in self._racines]
        lus: list[Passage] = []
        vus: set[str] = set()
        etape = 0
        while proposes and len(lus) < borne:
            suivants: list[_Noeud] = []
            choisis = False
            arret = False
            for lot in self._lots(question, proposes):
                if len(lus) >= borne:  # borne vérifiée avant chaque appel
                    break
                etape += 1
                sortie = self._selectionner(question, lot, borne - len(lus), etape)
                offerts = {n.node_id for n in lot}
                valides: list[_Noeud] = []
                inconnus = 0
                for node_id in dict.fromkeys(sortie.node_ids):
                    if node_id in offerts:
                        valides.append(self._noeuds[node_id])
                    else:
                        inconnus += 1
                if inconnus:
                    _log.warning(
                        "pageindex : %d identifiant(s) de noeud inconnu(s) ignoré(s) à l'étape %d",
                        inconnus,
                        etape,
                    )
                for noeud in valides:
                    if len(lus) >= borne:  # borne vérifiée avant chaque lecture
                        break
                    if noeud.node_id in vus or not noeud.text.strip():
                        continue
                    vus.add(noeud.node_id)
                    lus.append(self._passage(noeud))
                choisis = choisis or bool(valides)
                suivants.extend(self._noeuds[c] for n in valides for c in n.children)
                if sortie.done:
                    arret = True
                    break
            if arret or not choisis:
                break
            proposes = suivants
        return lus

    def _borner_contexte(self, question: QuestionInput, lus: list[Passage]) -> list[Passage]:
        """Garde les sections lues qui tiennent dans la fenêtre du générateur (avertissement)."""
        modele: str | None = getattr(self.generator, "model_id", None)
        fenetre = self._fenetre(modele) if modele else None
        if modele is None or fenetre is None or not lus:
            return lus
        tokenizer = self.ctx.tokenizer_for(modele)  # type: ignore[attr-defined]
        fixe = (
            int(tokenizer.count(question.text))
            + sum(int(tokenizer.count(t.text)) for t in question.history)
            + int(getattr(self.generator, "max_tokens", 0))
            + _MARGE_GENERATE
        )
        if fixe >= fenetre:
            raise ConfigError(
                "generator",
                f"`pageindex` : la question et la sortie réservée ({fixe} tokens) ne laissent "
                f"aucune place dans la fenêtre de {fenetre} tokens de `{modele}`",
            )

        def taille(passages: list[Passage]) -> int:
            return int(tokenizer.count(self.context_builder.build(passages).text)) + fixe

        gardes = list(lus)
        while len(gardes) > 1 and taille(gardes) > fenetre:
            gardes.pop()
        if len(gardes) < len(lus):
            _log.warning(
                "pageindex : %d section(s) lue(s) écartée(s), hors de la fenêtre de %d tokens",
                len(lus) - len(gardes),
                fenetre,
            )
        if taille(gardes) > fenetre:  # une seule section, trop longue : tronquée
            seul = gardes[0]
            habillage = taille([seul.model_copy(update={"text": ""})]) - fixe
            texte = _couper(seul.text, tokenizer, fenetre - fixe - habillage)
            if not texte:
                raise ConfigError(
                    "generator",
                    f"`pageindex` : aucune section ne tient dans la fenêtre de {fenetre} tokens "
                    f"de `{modele}`",
                )
            _log.warning(
                "pageindex : section tronquée avant génération (fenêtre de %d tokens)", fenetre
            )
            gardes = [seul.model_copy(update={"text": texte})]
        return gardes

    def answer(self, question: QuestionInput) -> ArchAnswer:
        if not self._charge:
            raise RuntimeError("`load` doit précéder `answer`")
        lus = self._borner_contexte(question, self._naviguer(question))
        contexte = self.context_builder.build(lus)
        tokenizer = self.ctx.tokenizer_for(self.generator.model_id)  # type: ignore[attr-defined]
        if not lus:
            vide = GenerationResult(text="", abstained=True, citations=(), invalid_citations=0)
            return build_arch_answer(contexte, vide, [], "provided", tokenizer=tokenizer)
        resultat = self.generator.generate(question, contexte)
        return build_arch_answer(
            contexte, resultat, passages_fournis(lus), "provided", tokenizer=tokenizer
        )
