"""Génération du Rapport `report/` d'une Exécution (story 4.11, FR-40, contracts.md §5 et §7).

`generer_rapport` lit les seuls fichiers de l'Exécution et écrit `report.md`, `scores.csv`,
`retrieval.csv` et `pairs.csv`. Il ne dépend pas du runner (AD-1) : `cli.py` l'appelle après
`wl run` (y compris sur une Exécution arrêtée au plafond) ou par `wl rapport <run_id>`.
"""

import csv
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from wavelibrarian.config.panel import excluded_judges
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.report.ancrages import Resolveur, resolveur_de
from wavelibrarian.report.lecture import CleGroupe, Execution, charger
from wavelibrarian.report.scores import (
    CRITERES,
    QUALITE,
    TOUS,
    LigneScore,
    Resultats,
    etiquette_palier,
    evaluer,
)
from wavelibrarian.report.wiki import section_fidelite

log = logging.getLogger(__name__)

ENTETE_SCORES = [
    "config_id", "condition", "tier", "phase", "question_type", "criterion",
    "value", "ci_low", "ci_high", "n",
]  # fmt: skip
ENTETE_RECHERCHE = [
    "config_id", "condition", "tier", "phase", "question_type", "metric", "k",
    "value", "ci_low", "ci_high", "n", "method",
]  # fmt: skip
# Les sept colonnes du contrat, puis le groupe de la comparaison (condition, tier, phase) : une
# paire ne se compare qu'à l'intérieur d'un groupe (§7).
ENTETE_PAIRES = [
    "config_a", "config_b", "metric", "diff", "p_value", "test", "n_common",
    "condition", "tier", "phase",
]  # fmt: skip
NOM_CRITERE = {
    QUALITE: "Qualité",
    "correctness": "correctness",
    "completeness": "completeness",
    "faithfulness": "faithfulness",
    "citation_correctness": "citation_correctness",
    "abstention_correctness": "abstention_correctness",
}


def _nb(x: float, decimales: int = 2) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


def _avec_ic(x: float, bas: float, haut: float) -> str:
    return f"{_nb(x)} [{_nb(bas)} ; {_nb(haut)}]"


def _flottant(x: float | None) -> str:
    return "" if x is None else f"{x:.6f}"


def _ordre(g: CleGroupe) -> tuple[str, str, int, str]:
    return (g[0], g[1], -1 if g[2] is None else g[2], g[3])


def _ecrire_csv(chemin: Path, entete: list[str], lignes: list[list[Any]]) -> None:
    with chemin.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(entete)
        w.writerows(lignes)


def ecrire_csv(dossier: Path, res: Resultats) -> None:
    """`scores.csv`, `retrieval.csv` et `pairs.csv`. Aucune colonne de score global."""
    _ecrire_csv(
        dossier / "scores.csv",
        ENTETE_SCORES,
        [
            [
                s.groupe[0], s.groupe[1], etiquette_palier(s.groupe[2]), s.groupe[3],
                s.question_type, s.critere, _flottant(s.value), _flottant(s.ci_low),
                _flottant(s.ci_high), s.n,
            ]
            for s in res.scores
        ],
    )  # fmt: skip
    _ecrire_csv(
        dossier / "retrieval.csv",
        ENTETE_RECHERCHE,
        [
            [
                r.groupe[0], r.groupe[1], etiquette_palier(r.groupe[2]), r.groupe[3],
                r.question_type, r.metric, r.k, _flottant(r.value), _flottant(r.ci_low),
                _flottant(r.ci_high), r.n, r.method,
            ]
            for r in res.recherche
        ],
    )  # fmt: skip
    _ecrire_csv(
        dossier / "pairs.csv",
        ENTETE_PAIRES,
        [
            [
                p.config_a, p.config_b, p.metric, _flottant(p.diff), _flottant(p.p_value),
                p.test, p.n_common, p.condition, etiquette_palier(p.tier), p.phase,
            ]
            for p in res.paires
        ],
    )  # fmt: skip


# --- Markdown ----------------------------------------------------------------------------------


def _table(entete: list[str], lignes: list[list[str]]) -> list[str]:
    sortie = ["| " + " | ".join(entete) + " |", "| " + " | ".join("---" for _ in entete) + " |"]
    sortie += ["| " + " | ".join(ligne) + " |" for ligne in lignes]
    return [*sortie, ""]


def _bandeau(ex: Execution) -> list[str]:
    statut = ex.manifeste.get("status", "inconnu")
    if statut == "completed":
        return []
    if statut == "budget_exceeded":
        return [
            "> **Exécution arrêtée au plafond de dépense : résultats partiels.** Les Questions "
            "restantes sont en `budget_exceeded` ; `wl run --reprendre` les pose.",
            "",
        ]
    return [f"> **Exécution non terminée (statut `{statut}`) : résultats partiels.**", ""]


def _entete(ex: Execution) -> list[str]:
    e = ex.experience
    m = ex.manifeste
    run_id = m.get("run_id", ex.run_dir.name)
    modeles = ", ".join(f"`{x}`" for x in m.get("models", ())) or "aucun"
    lignes = [
        f"# Rapport : {e.experiment_id}",
        "",
        *_bandeau(ex),
        f"Exécution `{run_id}`, statut `{m.get('status', 'inconnu')}`.",
        "",
        "## Expérience",
        "",
        "- Expérience résolue : [experiment.resolved.yaml](../experiment.resolved.yaml), "
        f"empreinte `{ex.empreinte or 'inconnue'}`.",
        f"- Profil d'exécution : `{e.profile}`.",
        f"- Partie utilisée : `{e.split}` (graine {e.seed}).",
        f"- Modèles gelés au : {e.models_frozen_at.isoformat()} (Catalogue du "
        f"{e.catalog_date.isoformat()}).",
        f"- Modèles : {modeles}.",
        f"- Configurations : {', '.join(f'`{c.id}`' for c in e.configurations)}.",
        f"- Conditions : {', '.join(f'`{c}`' for c in e.conditions)}.",
        "",
    ]
    return lignes


def _corpus(ex: Execution) -> list[str]:
    p = ex.profil_corpus
    if not p:
        return ["## Profil de corpus", "", "Profil de corpus absent (`corpus_profile.json`).", ""]
    champs = [
        ("Corpus", p.get("corpus_id")),
        ("Empreinte", p.get("fingerprint")),
        ("Parser", p.get("parser")),
        ("Tokenizer", p.get("tokenizer")),
        ("Documents", p.get("n_documents")),
        ("Tokens", p.get("n_tokens")),
        ("Langue dominante", p.get("dominant_lang")),
        ("Formats", p.get("formats")),
        ("Volatilité", p.get("volatility")),
    ]
    return [
        "## Profil de corpus",
        "",
        *_table(["Champ", "Valeur"], [[k, f"{v}"] for k, v in champs if v is not None]),
    ]


def _juges(ex: Execution) -> list[str]:
    config_de = {a.answer_id: a.config_id for a in ex.reponses.values()}
    admissibles: dict[str, set[str]] = defaultdict(set)
    egalites: dict[str, int] = defaultdict(int)
    for (aid, _), v in ex.panel.items():
        config = config_de.get(aid)
        if config is None:
            continue
        admissibles[config].update(v.judges)
        egalites[config] += int(v.tie)
    exclus: list[str] = []
    note = ""
    chemin = ex.experience.judges.excluded_from
    if chemin:
        try:
            exclus = sorted(excluded_judges(Path(chemin)))
        except ConfigError as erreur:
            note = f" (calibration illisible : {erreur.message})"
    lignes = [
        [
            f"`{c.id}`",
            ", ".join(f"`{j}`" for j in sorted(admissibles[c.id])) or "aucun",
            str(egalites[c.id]),
        ]
        for c in ex.experience.configurations
    ]
    return [
        "## Juges",
        "",
        *_table(["Configuration", "Panel admissible", "Égalités"], lignes),
        "Juges exclus par la calibration : "
        + (", ".join(f"`{j}`" for j in exclus) if exclus else "aucun")
        + f"{note}.",
        "",
    ]


def _inapplicables(ex: Execution) -> list[str]:
    if not ex.inapplicables:
        return ["## Configurations inapplicables", "", "Aucune.", ""]
    lignes = [
        [f"`{cle}`", f"`{v.get('architecture', '')}`", str(v.get("reason", ""))]
        for cle, v in sorted(ex.inapplicables.items())
    ]
    return [
        "## Configurations inapplicables",
        "",
        *_table(["Configuration", "Architecture", "Raison"], lignes),
    ]


def _etiquette(g: CleGroupe) -> list[str]:
    return [f"`{g[0]}`", etiquette_palier(g[2]), g[3]]


def _table_scores(res: Resultats, condition: str, titre: str, intro: str) -> list[str]:
    groupes = sorted((g for g in res.comptes if g[1] == condition), key=_ordre)
    if not groupes:
        return []
    par: dict[tuple[CleGroupe, str], LigneScore] = {
        (s.groupe, s.critere): s for s in res.scores if s.question_type == TOUS
    }
    colonnes = (QUALITE, *CRITERES)
    lignes: list[list[str]] = []
    for g in groupes:
        cellules = [
            _avec_ic(par[(g, c)].value, par[(g, c)].ci_low, par[(g, c)].ci_high)
            if (g, c) in par
            else "n/a"
            for c in colonnes
        ]
        lignes.append([*_etiquette(g), str(res.comptes[g].ok), *cellules])
    return [
        f"## {titre}",
        "",
        intro,
        "",
        *_table(
            ["Configuration", "Palier", "Phase", "n", *(NOM_CRITERE[c] for c in colonnes)], lignes
        ),
    ]


def _scores_par_type(res: Resultats) -> list[str]:
    lignes = [
        [*_etiquette(s.groupe), s.question_type, str(s.n), _avec_ic(s.value, s.ci_low, s.ci_high)]
        for s in sorted(res.scores, key=lambda s: (_ordre(s.groupe), s.question_type))
        if s.critere == QUALITE and s.question_type != TOUS and s.groupe[1] == "standard"
    ]
    if not lignes:
        return []
    return [
        "## Qualité par Type de question",
        "",
        *_table(["Configuration", "Palier", "Phase", "Type", "n", "Qualité"], lignes),
        "Les taux par Critère et par Type sont dans `scores.csv`.",
        "",
    ]


def _contaminees(ex: Execution, res: Resultats) -> list[str]:
    n = sum(c.contaminees for c in res.comptes.values())
    lignes = [
        [*_etiquette(s.groupe), s.groupe[1], str(s.n), _avec_ic(s.value, s.ci_low, s.ci_high)]
        for s in sorted(res.contaminees, key=lambda s: _ordre(s.groupe))
    ]
    corps = (
        ["Aucune Réponse à une Question contaminée.", ""]
        if not n
        else _table(["Configuration", "Palier", "Phase", "Condition", "n", "Qualité"], lignes)
    )
    return [
        "## Questions contaminées",
        "",
        "Les Questions contaminées (FR-12) sont exclues de tous les scores ci-dessus et de "
        "`scores.csv`, `retrieval.csv` et `pairs.csv` ; leur Qualité figure ici seulement.",
        "",
        *corps,
    ]


def _recherche(res: Resultats) -> list[str]:
    par = {
        (r.groupe, r.method, r.metric): r
        for r in res.recherche
        if r.question_type == TOUS and r.groupe[1] == "standard"
    }
    cles = sorted({(g, m) for g, m, _ in par}, key=lambda k: (_ordre(k[0]), k[1]))
    lignes: list[list[str]] = []
    for g, methode in cles:
        r0 = par[(g, methode, "recall")]
        lignes.append(
            [
                *_etiquette(g),
                g[1],
                methode,
                str(r0.n),
                *(
                    _avec_ic(r.value, r.ci_low, r.ci_high)
                    for r in (par[(g, methode, m)] for m in ("recall", "mrr", "ndcg"))
                ),
            ]
        )
    corps = (
        _table(
            [
                "Configuration",
                "Palier",
                "Phase",
                "Condition",
                "Méthode",
                "n",
                "rappel@5",
                "MRR",
                "nDCG@5",
            ],
            lignes,
        )  # fmt: skip
        if lignes
        else ["Aucune métrique de recherche.", ""]
    )
    return [
        "## Recherche",
        "",
        "Un Passage est pertinent si ses Ancrages recoupent ceux de référence ; la méthode "
        "reprend `retrieval_method`. La Baseline `no_context` n'a pas de recherche. Détail par "
        "Type : `retrieval.csv`.",
        "",
        *corps,
    ]


def _paires(res: Resultats) -> list[str]:
    qualite = [p for p in res.paires if p.metric == QUALITE]
    lignes = [
        [
            f"`{p.config_a}`",
            f"`{p.config_b}`",
            p.condition,
            etiquette_palier(p.tier),
            p.phase,
            "aucune Question commune" if p.diff is None else _nb(p.diff, 3),
            "n/a" if p.p_value is None else _nb(p.p_value, 4),
            str(p.n_common),
        ]
        for p in qualite
    ]
    corps = (
        _table(
            [
                "A",
                "B",
                "Condition",
                "Palier",
                "Phase",
                "Différence de Qualité (A − B)",
                "p-valeur (McNemar exact)",
                "n_common",
            ],
            lignes,
        )  # fmt: skip
        if lignes
        else ["Moins de deux Configurations comparables.", ""]
    )
    return [
        "## Comparaisons appariées",
        "",
        "Chaque paire de Configurations se compare dans un même groupe (condition, palier, "
        "phase), sur les Questions communes (`n_common`) : McNemar exact pour la Qualité et les "
        "Critères, bootstrap apparié pour les métriques de recherche. Toutes les lignes sont "
        "dans `pairs.csv`.",
        "",
        *corps,
        f"**Multiplicité.** Aucune correction (Holm, Bonferroni) n'est appliquée aux "
        f"{len(res.paires)} comparaisons de `pairs.csv` : une p-valeur isolée sous 0,05 parmi "
        "plusieurs se lit avec prudence. Une paire sans Question commune n'a pas de p-valeur, "
        "donc aucune « Qualité égale » n'en est déduite.",
        "",
    ]


def _non_notees(ex: Execution, res: Resultats) -> list[str]:
    lignes = [
        [
            *_etiquette(g),
            g[1],
            str(c.ok),
            str(c.error),
            str(c.inapplicable),
            str(c.budget_exceeded),
            str(c.non_jugees),
        ]
        for g, c in sorted(res.comptes.items(), key=lambda kv: _ordre(kv[0]))
    ]
    manifeste = ex.manifeste.get("unjudged")
    return [
        "## Réponses non notées",
        "",
        "Seules les Réponses `ok` sont notées. `non jugées` : Réponses `ok` auxquelles manque un "
        "verdict de Panel (Juge en échec), reprises par `wl run --reprendre`."
        + (f" Le manifeste en compte {manifeste}." if manifeste else ""),
        "",
        *_table(
            [
                "Configuration",
                "Palier",
                "Phase",
                "Condition",
                "ok",
                "error",
                "inapplicable",
                "budget_exceeded",
                "non jugées",
            ],
            lignes,
        ),  # fmt: skip
    ]


def construire_markdown(ex: Execution, res: Resultats) -> str:
    sections = [
        *_entete(ex),
        *_corpus(ex),
        *_juges(ex),
        *_inapplicables(ex),
        *_table_scores(
            res,
            "standard",
            "Scores",
            "Taux de oui avec IC bootstrap à 95 % ; aucun score global. Qualité : `correctness` "
            "oui, ou `abstention_correctness` oui pour une Question `unanswerable`.",
        ),
        *_scores_par_type(res),
        *_table_scores(
            res,
            "perfect_context",
            "Contexte parfait",
            "Résultats **contexte parfait** : les Ancrages de référence sont fournis au Generator. "
            "Ils ne se comparent pas à ceux de la Condition standard.",
        ),
        *_contaminees(ex, res),
        *_recherche(res),
        *_paires(res),
        *_non_notees(ex, res),
    ]
    fidelite = section_fidelite(ex.run_dir)
    if fidelite:
        sections += [*fidelite.rstrip("\n").split("\n"), ""]
    return "\n".join(sections).rstrip("\n") + "\n"


def generer_rapport(
    run_dir: Path, *, wl_home: Path | None = None, resoudre: Resolveur | None = None
) -> Path:
    """Écrit `report/` de l'Exécution et rend son dossier. `wl_home` : cache de parsing pour
    résoudre les Ancrages de référence (défaut `WL_HOME` ou `.wl`) ; `resoudre` : résolveur
    d'Ancrages injecté (tests). `ConfigError` si l'Expérience résolue ou le Jeu sont illisibles."""
    ex = charger(run_dir)
    if resoudre is None:
        home = wl_home or Path(os.environ.get("WL_HOME") or ".wl")
        resoudre = resolveur_de(ex.experience, home)
    res = evaluer(ex, resoudre)
    sortie = run_dir / "report"
    sortie.mkdir(exist_ok=True)
    ecrire_csv(sortie, res)
    (sortie / "report.md").write_text(construire_markdown(ex, res), encoding="utf-8", newline="\n")
    return sortie
