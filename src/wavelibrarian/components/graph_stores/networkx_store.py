"""GraphStore `networkx` : graphe non orienté en mémoire, sauvegardé en JSON (FR-27)."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import networkx as nx
from pydantic import BaseModel, ConfigDict

from wavelibrarian.components.graph.fusion import (
    KIND_GENERIQUE,
    meilleur_kind,
    meilleur_texte,
    nom_canonique,
)
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.ids import slug_entite
from wavelibrarian.registry import register

_FICHIER = "graph.json"


@register("graph_store", "networkx")
class NetworkxGraphStore:
    """Entités fusionnées par `slug_entite` (insensible à la casse, aux accents, à la forme de
    l'apostrophe et aux ligatures œ/æ).

    Un nœud porte `name`, `kind`, `description`, `passage_ids` et `noms` (forme -> nombre de
    mentions) ; une arête non orientée porte `description`, `weight`, `passage_ids`. Fusion
    indépendante de l'ordre des mentions (`components/graph/fusion.py`) : nom = forme la plus
    mentionnée (ex æquo la plus accentuée, puis la plus petite), type extrait prioritaire sur le
    type générique `entity` (sinon le plus petit), description = la plus longue, poids = le plus
    grand, Passages = union. Une relation dont une extrémité est inconnue crée cette entité (forme
    donnée, sans mention comptée, type `entity`). `remove_passages` ne recompte pas `noms`.
    """

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, params: "NetworkxGraphStore.Params", ctx: Any) -> None:
        self._g: nx.Graph = nx.Graph()

    def upsert_entity(
        self,
        entity_id: str,
        name: str,
        kind: str,
        description: str,
        passage_ids: Sequence[str],
    ) -> None:
        self._upsert(entity_id, name, kind, description, passage_ids, mention=True)

    def _upsert(
        self,
        entity_id: str,
        name: str,
        kind: str,
        description: str,
        passage_ids: Sequence[str],
        mention: bool,
    ) -> None:
        cle = slug_entite(entity_id) or slug_entite(name)
        if not cle:
            raise WlError(f"entité sans identifiant exploitable : {entity_id!r}")
        forme = name or entity_id
        if cle in self._g:
            n = self._g.nodes[cle]
            noms: dict[str, int] = dict(n.get("noms") or {n["name"]: 0})
            if mention or forme not in noms:
                noms[forme] = noms.get(forme, 0) + int(mention)
            n["noms"] = noms
            n["name"] = nom_canonique(noms)
            n["kind"] = meilleur_kind(n["kind"], kind)
            n["description"] = meilleur_texte(n["description"], description)
            n["passage_ids"] = sorted(set(n["passage_ids"]) | set(passage_ids))
        else:
            self._g.add_node(
                cle,
                name=forme,
                noms={forme: int(mention)},
                kind=kind,
                description=description,
                passage_ids=sorted(set(passage_ids)),
            )

    def upsert_relation(
        self,
        source: str,
        target: str,
        description: str,
        weight: float,
        passage_ids: Sequence[str],
    ) -> None:
        a, b = slug_entite(source), slug_entite(target)
        if not a or not b:
            raise WlError(f"relation sans extrémité exploitable : {source!r} -> {target!r}")
        if a == b:
            return  # pas de boucle : une entité ne se relie pas à elle-même
        for cle, brut in ((a, source), (b, target)):
            if cle not in self._g:
                self._upsert(cle, brut, KIND_GENERIQUE, "", passage_ids, mention=False)
            else:  # l'extrémité est mentionnée par les mêmes Passages
                n = self._g.nodes[cle]
                n["passage_ids"] = sorted(set(n["passage_ids"]) | set(passage_ids))
        if self._g.has_edge(a, b):
            e = self._g.edges[a, b]
            e["description"] = meilleur_texte(e["description"], description)
            e["weight"] = max(float(e["weight"]), float(weight))
            e["passage_ids"] = sorted(set(e["passage_ids"]) | set(passage_ids))
        else:
            self._g.add_edge(
                a,
                b,
                description=description,
                weight=float(weight),
                passage_ids=sorted(set(passage_ids)),
            )

    def remove_passages(self, passage_ids: Sequence[str]) -> None:
        """Retire ces Passages ; une entité ou une relation sans Passage est retirée."""
        retires = set(passage_ids)
        if not retires:
            return
        for a, b, e in list(self._g.edges(data=True)):
            restants = [p for p in e["passage_ids"] if p not in retires]
            if restants:
                e["passage_ids"] = restants
            else:
                self._g.remove_edge(a, b)
        for cle, n in list(self._g.nodes(data=True)):
            restants = [p for p in n["passage_ids"] if p not in retires]
            if restants:
                n["passage_ids"] = restants
            else:
                self._g.remove_node(cle)

    def graph(self) -> nx.Graph:
        return self._g

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        noeuds = [{"id": k, **d} for k, d in sorted(self._g.nodes(data=True))]
        aretes = sorted(
            (
                {"source": a, "target": b, **d}
                for a, b, d in ((min(u, v), max(u, v), d) for u, v, d in self._g.edges(data=True))
            ),
            key=lambda e: (e["source"], e["target"]),
        )
        contenu = json.dumps({"nodes": noeuds, "edges": aretes}, ensure_ascii=False, sort_keys=True)
        (directory / _FICHIER).write_bytes(contenu.encode("utf-8"))

    def load(self, directory: Path) -> None:
        try:
            brut = json.loads((directory / _FICHIER).read_text(encoding="utf-8"))
            g: nx.Graph = nx.Graph()
            for n in brut["nodes"]:
                n = dict(n)
                g.add_node(str(n.pop("id")), **n)
            for e in brut["edges"]:
                e = dict(e)
                g.add_edge(str(e.pop("source")), str(e.pop("target")), **e)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WlError(f"graphe illisible : {directory}") from exc
        self._g = g
