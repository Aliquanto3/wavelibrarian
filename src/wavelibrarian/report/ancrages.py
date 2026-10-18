"""Ancrages de référence des Questions, résolus sur le Corpus de la phase (contracts.md §7).

Le Rapport en a besoin pour les métriques de recherche : un Passage est pertinent si ses
`anchor_ids` recoupent les Ancrages de référence. Même résolution que le jugement du runner
(`Corpus après Scénario` pour `after_update`). Les Documents d'un Palier contiennent tous les
Documents des Ancrages de référence (AD-22) : le Corpus entier donne les mêmes identifiants.

Le Corpus est relu sur disque : son empreinte est comparée à celle du manifeste (`inputs`,
écrite au départ de l'Exécution). Un Corpus ou un Scénario modifié depuis rendrait des Ancrages
faux : la recherche n'est alors pas mesurée, et le Rapport le dit (`alertes`). Les Ancrages qui
ne se résolvent pas sont comptés et signalés de même.
"""

import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from wavelibrarian.config.experiment import ResolvedExperiment
from wavelibrarian.core.types import ParsedCorpus, Phase, Question
from wavelibrarian.corpus.declare import DeclaredCorpus, declare
from wavelibrarian.corpus.ingest import ingest
from wavelibrarian.corpus.scenario import appliquer_fichier

log = logging.getLogger(__name__)

Resolveur = Callable[[str, Phase, Question], list[str]]  # (config_id, phase, Question) -> anchor_id

# Empreinte du manifeste (`inputs`) qui couvre le Corpus de chaque phase.
_ENTREE_DE: dict[Phase, str] = {
    "base": "corpus_fingerprint",
    "after_update": "scenario_fingerprint",
}


class ResolveurCorpus:
    """Résolveur paresseux : le Corpus n'est ingéré (cache de parsing) qu'à la première demande.
    Ancrage ou Corpus introuvable, ou Corpus différent de celui de l'Exécution : liste vide et
    alerte (`alertes`), jamais d'échec du Rapport."""

    def __init__(
        self,
        experience: ResolvedExperiment,
        wl_home: Path,
        inputs: Mapping[str, Any] | None = None,
    ) -> None:
        self._experience = experience
        self._wl_home = wl_home
        self._inputs = inputs
        self._parser_de = {c.id: c.parser.name for c in experience.configurations}
        # Parser de l'empreinte du manifeste : celui de la première Configuration (runner).
        self._parser_ref = experience.configurations[0].parser.name
        self._declare: DeclaredCorpus | None = None
        self._corpus: dict[tuple[str, Phase], ParsedCorpus | None] = {}
        self._phases_ok: dict[Phase, bool] = {}
        self._alertes: dict[str, None] = {}  # ordonné, sans doublon
        self._non_resolus: dict[tuple[str, Phase], set[str]] = {}

    def _alerter(self, message: str) -> None:
        if message not in self._alertes:
            log.warning("%s", message)
            self._alertes[message] = None

    def _ingerer(self, parser: str, phase: Phase) -> ParsedCorpus | None:
        if (parser, phase) not in self._corpus:
            try:
                if self._declare is None:
                    self._declare = declare(Path(self._experience.corpus))
                decl = self._declare
                parse: ParsedCorpus | None = ingest(decl, parser, wl_home=self._wl_home)
                if phase == "after_update":
                    if self._experience.scenario is None or parse is None:
                        parse = None
                    else:
                        parse = appliquer_fichier(
                            parse,
                            Path(self._experience.scenario),
                            lang=decl.spec.lang,
                            parser=parser,
                        )[1]
            except Exception as erreur:
                self._alerter(
                    f"Corpus indisponible pour les Ancrages ({parser}, {phase}) : {erreur}"
                )
                parse = None
            self._corpus[(parser, phase)] = parse
        return self._corpus[(parser, phase)]

    def _phase_conforme(self, phase: Phase) -> bool:
        """Le Corpus relu a-t-il l'empreinte du manifeste pour cette phase ?"""
        if self._inputs is None or (phase == "after_update" and not self._experience.scenario):
            return True  # rien à comparer (tests), ou pas de Corpus après Scénario
        if phase not in self._phases_ok:
            cle = _ENTREE_DE[phase]
            attendue = self._inputs.get(cle)
            if attendue is None:
                self._alerter(
                    f"Empreinte `{cle}` absente du manifeste : le Corpus relu ({phase}) n'a pas "
                    "pu être comparé à celui de l'Exécution."
                )
                self._phases_ok[phase] = True
            else:
                ref = self._ingerer(self._parser_ref, phase)
                ok = ref is not None and ref.fingerprint == attendue
                if ref is not None and not ok:
                    self._alerter(
                        f"Corpus modifié depuis l'Exécution ({phase}) : empreinte "
                        f"{ref.fingerprint}, manifeste {attendue} (`{cle}`). Recherche non "
                        "mesurée pour cette phase."
                    )
                self._phases_ok[phase] = ok
        return self._phases_ok[phase]

    def __call__(self, config_id: str, phase: Phase, q: Question) -> list[str]:
        if not self._phase_conforme(phase):
            return []
        parser = self._parser_de.get(config_id, "auto")
        parse = self._ingerer(parser, phase)
        if parse is None:
            return []
        ids: list[str] = []
        for r in q.reference_anchors:
            i = parse.resolve(r.doc, r.page, r.headings)
            if i is None:
                self._non_resolus.setdefault((parser, phase), set()).add(q.id)
            else:
                ids.append(i)
        return ids

    def textes(self, config_id: str, phase: Phase, q: Question) -> list[str]:
        """Texte des Ancrages de référence résolus, celui que reçoivent les Juges
        (`reference_texts`) ; liste vide dans les mêmes cas que `__call__`."""
        ids = self(config_id, phase, q)
        parse = self._corpus.get((self._parser_de.get(config_id, "auto"), phase))
        return [parse.anchor_text(i) for i in ids] if parse is not None else []

    def alertes(self) -> list[str]:
        """Alertes à reprendre dans le Rapport, y compris les Ancrages non résolus."""
        lignes = list(self._alertes)
        for (parser, phase), questions in sorted(self._non_resolus.items()):
            lignes.append(
                f"{len(questions)} Question(s) avec au moins un Ancrage de référence non résolu "
                f"sur le Corpus ({parser}, {phase}) : métriques calculées sur les seuls Ancrages "
                f"résolus, Question écartée si aucun ne l'est ({', '.join(sorted(questions)[:5])}"
                f"{'…' if len(questions) > 5 else ''})."
            )
        return lignes


def resolveur_de(
    experience: ResolvedExperiment, wl_home: Path, inputs: Mapping[str, Any] | None = None
) -> ResolveurCorpus:
    """`inputs` : empreintes du manifeste ; `None` (tests) ne compare pas les empreintes."""
    return ResolveurCorpus(experience, wl_home, inputs)
