"""Section « Coûts, énergie et latence » de `report.md` (story 4.12)."""

from collections import defaultdict
from decimal import Decimal

from wavelibrarian.report.couts import POSTES_A_PART, POSTES_CONFIGURATION, Couts, LigneCout
from wavelibrarian.report.lecture import Execution
from wavelibrarian.report.scores import etiquette_palier

ENTETE_POSTES = [
    "Configuration", "Condition", "Palier", "Phase", "Poste", "€ réel", "€ sans cache",
    "dont possession (€)", "kWh mesurés", "kWh estimés", "CO2e mesuré (g)", "CO2e estimé (g)",
    "Appels", "€ fictif (fake)",
]  # fmt: skip
ENTETE_LATENCE = [
    "Configuration", "Condition", "Palier", "Phase", "n", "p50 (s)", "p95 (s)", "Débit (Q/min)",
    "€/requête", "€/1 000 requêtes",
]  # fmt: skip


def _nb(x: float, decimales: int = 2) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


def _eur(x: Decimal, decimales: int = 4) -> str:
    return _nb(float(x), decimales)


def _opt(x: float | None, decimales: int) -> str:
    return "n/a" if x is None else _nb(x, decimales)


def _table(entete: list[str], lignes: list[list[str]]) -> list[str]:
    sortie = ["| " + " | ".join(entete) + " |", "| " + " | ".join("---" for _ in entete) + " |"]
    sortie += ["| " + " | ".join(ligne) + " |" for ligne in lignes]
    return [*sortie, ""]


def _ligne_poste(ligne: LigneCout) -> list[str]:
    config, condition, tier, phase, post = ligne.cle
    return [
        f"`{config}`", condition, etiquette_palier(tier), phase, post, _eur(ligne.real),
        _eur(ligne.uncached), _eur(ligne.possession), f"{ligne.kwh_measured:.6f}",
        f"{ligne.kwh_estimated:.6f}", _nb(float(ligne.co2e_measured_g), 3),
        _nb(float(ligne.co2e_estimated_g), 3), str(ligne.n_calls), _eur(ligne.fake),
    ]  # fmt: skip


def _parametres(ex: Execution, couts: Couts) -> list[str]:
    c = ex.experience.costs
    devises = ", ".join(
        f"1 {d} = {_nb(float(t), 4)} EUR" for d, t in sorted(c.fx.rates_to_eur.items())
    )
    hors = sum((x.api_real for x in couts.lignes if x.cle[4] in POSTES_A_PART), Decimal(0))
    o = c.owned_costs
    lignes = [
        f"- Taux de change daté du {c.fx.date.isoformat()} ({c.fx.source}) : {devises}.",
        f"- Coût de possession du calcul local (date {o.date.isoformat()}) : "
        f"{_eur(o.kwh_price_eur)} €/kWh, {o.hardware_name} à {_eur(o.hardware_price_eur, 0)} € "
        f"sur {o.hardware_life_hours} h. Le stockage de l'index n'est pas compté (sa taille "
        "n'est pas dans les fichiers de l'Exécution).",
        f"- Intensité carbone ({c.carbon.region}, {c.carbon.date.isoformat()}) : "
        f"{_nb(float(c.carbon.gco2e_per_kwh), 1)} g CO2e/kWh.",
        f"- **Somme des `wl.cost` des spans d'un fournisseur réel (hors `fake`), en euros : "
        f"{_eur(couts.total_api())} €** "
        f"(possession en plus : {_eur(couts.total_possession())} €), dont {_eur(hors)} € hors "
        "Configuration (`judging`, `evalset`).",
        f"- Coûts **fictifs** (spans `fake` et possession d'une énergie du compteur factice, "
        f"jamais dépensés, colonne `cost_eur_fake`) : {_eur(couts.total_fake())} €, hors "
        "`cost_eur_real`."
        + (
            " Faux LLM pur : `cost_eur_real` vaut 0 ; les fronts de Pareto, le coût par requête "
            "et le point mort se calculent sur `cost_eur_fake`."
            if couts.faux_llm_pur
            else ""
        ),
        "- **Avertissement** : les kWh `measured` (compteur matériel) et `estimated` (modèle "
        "d'estimation) restent dans deux colonnes, jamais additionnées : leurs périmètres "
        "ne se comparent pas. Le CO2e suit la même séparation.",
    ]
    source = ex.manifeste.get("rejudged_from")
    if source:  # rejugement (story 9.6) : seule la phase de jugement a été refaite
        lignes.append(
            f"- **Rejugement** : coûts, énergie et latence de génération (tous les Postes hors "
            f"`judging`) copiés de `{source}` ; le Poste `judging` est celui du rejugement."
        )
    if any(x.architecture == "cag" for x in ex.experience.configurations):
        lignes.append(
            "- Le préchargement du contexte de `cag` est facturé à chaque Exécution au Poste "
            "`indexing` (hit d'index et reprise compris) : il ne s'amortit pas comme un index."
        )
    if couts.sources_energie:
        detail = ", ".join(f"`{k}` ({n})" for k, n in sorted(couts.sources_energie.items()))
        lignes.append(f"- Source de l'énergie (`wl.energy_source`, spans avec énergie) : {detail}.")
    if any(ligne.kwh_measured for ligne in couts.lignes):
        lignes.append(
            "- Les kWh `measured` viennent d'un compteur CPU ou GPU ; codecarbon y ajoute la part "
            "RAM, estimée par formule (aucun compteur DRAM lu)."
        )
    if couts.spans_sans_energie:
        lignes.append(
            f"- {couts.spans_sans_energie} span(s) locaux sans énergie connue : comptés pour 0 kWh."
        )
    if couts.valeurs_invalides:
        lignes.append(
            f"- **Anomalie** : {couts.valeurs_invalides} coût(s) illisible(s) dans `traces.jsonl`, "
            "comptés pour 0 € : la somme ci-dessus est incomplète."
        )
    return lignes


def _points_morts(couts: Couts) -> list[str]:
    sortie = [
        "### Point mort",
        "",
        "N* = (indexation_A − indexation_B) ÷ (requête_B − requête_A), pour A plus cher à "
        "l'indexation que B, en Condition standard et phase `base`. Il n'est donné que si la "
        "Qualité de A est égale ou supérieure à celle de B et si requête_A < requête_B ; sinon la "
        "raison est écrite.",
        "",
    ]
    if not couts.points_morts:
        return [*sortie, "Aucune paire où une Configuration coûte plus cher à l'indexation.", ""]
    return [
        *sortie,
        *_table(
            ["A (indexation plus chère)", "B", "Palier", "Point mort N* (requêtes)"],
            [
                [
                    f"`{p.config_a}`",
                    f"`{p.config_b}`",
                    etiquette_palier(p.tier),
                    f"{p.n_star}" if p.n_star is not None else f"aucun : {p.raison}",
                ]
                for p in couts.points_morts
            ],
        ),  # fmt: skip
    ]


def section_couts(ex: Execution, couts: Couts) -> list[str]:
    if not couts.traces_presentes:
        return ["## Coûts, énergie et latence", "", "Fichier `traces.jsonl` absent.", ""]
    cfg = [x for x in couts.lignes if x.cle[4] in POSTES_CONFIGURATION]
    a_part = [x for x in couts.lignes if x.cle[4] in POSTES_A_PART]
    totaux: dict[tuple[str, str, int | None], list[Decimal]] = defaultdict(
        lambda: [Decimal(0), Decimal(0), Decimal(0)]
    )
    for x in cfg:
        t = totaux[x.cle[:3]]
        t[0] += x.real
        t[1] += x.uncached
        t[2] += x.possession
    cles = sorted(totaux, key=lambda k: (k[0], k[1], -1 if k[2] is None else k[2]))
    lat = [
        [
            f"`{x.groupe[0]}`", x.groupe[1], etiquette_palier(x.groupe[2]), x.groupe[3], str(x.n),
            _opt(x.p50, 3), _opt(x.p95, 3), _opt(x.debit_qpm, 1),
            "n/a" if x.cout_requete is None else _eur(x.cout_requete, 6),
            "n/a" if x.cout_1000 is None else _eur(x.cout_1000, 4),
        ]
        for x in couts.latences
    ]  # fmt: skip
    source = ex.manifeste.get("rejudged_from")
    copie = f" (copiés de `{source}`)" if source else ""
    return [
        "## Coûts, énergie et latence",
        "",
        *_parametres(ex, couts),
        "",
        f"### Coût total par Configuration{copie}",
        "",
        "Indexation + mise à jour + requête, possession comprise ; `judging` et `evalset` sont "
        "hors coût d'une Configuration.",
        "",
        *_table(
            [
                "Configuration",
                "Condition",
                "Palier",
                "€ réel",
                "€ sans cache",
                "dont possession (€)",
            ],
            [
                [f"`{k[0]}`", k[1], etiquette_palier(k[2]), *(_eur(v) for v in totaux[k])]
                for k in cles
            ],
        ),
        f"### Coûts et énergie par Poste{copie}",
        "",
        *_table(ENTETE_POSTES, [_ligne_poste(x) for x in cfg]),
        "### Postes hors Configuration (`judging`, `evalset`)",
        "",
        *(_table(ENTETE_POSTES, [_ligne_poste(x) for x in a_part]) if a_part else ["Aucun.", ""]),
        f"### Latence, débit et coût par requête{copie}",
        "",
        "Latence des Réponses `ok` (somme des spans `query`, hors reprise) ; débit = Réponses ÷ "
        "durée murale de la phase query ; coût par requête = Poste `query` (appels des Réponses "
        "en échec compris) ÷ Réponses `ok`.",
        "",
        *_table(ENTETE_LATENCE, lat),
        *_points_morts(couts),
    ]
