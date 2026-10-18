"""Communautés déterministes par Louvain de networkx (graine dérivée de l'Expérience)."""

from dataclasses import dataclass
from typing import Any

import networkx as nx

from wavelibrarian.core.ids import sha16


@dataclass(frozen=True)
class Community:
    """`community_id` ne dépend que de la composition : une communauté inchangée garde son id."""

    community_id: str
    members: tuple[str, ...]  # entity_id triés


def louvain_seed(experiment_seed: int) -> int:
    """Graine de Louvain dérivée de la graine de l'Expérience (AD-20)."""
    return int(sha16("louvain", str(experiment_seed)), 16) % (2**32)


def detect_communities(graph: "nx.Graph[Any]", seed: int, min_size: int = 1) -> list[Community]:
    """Louvain sur une copie canonique (nœuds et arêtes triés), graine fixée ; communautés triées
    par taille décroissante puis plus petit membre. Deux appels donnent les mêmes communautés."""
    if graph.number_of_nodes() == 0:
        return []
    g: nx.Graph[Any] = nx.Graph()
    for n in sorted(graph.nodes):
        g.add_node(n)
    for a, b, d in sorted(
        ((min(u, v), max(u, v), d) for u, v, d in graph.edges(data=True)),
        key=lambda t: (t[0], t[1]),
    ):
        g.add_edge(a, b, weight=float(d.get("weight", 1.0)))
    parts = nx.community.louvain_communities(g, weight="weight", seed=seed)
    communautes = [
        Community(sha16("community", *sorted(p)), tuple(sorted(p)))
        for p in parts
        if len(p) >= min_size
    ]
    communautes.sort(key=lambda c: (-len(c.members), c.members[0]))
    return communautes
