"""Sections de `report.md` de la story 4.13 : fronts de Pareto, Paliers, Fraîcheur."""

from wavelibrarian.report.couts import Couts
from wavelibrarian.report.fraicheur import LigneFraicheur, qualite_par_palier
from wavelibrarian.report.fronts import (
    FRONT_REFERENCE,
    Front,
    front_de_reference,
    libelle_groupe,
)
from wavelibrarian.report.lecture import Execution
from wavelibrarian.report.scores import QUALITE, TOUS, Resultats


def _nb(x: float, decimales: int = 2) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


def _avec_ic(x: float, bas: float, haut: float) -> str:
    return f"{_nb(x)} [{_nb(bas)} ; {_nb(haut)}]"


def _table(entete: list[str], lignes: list[list[str]]) -> list[str]:
    sortie = ["| " + " | ".join(entete) + " |", "| " + " | ".join("---" for _ in entete) + " |"]
    sortie += ["| " + " | ".join(ligne) + " |" for ligne in lignes]
    return [*sortie, ""]


def section_pareto(
    res: Resultats, couts: Couts | None, fronts: list[Front], ex: Execution
) -> list[str]:
    """Tableau de synthèse du front Qualité × coût total, à placer juste après l'en-tête."""
    titre = ["## Configurations non dominées (Qualité × coût total)", ""]
    if couts is None or not couts.traces_presentes:
        return [
            *titre,
            "Traces absentes (`traces.jsonl`) : ni coût, ni front de coût ni front d'énergie. "
            "Le front Qualité × latence p95 reste dans `pareto.csv`.",
            "",
        ]
    front = front_de_reference(fronts)
    if front is None:
        return [*titre, "Aucune Réponse notée en Condition standard : aucun front.", ""]
    qualite = {
        s.groupe[0]: s
        for s in res.scores
        if s.critere == QUALITE
        and s.question_type == TOUS
        and s.groupe[1:] == (front.condition, front.tier, "base")
    }
    p95 = {
        lat.groupe[0]: lat.p95
        for lat in couts.latences
        if lat.groupe[1:] == (front.condition, front.tier, "base")
    }
    lignes: list[list[str]] = []
    for p in front.points:
        s = qualite[p.config_id]
        latence = p95.get(p.config_id)
        lignes.append(
            [
                f"`{p.config_id}`",
                _avec_ic(s.value, s.ci_low, s.ci_high),
                f"{_nb(p.cout, 4)} €",
                "n/a" if latence is None else _nb(latence, 3),
            ]
        )
    n = len(ex.experience.configurations)
    return [
        *titre,
        f"Front `{front.nom}` ({libelle_groupe(front)}) : {len(front.points)} Configuration(s) "
        f"non dominée(s) sur {n}. Une Configuration est dominée si une autre a une Qualité au "
        "moins égale pour un coût au plus égal, l'un des deux strictement. Aucun score global ni "
        "pondération entre Critères : le front garde seulement les compromis.",
        "",
        *_table(["config_id", "Qualité [IC 95 %]", "Coût total (€)", "Latence p95 (s)"], lignes),
        "Qualité de la phase `base` ; coût total = indexation + mise à jour + requête, phases "
        "cumulées, Coût de possession compris, `judging` et `evalset` exclus. Les fronts Qualité "
        "× énergie (kWh mesurés et estimés à part), Qualité × latence p95 et (taux d'un Critère, "
        "coût total) par Critère, ainsi que ceux des autres Conditions et Paliers "
        f"(`{FRONT_REFERENCE}@perfect_context`, `…@palier-N`), sont dans `pareto.csv` (`front, "
        "config_id, x, y`). Les Qualités ne portent pas toutes sur les mêmes Questions si une "
        "Exécution est partielle.",
        "",
    ]


def section_paliers(res: Resultats, couts: Couts | None) -> list[str]:
    """Qualité, coût total et latence p95 par Palier (phase `base`) ; vide sans Palier."""
    qualite = qualite_par_palier(res)
    if not qualite:
        return []
    p95 = {lat.groupe: lat.p95 for lat in (couts.latences if couts else [])}
    lignes: list[list[str]] = []
    for (config, condition, tier), (v, bas, haut, n) in sorted(qualite.items()):
        cout = (
            "n/a"
            if couts is None or not couts.traces_presentes
            else _nb(float(couts.total_configuration(config, condition, tier)), 4)
        )
        latence = p95.get((config, condition, tier, "base"))
        lignes.append(
            [
                f"`{config}`",
                condition,
                str(tier),
                str(n),
                _avec_ic(v, bas, haut),
                cout,
                "n/a" if latence is None else _nb(latence, 3),
            ]
        )
    return [
        "## Résultats par Palier",
        "",
        "Qualité de la phase `base` sur le sous-corpus de chaque Palier (FR-54), avec le coût "
        "total de la Configuration (€, phases cumulées) et la latence p95 (s). Un Palier ne se "
        "compare qu'à lui-même : les Paliers ne sont jamais mêlés dans un score. Une Citation est "
        "toujours tirée du contexte de l'index du Palier (le Generator retire toute étiquette "
        "absente du contexte et la compte dans `invalid_citations`), donc `citation_correctness` "
        "se lit déjà sur le sous-corpus du Palier.",
        "",
        *_table(
            [
                "Configuration",
                "Condition",
                "Palier",
                "n",
                "Qualité [IC 95 %]",
                "Coût total (€)",
                "Latence p95 (s)",
            ],
            lignes,
        ),  # fmt: skip
    ]


def section_fraicheur(ex: Execution, lignes: list[LigneFraicheur]) -> list[str]:
    """Fraîcheur par (Configuration, Condition, Palier) ; une phrase si aucun Scénario."""
    titre = ["## Fraîcheur", ""]
    if not ex.experience.scenario:
        return [
            *titre,
            "Aucun Scénario de mise à jour dans cette Expérience : pas de Fraîcheur.",
            "",
        ]
    if not lignes:
        return [*titre, "Aucune Réponse `after_update` à une Question de Scénario.", ""]
    corps = []
    for x in lignes:
        config, condition, tier = x.cle
        corps.append(
            [
                f"`{config}`",
                condition,
                "all" if tier is None else str(tier),
                str(x.n),
                "n/a"
                if x.taux is None or x.ci_low is None or x.ci_high is None
                else _avec_ic(x.taux, x.ci_low, x.ci_high),
                str(x.inapplicables),
                str(x.echecs),
                str(x.non_jugees),
            ]
        )
    return [
        *titre,
        "Fraîcheur = part des Questions à `scenario_target` correctes (Qualité) en phase "
        "`after_update`, avec IC bootstrap. Les Réponses `inapplicable` (Ancrage créé ou supprimé "
        "par le Scénario, absent du Corpus de la phase en contexte parfait) sont **retirées du "
        "dénominateur** et comptées à part ; `error` et `budget_exceeded` ne sont pas notées non "
        "plus. Les Questions contaminées sont exclues.",
        "",
        *_table(
            [
                "Configuration",
                "Condition",
                "Palier",
                "n",
                "Fraîcheur [IC 95 %]",
                "inapplicable",
                "error / budget_exceeded",
                "non jugées",
            ],
            corps,
        ),  # fmt: skip
    ]
