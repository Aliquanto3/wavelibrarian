"""Extracteur d'entités LLM (rôle `extract_entities`), réutilisable par GraphRAG et LightRAG."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from wavelibrarian.components.graph._texte import borner, reserve_schema
from wavelibrarian.components.graph.fusion import meilleur_kind, meilleur_texte, nom_canonique
from wavelibrarian.core.ids import slug_entite
from wavelibrarian.core.types import Passage
from wavelibrarian.llm.roles import ExtractEntitiesOutput
from wavelibrarian.ports.components import GraphStore
from wavelibrarian.ports.gateway import LLMRequest, Message

_log = logging.getLogger(__name__)

_SYSTEM = (
    "Extrais du texte les entités nommées (name, kind, description) et les relations entre "
    "elles (source, target, description, weight entre 0 et 1). Réponds en JSON."
)


@dataclass(frozen=True)
class Extraction:
    """Ce qu'un Passage a produit : entités et relations, identifiants déjà normalisés."""

    passage_id: str
    entities: tuple[tuple[str, str, str, str], ...]  # (entity_id, name, kind, description)
    relations: tuple[
        tuple[str, str, str, float], ...
    ]  # (source_id, target_id, description, weight)


class EntityExtractor:
    """Un appel `extract_entities` par Passage, step `graph.extract.<passage_id>`.

    Chaque entité et chaque relation est rattachée au `passage_id` d'où elle vient. Une sortie non
    conforme est réessayée une fois par la passerelle puis lève `NonConformantOutput` (AD-4).
    Le poste (`indexing` ou `update`) est celui de la portée ouverte par le runner.
    """

    def __init__(self, ctx: Any, model_id: str | None = None, max_tokens: int = 1024) -> None:
        self._ctx = ctx
        self.model_id: str = model_id or ctx.profile.defaults.generator_models[0]
        self._max_tokens = max_tokens

    def extract_passage(self, passage: Passage) -> Extraction:
        texte = borner(
            self._ctx,
            self.model_id,
            _SYSTEM,
            passage.text,
            self._max_tokens,
            "extract_entities",
            reserve=reserve_schema(self._ctx, self.model_id, ExtractEntitiesOutput),
        )
        requete = LLMRequest(
            model_id=self.model_id,
            role="extract_entities",
            step=f"graph.extract.{passage.passage_id}",
            system=_SYSTEM,
            messages=(Message(role="user", content=texte),),
            max_tokens=self._max_tokens,
            seed=self._ctx.seed,
            inputs={"text": texte},
        )
        sortie, _ = self._ctx.gateway.complete_structured(requete, ExtractEntitiesOutput)
        # mentions d'une même entité dans le Passage : mêmes règles de fusion que le GraphStore
        noms: dict[str, dict[str, int]] = {}
        kinds: dict[str, str] = {}
        descriptions: dict[str, str] = {}
        for e in sortie.entities:
            cle = slug_entite(e.name)
            if not cle:
                continue
            compte = noms.setdefault(cle, {})
            compte[e.name] = compte.get(e.name, 0) + 1
            kinds[cle] = meilleur_kind(kinds.get(cle, ""), e.kind)
            descriptions[cle] = meilleur_texte(descriptions.get(cle, ""), e.description)
        entites = [(c, nom_canonique(noms[c]), kinds[c], descriptions[c]) for c in noms]
        relations = []
        for r in sortie.relations:
            a, b = slug_entite(r.source), slug_entite(r.target)
            if a and b and a != b:
                relations.append((a, b, r.description, float(r.weight)))
        return Extraction(passage.passage_id, tuple(entites), tuple(relations))

    def extract(self, passages: Sequence[Passage]) -> list[Extraction]:
        return [self.extract_passage(p) for p in passages]

    def extract_into(self, store: GraphStore, passages: Sequence[Passage]) -> list[Extraction]:
        """Extrait chaque Passage et verse le résultat dans le GraphStore."""
        resultats = self.extract(passages)
        for x in resultats:
            ajouter(store, x)
        return resultats


def ajouter(store: GraphStore, x: Extraction) -> None:
    """Verse une extraction dans le GraphStore, rattachée à son `passage_id`."""
    for eid, nom, kind, description in x.entities:
        store.upsert_entity(eid, nom, kind, description, [x.passage_id])
    for source, cible, description, poids in x.relations:
        store.upsert_relation(source, cible, description, poids, [x.passage_id])
