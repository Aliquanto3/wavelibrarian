"""Fronts de Pareto du Rapport, `pareto.csv` et tableau de synthèse (story 4.13, FR-40, AD-22).

Les grandeurs viennent de 4.11 (Qualité et taux par Critère, phase `base`) et de 4.12 (coût total
d'une Configuration, phases cumulées ; latence p95 ; kWh). Un front est calculé par (Condition,
Palier) : les groupes ne se mêlent jamais. Aucun score global, aucune pondération (PRD §6).
"""

from dataclasses import dataclass
from decimal import Decimal

from wavelibrarian.report.couts import POSTES_CONFIGURATION, Couts
from wavelibrarian.report.lecture import Execution
from wavelibrarian.report.scores import CRITERES, QUALITE, TOUS, Resultats, etiquette_palier
from wavelibrarian.stats.pareto import Point, front_pareto

ENTETE_PARETO = ["front", "config_id", "x", "y"]
FRONT_REFERENCE = "qualite-cout"  # celui du tableau de synthèse et de `--exporter-front`
_LATENCE = "qualite-latence-p95"
_ENERGIE_MESUREE = "qualite-energie-mesuree"
_ENERGIE_ESTIMEE = "qualite-energie-estimee"
_ENERGIE_MIXTE = "qualite-energie-mixte"
# Décimales de `pareto.csv` ; le front est calculé sur ces valeurs arrondies, pour que le front
# relu dans le fichier (export) soit celui du Rapport. x à 9 décimales : un kWh de requête locale
# tient souvent sous 1e-6.
_DECIMALES_X = 9
_DECIMALES_Y = 6

Groupe = tuple[str, int | None]  # (condition, tier)


@dataclass(frozen=True)
class Front:
    """`nom` est la clé de `pareto.csv` ; `points` suivent l'ordre de `front_pareto` (x croissant :
    `cout` est la grandeur à minimiser, `qualite` la Qualité ou le taux, maximisé)."""

    nom: str
    condition: str
    tier: int | None
    points: tuple[Point, ...]


def _ordre(g: Groupe) -> tuple[str, int]:
    return (g[0], -1 if g[1] is None else g[1])


def _suffixe(g: Groupe, palier_max: int | None) -> str:
    """Condition standard et plus grand Palier (le Corpus complet) : pas de suffixe."""
    suffixe = "" if g[0] == "standard" else f"@{g[0]}"
    if g[1] is not None and g[1] != palier_max:
        suffixe += f"@palier-{g[1]}"
    return suffixe


def _taux(res: Resultats) -> dict[tuple[str, str, int | None, str], float]:
    """(config_id, condition, tier, critère) -> taux en phase `base`, toutes Questions."""
    return {
        (s.groupe[0], s.groupe[1], s.groupe[2], s.critere): s.value
        for s in res.scores
        if s.question_type == TOUS and s.groupe[3] == "base"
    }


def _kwh(
    couts: Couts, config: str, condition: str, tier: int | None
) -> tuple[Decimal, Decimal, Decimal]:
    """kWh (mesurés, estimés, mixtes) des Postes d'une Configuration, phases cumulées, non
    additionnés."""
    mesure = estime = mixte = Decimal(0)
    for ligne in couts.lignes:
        if ligne.cle[:3] == (config, condition, tier) and ligne.cle[4] in POSTES_CONFIGURATION:
            mesure += ligne.kwh_measured
            estime += ligne.kwh_estimated
            mixte += ligne.kwh_mixed
    return mesure, estime, mixte


def construire_fronts(ex: Execution, res: Resultats, couts: Couts | None) -> list[Front]:
    """Tous les fronts de `pareto.csv`, par groupe (Condition, Palier) : Qualité × coût, Qualité ×
    énergie (mesurée, estimée), Qualité × latence p95, un front par Critère. Sans traces (`couts`
    absent ou sans `traces.jsonl`), ni front de coût ni front d'énergie : un coût nul pour tous ne
    départagerait rien."""
    taux = _taux(res)
    groupes = {(c, t) for (_, c, t, k) in taux if k == QUALITE}
    paliers = [t for _, t in groupes if t is not None]
    palier_max = max(paliers) if paliers else None
    avec_couts = couts is not None and couts.traces_presentes
    p95 = {
        lat.groupe: lat.p95
        for lat in (couts.latences if couts is not None else [])
        if lat.p95 is not None
    }
    configs = sorted(c.id for c in ex.experience.configurations)
    fronts: list[Front] = []

    def ajouter(nom: str, g: Groupe, points: list[Point]) -> None:
        if points:
            nom_complet = nom + _suffixe(g, palier_max)
            arrondis = [
                Point(p.config_id, round(p.qualite, _DECIMALES_Y), round(p.cout, _DECIMALES_X))
                for p in points
            ]
            fronts.append(Front(nom_complet, g[0], g[1], tuple(front_pareto(arrondis))))

    for g in sorted(groupes, key=_ordre):
        condition, tier = g
        presentes = [c for c in configs if (c, condition, tier, QUALITE) in taux]
        total: dict[str, float] = {}
        if avec_couts and couts is not None:
            fictif = couts.faux_llm_pur  # Faux LLM pur : le front se calcule sur `cost_eur_fake`
            total = {
                c: float(couts.total_configuration(c, condition, tier, fictif=fictif))
                for c in presentes
            }
            ajouter(
                FRONT_REFERENCE,
                g,
                [Point(c, taux[(c, condition, tier, QUALITE)], total[c]) for c in presentes],
            )
            kwh = {c: _kwh(couts, c, condition, tier) for c in presentes}
            for nom, rang in ((_ENERGIE_MESUREE, 0), (_ENERGIE_ESTIMEE, 1), (_ENERGIE_MIXTE, 2)):
                ajouter(
                    nom,
                    g,
                    [
                        Point(c, taux[(c, condition, tier, QUALITE)], float(kwh[c][rang]))
                        for c in presentes
                        if kwh[c][rang] > 0
                    ],
                )
        ajouter(
            _LATENCE,
            g,
            [
                Point(c, taux[(c, condition, tier, QUALITE)], p)
                for c in presentes
                if (p := p95.get((c, condition, tier, "base"))) is not None
            ],
        )
        if total:
            for critere in CRITERES:
                ajouter(
                    f"critere-{critere}-cout",
                    g,
                    [
                        Point(c, taux[(c, condition, tier, critere)], total[c])
                        for c in presentes
                        if (c, condition, tier, critere) in taux
                    ],
                )
    return fronts


def lignes_pareto(fronts: list[Front]) -> list[list[str]]:
    """Lignes de `pareto.csv` : `front, config_id, x, y` (x : coût, kWh ou secondes ; y : taux)."""
    return [
        [f.nom, p.config_id, f"{p.cout:.{_DECIMALES_X}f}", f"{p.qualite:.{_DECIMALES_Y}f}"]
        for f in fronts
        for p in f.points
    ]


def front_de_reference(fronts: list[Front]) -> Front | None:
    """`qualite-cout` du groupe (standard, plus grand Palier) : celui du tableau de synthèse et de
    l'export. Les autres Conditions et Paliers portent un suffixe (`@perfect_context`,
    `@palier-5`)."""
    return next((f for f in fronts if f.nom == FRONT_REFERENCE), None)


def libelle_groupe(f: Front) -> str:
    return f"{f.condition}, palier {etiquette_palier(f.tier)}"
