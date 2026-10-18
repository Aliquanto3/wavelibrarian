"""Cache d'extraction par texte (`extractions.json`), partagé par GraphRAG et LightRAG.

Un Document modifié change de `doc_id`, donc d'ids de Passages : la clé est le hash du texte, si
bien qu'un Passage au texte inchangé reprend son extraction, rattachée à son nouvel id, sans appel.
"""

from collections.abc import Sequence
from typing import Any

from wavelibrarian.components.graph.extraction import EntityExtractor, Extraction, ajouter
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import Passage
from wavelibrarian.ports.components import GraphStore


def cle_extraction(p: Passage) -> str:
    return sha16("extraction", p.text)


def brut(x: Extraction) -> dict[str, Any]:
    return {"entities": [list(e) for e in x.entities], "relations": [list(r) for r in x.relations]}


def depuis_brut(passage_id: str, contenu: dict[str, Any]) -> Extraction:
    return Extraction(
        passage_id,
        tuple((str(a), str(b), str(c), str(d)) for a, b, c, d in contenu["entities"]),
        tuple((str(a), str(b), str(c), float(w)) for a, b, c, w in contenu["relations"]),
    )


def extraire_avec_cache(
    extracteur: EntityExtractor,
    graphe: GraphStore,
    passages: Sequence[Passage],
    cache: dict[str, Any],
) -> list[Passage]:
    """Verse les Passages dans le graphe : cache d'abord, appel pour les autres ; met le cache à
    jour. Un texte répété dans le lot n'est extrait qu'une fois. Renvoie les Passages extraits par
    un appel."""
    a_extraire: list[Passage] = []
    repetes: list[Passage] = []
    en_attente: set[str] = set()
    for p in passages:
        cle = cle_extraction(p)
        contenu = cache.get(cle)
        if contenu is not None:
            ajouter(graphe, depuis_brut(p.passage_id, contenu))
        elif cle in en_attente:
            repetes.append(p)
        else:
            en_attente.add(cle)
            a_extraire.append(p)
    extraites = extracteur.extract_into(graphe, a_extraire)
    cache.update({cle_extraction(p): brut(x) for p, x in zip(a_extraire, extraites, strict=True)})
    for p in repetes:
        ajouter(graphe, depuis_brut(p.passage_id, cache[cle_extraction(p)]))
    return a_extraire
