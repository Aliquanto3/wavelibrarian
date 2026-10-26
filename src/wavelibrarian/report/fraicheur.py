"""Fraîcheur et résultats par Palier du Rapport (story 4.13, FR-53, FR-54, contracts.md §7).

Fraîcheur = parmi les Questions à `scenario_target`, part des Questions correctes (Qualité) en phase
`after_update`. Une Réponse `inapplicable` (Ancrage créé ou supprimé par le Scénario, absent du
Corpus de la phase en contexte parfait) sort du dénominateur et est comptée à part ; `error` et
`budget_exceeded` aussi (seules les Réponses `ok` sont notées, comme partout dans le Rapport). Les
Questions contaminées (FR-12) sont exclues, comme des scores principaux.
"""

from collections import defaultdict
from dataclasses import dataclass

from wavelibrarian.report.lecture import Execution
from wavelibrarian.report.scores import (
    QUALITE,
    TOUS,
    Resultats,
    etiquette_palier,
    qualite,
    verdicts_oui_non,
)
from wavelibrarian.stats.bootstrap import bootstrap_ci, graine_derivee

CleFraicheur = tuple[str, str, int | None]  # (config_id, condition, tier)


@dataclass(frozen=True)
class LigneFraicheur:
    """`n` : Réponses `ok` notées (dénominateur) ; `taux` et IC `None` si `n` vaut 0."""

    cle: CleFraicheur
    n: int
    correctes: int
    taux: float | None
    ci_low: float | None
    ci_high: float | None
    inapplicables: int
    echecs: int  # `error` et `budget_exceeded`
    non_jugees: int  # `ok` sans verdict de Qualité


def _ordre(c: CleFraicheur) -> tuple[str, str, int]:
    return (c[0], c[1], -1 if c[2] is None else c[2])


def calculer_fraicheur(ex: Execution) -> list[LigneFraicheur]:
    """Une ligne par (Configuration, Condition, Palier) ayant une Réponse `after_update` à une
    Question de Scénario ; liste vide sans Scénario ou sans Question liée."""
    par_cle: dict[CleFraicheur, list[bool | None]] = defaultdict(list)
    inapplicables: dict[CleFraicheur, int] = defaultdict(int)
    echecs: dict[CleFraicheur, int] = defaultdict(int)
    for a in sorted(ex.reponses.values(), key=lambda r: r.answer_id):
        q = ex.jeu.get(a.question_id)
        if a.phase != "after_update" or q is None or q.scenario_target is None:
            continue
        if q.contaminated_by:
            continue
        cle = (a.config_id, a.condition, a.tier)
        if a.status == "ok":
            par_cle[cle].append(qualite(q, verdicts_oui_non(ex, a.answer_id)))
        elif a.status == "inapplicable":
            inapplicables[cle] += 1
        else:
            echecs[cle] += 1
    s = ex.experience.stats
    lignes: list[LigneFraicheur] = []
    for cle in sorted({*par_cle, *inapplicables, *echecs}, key=_ordre):
        notees = [float(v) for v in par_cle.get(cle, []) if v is not None]
        ic = bootstrap_ci(
            notees,
            seed=graine_derivee(
                ex.experience.seed, cle[0], cle[1], etiquette_palier(cle[2]), "fraicheur"
            ),
            n_resamples=s.resamples,
            confidence=s.confidence,
        )
        lignes.append(
            LigneFraicheur(
                cle,
                len(notees),
                int(sum(notees)),
                None if ic is None else ic.mean,
                None if ic is None else ic.low,
                None if ic is None else ic.high,
                inapplicables.get(cle, 0),
                echecs.get(cle, 0),
                len(par_cle.get(cle, [])) - len(notees),
            )
        )
    return lignes


def qualite_par_palier(
    res: Resultats,
) -> dict[tuple[str, str, int], tuple[float, float, float, int]]:
    """(config_id, condition, Palier) -> (Qualité, IC bas, IC haut, n), phase `base`, Paliers
    seulement (une Exécution sans Palier n'a pas cette section)."""
    return {
        (s.groupe[0], s.groupe[1], s.groupe[2]): (s.value, s.ci_low, s.ci_high, s.n)
        for s in res.scores
        if s.critere == QUALITE
        and s.question_type == TOUS
        and s.groupe[3] == "base"
        and s.groupe[2] is not None
    }
