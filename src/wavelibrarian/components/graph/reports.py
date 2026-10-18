"""Rapports de communauté (rôle `community_report`) : un Passage de `level` 1 par communauté."""

import logging
from collections.abc import Mapping, Sequence
from typing import Any

import networkx as nx

from wavelibrarian.components.graph._texte import borner
from wavelibrarian.components.graph.communities import Community
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import Passage
from wavelibrarian.ports.gateway import LLMRequest, Message

_log = logging.getLogger(__name__)

_SYSTEM = (
    "Rédige le rapport de cette communauté d'entités : thème, entités clés, relations "
    "importantes. Réponds par le seul texte du rapport."
)


def community_context(graph: "nx.Graph[Any]", community: Community) -> str:
    """Entités puis relations internes de la communauté, triées, une ligne chacune."""
    lignes = []
    for m in community.members:
        n = graph.nodes[m]
        lignes.append(f"Entité {n['name']} ({n['kind']}) : {n['description']}")
    membres = set(community.members)
    for a, b in sorted((min(u, v), max(u, v)) for u, v in graph.edges):
        if a in membres and b in membres:
            lignes.append(
                f"Relation {graph.nodes[a]['name']} - {graph.nodes[b]['name']} : "
                f"{graph.edges[a, b]['description']}"
            )
    return "\n".join(lignes)


class CommunityReporter:
    """Un appel `community_report` par communauté, step `graph.report.<community_id>`.

    Le rapport est un Passage de `level` 1 : `child_ids` = Passages sources (ceux des entités de la
    communauté), `anchor_ids` = union de leurs Ancrages (AD-7), `doc_id` = le Document commun ou
    `None`. Une communauté sans Passage source connu, ou dont le rapport est vide, est écartée avec
    un avertissement.
    """

    def __init__(self, ctx: Any, model_id: str | None = None, max_tokens: int = 1024) -> None:
        self._ctx = ctx
        self.model_id: str = model_id or ctx.profile.defaults.generator_models[0]
        self._max_tokens = max_tokens

    def sources(
        self, graph: "nx.Graph[Any]", community: Community, passages: Mapping[str, Passage]
    ) -> list[Passage]:
        ids = {p for m in community.members for p in graph.nodes[m]["passage_ids"]}
        return [passages[i] for i in sorted(ids) if i in passages]

    def report(
        self, graph: "nx.Graph[Any]", community: Community, passages: Mapping[str, Passage]
    ) -> Passage | None:
        sources = self.sources(graph, community, passages)
        ancres = sorted({a for s in sources for a in s.anchor_ids})
        if not ancres:
            _log.warning(
                "communauté %s : aucun Passage source, rapport écarté", community.community_id
            )
            return None
        texte = borner(
            self._ctx,
            self.model_id,
            _SYSTEM,
            community_context(graph, community),
            self._max_tokens,
            "community_report",
        )
        requete = LLMRequest(
            model_id=self.model_id,
            role="community_report",
            step=f"graph.report.{community.community_id}",
            system=_SYSTEM,
            messages=(Message(role="user", content=texte),),
            max_tokens=self._max_tokens,
            seed=self._ctx.seed,
            inputs={"text": texte},
        )
        rapport = str(self._ctx.gateway.complete(requete).text).strip()
        if not rapport:
            _log.warning("communauté %s : rapport vide, écarté", community.community_id)
            return None
        docs = {s.doc_id for s in sources}
        return Passage(
            passage_id=sha16("node", "community_report", community.community_id),
            doc_id=next(iter(docs)) if len(docs) == 1 else None,
            text=rapport,
            anchor_ids=tuple(ancres),
            level=1,
            child_ids=tuple(s.passage_id for s in sources),
        )

    def reports(
        self,
        graph: "nx.Graph[Any]",
        communities: Sequence[Community],
        passages: Mapping[str, Passage],
    ) -> list[Passage]:
        sortie = [self.report(graph, c, passages) for c in communities]
        return [p for p in sortie if p is not None]
