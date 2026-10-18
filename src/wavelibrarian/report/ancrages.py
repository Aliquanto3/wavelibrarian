"""Ancrages de référence des Questions, résolus sur le Corpus de la phase (contracts.md §7).

Le Rapport en a besoin pour les métriques de recherche : un Passage est pertinent si ses
`anchor_ids` recoupent les Ancrages de référence. Même résolution que le jugement du runner
(`Corpus après Scénario` pour `after_update`). Les Documents d'un Palier contiennent tous les
Documents des Ancrages de référence (AD-22) : le Corpus entier donne les mêmes identifiants.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from wavelibrarian.config.experiment import ResolvedExperiment
from wavelibrarian.core.types import ParsedCorpus, Phase, Question
from wavelibrarian.corpus.declare import DeclaredCorpus, declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.corpus.scenario import appliquer_fichier

log = logging.getLogger(__name__)

Resolveur = Callable[[str, Phase, Question], list[str]]  # (config_id, phase, Question) -> anchor_id


def resolveur_de(experience: ResolvedExperiment, wl_home: Path) -> Resolveur:
    """Résolveur paresseux : le Corpus n'est ingéré (cache de parsing) qu'à la première demande.
    Ancrage ou Corpus introuvable : liste vide et avertissement, jamais d'échec du Rapport."""
    parser_de = {c.id: c.parser.name for c in experience.configurations}
    declare_cache: list[DeclaredCorpus] = []
    corpus_de: dict[tuple[str, Phase], ParsedCorpus | None] = {}

    def corpus(parser: str, phase: Phase) -> ParsedCorpus | None:
        if (parser, phase) not in corpus_de:
            try:
                if not declare_cache:
                    declare_cache.append(declare(Path(experience.corpus)))
                decl = declare_cache[0]
                parse = ingest(decl, parser, wl_home=wl_home)
                if phase == "after_update":
                    if experience.scenario is None:
                        parse = None
                    else:
                        parse = appliquer_fichier(
                            parse, Path(experience.scenario), lang=decl.spec.lang, parser=parser
                        )[1]
                corpus_de[(parser, phase)] = parse
            except Exception as erreur:
                log.warning(
                    "Corpus indisponible pour les Ancrages (%s, %s) : %s", parser, phase, erreur
                )
                corpus_de[(parser, phase)] = None
        return corpus_de[(parser, phase)]

    def resoudre(config_id: str, phase: Phase, q: Question) -> list[str]:
        parse = corpus(parser_de.get(config_id, "auto"), phase)
        if parse is None:
            return []
        ids = (parse.resolve(r.doc, r.page, r.headings) for r in q.reference_anchors)
        return [i for i in ids if i is not None]

    return resoudre
