"""Architecture `raptor` : arbre de résumés par regroupement récursif, interrogé à plat (FR-23).

Indexation : feuilles (chunker), puis jusqu'à `max_depth` niveaux de résumés. À chaque niveau,
les nœuds sont regroupés (voir `_grouper`) et chaque groupe est résumé par le rôle `summarize`
(step `raptor.summarize.level<n>`, Poste courant, `indexing` sous le runner). Feuilles et nœuds
vont dans le même store vectoriel et dans `passages.jsonl` : la recherche dense porte sur l'arbre
aplati. Un nœud porte `level` >= 1, `child_ids`, l'union des Ancrages de ses feuilles et un
`doc_id` nul s'il couvre plusieurs Documents. Une Citation d'un nœud devient des Citations vers
les Ancrages de ses feuilles par la table `labels` (AD-7), sans code propre ici.

Regroupement (déterministe, AD-20) : les nœuds sont ordonnés par plus proche voisin (cosinus,
départage par id, départ au plus petit id), puis coupés en `ceil(n / group_max)` groupes
consécutifs de tailles égales à un près. Chaque groupe compte donc entre `group_min` et
`group_max` nœuds ; seul un niveau de moins de `group_min` nœuds forme un unique groupe plus
petit (dernier groupe toléré). Simplification documentée : ce n'est pas un GMM/UMAP.
`group_max` >= 2 garantit que chaque niveau compte moins de nœuds que le précédent ; la
construction s'arrête dès qu'il reste un seul nœud (pas de résumé d'un nœud unique).

Fenêtre du modèle de résumé : avec le chunker `fixed_tokens`, la construction refuse une
configuration dont un groupe plein (`group_max` enfants de `max(size, summary_max_tokens)`
tokens) dépasserait la fenêtre du Catalogue ; chaque appel est de plus vérifié avant l'envoi,
pour qu'aucun prompt ne soit tronqué en silence (Ollama `num_ctx`).

Pas de mise à jour incrémentale : `update` reconstruit l'arbre sur `corpus_after`.
"""

import math
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from pydantic import Field, model_validator

from wavelibrarian.architectures._passages import ecrire_passages
from wavelibrarian.architectures.naive_rag import _SOUS_DOSSIER, NaiveRag
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import ModelRefMeta, ParsedCorpus, Passage
from wavelibrarian.ports.architecture import ArchCapabilities, CorpusChange
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.registry import register

_SYSTEM = (
    "Résume en quelques phrases, dans la langue du texte, les passages suivants qui traitent de "
    "sujets proches. Garde les noms, les dates et les chiffres utiles pour retrouver ces passages."
)
_REPLI_CARACTERES = 1000  # texte de repli si le résumé revient vide


def _normaliser(m: Any) -> Any:
    normes = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(normes > 0.0, normes, 1.0)


@register("architecture", "raptor")
class Raptor(NaiveRag):
    """RAPTOR : feuilles + niveaux de résumés dans un même store, recherche dense à plat."""

    name = "raptor"
    capabilities = ArchCapabilities(incremental_update=False, retrieval_method="ranked")

    class Params(NaiveRag.Params):
        group_min: int = Field(default=5, ge=1)
        group_max: int = Field(default=10, ge=2)  # >= 2 : chaque niveau réduit
        max_depth: int = Field(default=3, ge=1)
        summary_model: Annotated[str | None, ModelRefMeta("generator_models[0]")] = None
        summary_max_tokens: int = Field(default=256, gt=0)

        @model_validator(mode="after")
        def _bornes(self) -> "Raptor.Params":
            # 2 * group_min - 1 garantit que le découpage égal respecte group_min dès n > group_max.
            if self.group_max < 2 * self.group_min - 1:
                raise ValueError("group_max doit valoir au moins 2 * group_min - 1")
            return self

    def __init__(self, params: Any, ctx: Any) -> None:
        if params.retriever.name != "dense":
            raise ConfigError(
                "retriever",
                f"`raptor` cherche dans l'arbre aplati par embeddings : retriever `dense` seul, "
                f"pas `{params.retriever.name}`",
            )
        super().__init__(params, ctx)
        self._summary_model: str = params.summary_model or ctx.profile.defaults.generator_models[0]
        self._verifier_fenetre_configuree()

    # -- fenêtre du modèle de résumé ------------------------------------------------------------

    def _fenetre(self) -> int | None:
        return self.ctx.catalog.get(self._summary_model).context_window  # type: ignore[attr-defined]

    def _tokens_modele(self, n_reference: int) -> int:
        """Tokens de référence ramenés au modèle de résumé, comme l'estimation de la passerelle."""
        entree = self.ctx.catalog.get(self._summary_model)  # type: ignore[attr-defined]
        if entree.tokenizer == "reference":
            return math.ceil(Decimal(n_reference) * entree.token_factor)
        return n_reference

    def _verifier_fenetre_configuree(self) -> None:
        """Refus avant tout appel si un groupe plein dépasse la fenêtre (chunker `fixed_tokens`)."""
        fenetre = self._fenetre()
        spec = self.params.chunker  # type: ignore[attr-defined]
        if fenetre is None or spec.name != "fixed_tokens":
            return
        p: Any = self.params
        taille = int(spec.params.get("size", 300))
        par_enfant = max(self._tokens_modele(taille), p.summary_max_tokens)
        systeme = self._tokens_modele(self.ctx.tokenizer.count(_SYSTEM))  # type: ignore[attr-defined]
        besoin = p.group_max * par_enfant + systeme + p.summary_max_tokens
        if besoin > fenetre:
            raise ConfigError(
                "group_max",
                f"`raptor` : un groupe de {p.group_max} enfants (environ {besoin} tokens avec la "
                f"sortie) dépasse la fenêtre de {fenetre} tokens de `{self._summary_model}`",
            )

    def _verifier_fenetre(self, texte: str) -> None:
        """Contrôle avant chaque appel : entrée estimée + sortie réservée dans la fenêtre."""
        fenetre = self._fenetre()
        if fenetre is None:
            return
        tokenizer = self.ctx.tokenizer_for(self._summary_model)  # type: ignore[attr-defined]
        n = self._tokens_modele(tokenizer.count(_SYSTEM + "\n" + texte))
        n += self.params.summary_max_tokens  # type: ignore[attr-defined]
        if n > fenetre:
            raise ConfigError(
                "group_max",
                f"`raptor` : le texte à résumer (environ {n} tokens avec la sortie) dépasse la "
                f"fenêtre de {fenetre} tokens de `{self._summary_model}` ; baisser `group_max`",
            )

    # -- regroupement ---------------------------------------------------------------------------

    @staticmethod
    def _ordre_voisins(ids: list[str], vecteurs: Any) -> list[str]:
        """Chaîne de plus proches voisins ; départ au plus petit id, égalités par id."""
        rangs = sorted(range(len(ids)), key=lambda n: ids[n])
        m = vecteurs[rangs]  # lignes par id croissant : argmax rend le plus petit id ex æquo
        libres = np.ones(len(rangs), dtype=bool)
        courant = 0
        libres[0] = False
        ordre = [ids[rangs[0]]]
        for _ in range(len(rangs) - 1):
            courant = int(np.argmax(np.where(libres, m @ m[courant], -np.inf)))
            libres[courant] = False
            ordre.append(ids[rangs[courant]])
        return ordre

    def _grouper(self, ids: list[str], vecteurs: Any) -> list[list[str]]:
        n = len(ids)
        n_groupes = max(1, math.ceil(n / self.params.group_max))  # type: ignore[attr-defined]
        ordre = self._ordre_voisins(ids, _normaliser(np.asarray(vecteurs, dtype=np.float64)))
        base, extra = divmod(n, n_groupes)
        groupes: list[list[str]] = []
        debut = 0
        for g in range(n_groupes):
            taille = base + (1 if g < extra else 0)
            groupes.append(ordre[debut : debut + taille])
            debut += taille
        return groupes

    # -- construction ---------------------------------------------------------------------------

    def _resumer(self, niveau: int, enfants: list[Passage]) -> str:
        texte = "\n\n".join(p.text for p in enfants)
        self._verifier_fenetre(texte)
        requete = LLMRequest(
            model_id=self._summary_model,
            role="summarize",
            step=f"raptor.summarize.level{niveau}",
            system=_SYSTEM,
            messages=(Message(role="user", content=texte),),
            max_tokens=self.params.summary_max_tokens,  # type: ignore[attr-defined]
            seed=self.ctx.seed,  # type: ignore[attr-defined]
            inputs={"text": texte},
        )
        resume = str(self.ctx.gateway.complete(requete).text).strip()  # type: ignore[attr-defined]
        return resume or texte[:_REPLI_CARACTERES]

    def _noeud(self, niveau: int, enfants: list[Passage]) -> Passage:
        enfants = sorted(enfants, key=lambda p: p.passage_id)
        child_ids = tuple(p.passage_id for p in enfants)
        docs = {p.doc_id for p in enfants}
        ancrages = sorted({a for p in enfants for a in p.anchor_ids})
        return Passage(
            passage_id=sha16("node", "raptor", str(niveau), *child_ids),
            doc_id=next(iter(docs)) if len(docs) == 1 else None,
            text=self._resumer(niveau, enfants),
            anchor_ids=tuple(ancrages),
            level=niveau,
            child_ids=child_ids,
        )

    def _encoder_vecteurs(self, store: Any, passages: list[Passage]) -> Any:
        """Encode par lots, ajoute au store et renvoie la matrice des vecteurs."""
        sorties = []
        for debut in range(0, len(passages), 64):
            lot = passages[debut : debut + 64]
            v = np.asarray(
                self.embedder.embed_passages([p.text for p in lot]), dtype=np.float32
            ).reshape(len(lot), -1)
            store.add([p.passage_id for p in lot], v)
            sorties.append(v)
        if not sorties:
            return np.zeros((0, self.embedder.dim), dtype=np.float32)
        return np.concatenate(sorties)

    def index(self, corpus: ParsedCorpus, directory: Path) -> None:
        feuilles = sorted(
            (p for doc in corpus.documents for p in self.chunker.chunk(doc)),  # type: ignore[attr-defined]
            key=lambda p: p.passage_id,
        )
        store = self._nouveau_store()
        vecteurs = self._encoder_vecteurs(store, feuilles)
        tous: list[Passage] = list(feuilles)
        courant = feuilles
        max_depth: int = self.params.max_depth  # type: ignore[attr-defined]
        for niveau in range(1, max_depth + 1):
            if len(courant) <= 1:  # rien à regrouper : pas de résumé d'un nœud unique
                break
            par_id = {p.passage_id: p for p in courant}
            groupes = self._grouper([p.passage_id for p in courant], vecteurs)
            noeuds = [self._noeud(niveau, [par_id[i] for i in g]) for g in groupes]
            noeuds.sort(key=lambda p: p.passage_id)
            vecteurs = self._encoder_vecteurs(store, noeuds)
            tous.extend(noeuds)
            courant = noeuds
        ecrire_passages(directory, tous)
        store.save(directory / _SOUS_DOSSIER)

    def update(
        self,
        change: CorpusChange,
        corpus_after: ParsedCorpus,
        old_directory: Path,
        new_directory: Path,
    ) -> None:
        """Pas d'incrémental : l'arbre est reconstruit sur `corpus_after` (Poste `update`)."""
        self.index(corpus_after, new_directory)
