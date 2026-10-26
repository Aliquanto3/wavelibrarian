"""Grandeurs de Qualité, de recherche et d'appariement du Rapport (contracts.md §7, AD-22).

Une seule définition de chaque grandeur, calculée des seuls fichiers de l'Exécution, par
(config_id, condition, tier, phase). Les Questions contaminées (FR-12) sont exclues des scores
principaux et comptées à part. Seules les Réponses `ok` sont notées : `error`, `inapplicable` et
`budget_exceeded` sont comptées, jamais jugées. Chaque IC et chaque test reçoit une graine dérivée
de la graine de l'Expérience (AD-20, `graine_derivee`).
"""

import itertools
from collections import defaultdict
from dataclasses import dataclass, field

from wavelibrarian.core.types import NA, Answer, Question, oui_non
from wavelibrarian.report.ancrages import Resolveur
from wavelibrarian.report.lecture import CleGroupe, Execution, groupe_de
from wavelibrarian.scoring.retrieval import K_PAR_DEFAUT, retrieval_metrics
from wavelibrarian.stats.bootstrap import bootstrap_ci, compare_continu, graine_derivee
from wavelibrarian.stats.mcnemar import compare as mcnemar_compare

CRITERES = (
    "correctness",
    "completeness",
    "faithfulness",
    "citation_correctness",
    "abstention_correctness",
)
QUALITE = "quality"  # Qualité (contracts §7), distincte des Critères
TOUS = "all"  # valeur de `question_type` pour toutes les Questions
METRIQUES_RECHERCHE = ("recall", "mrr", "ndcg")

Vecteurs = dict[str, dict[str, float]]  # métrique -> {question_id: valeur}
CleApparie = tuple[str, int | None, str]  # (condition, tier, phase)


def etiquette_palier(tier: int | None) -> str:
    return "all" if tier is None else str(tier)


def _ordre(g: CleGroupe) -> tuple[str, str, int, str]:
    return (g[0], g[1], -1 if g[2] is None else g[2], g[3])


@dataclass(frozen=True)
class LigneScore:
    groupe: CleGroupe
    question_type: str
    critere: str
    value: float
    ci_low: float
    ci_high: float
    n: int  # verdicts `yes` ou `no` (n effectif du taux)
    n_na: int = 0  # verdicts `na` (sans objet), hors du taux (story 9.3)


@dataclass(frozen=True)
class LigneRecherche:
    groupe: CleGroupe
    question_type: str
    metric: str
    k: int
    value: float
    ci_low: float
    ci_high: float
    n: int
    method: str


@dataclass(frozen=True)
class LignePaire:
    """`diff` et `p_value` sont `None` sans Question commune (`n_common` = 0)."""

    config_a: str
    config_b: str
    metric: str
    diff: float | None
    p_value: float | None
    test: str
    n_common: int
    condition: str
    tier: int | None
    phase: str


@dataclass
class Comptes:
    """Réponses d'un groupe par statut ; `non_jugees` : Réponses `ok` auxquelles manque au moins
    un verdict (Critère sans verdict de Panel, `unjudged` du manifeste)."""

    ok: int = 0
    error: int = 0
    inapplicable: int = 0
    budget_exceeded: int = 0
    contaminees: int = 0
    non_jugees: int = 0


@dataclass
class Resultats:
    comptes: dict[CleGroupe, Comptes] = field(default_factory=dict)
    scores: list[LigneScore] = field(default_factory=list)
    contaminees: list[LigneScore] = field(default_factory=list)  # Qualité à part (FR-12)
    recherche: list[LigneRecherche] = field(default_factory=list)
    paires: list[LignePaire] = field(default_factory=list)
    # Verdicts `na` d'un (groupe, Critère) sans aucun `yes` ni `no` : pas de ligne de score.
    na_seuls: dict[tuple[CleGroupe, str], int] = field(default_factory=dict)
    alertes_recherche: list[str] = field(default_factory=list)  # Ancrages, Corpus modifié


def qualite(q: Question, verdicts: dict[str, bool]) -> bool | None:
    """Qualité d'une Réponse : `correctness` oui, ou `abstention_correctness` oui pour une
    Question `unanswerable` (contracts §7) ; `None` sans verdict."""
    return verdicts.get("abstention_correctness" if q.type == "unanswerable" else "correctness")


def verdicts_oui_non(ex: Execution, answer_id: str) -> dict[str, bool]:
    """Verdicts de panel d'une Réponse en booléens ; un `na` est absent (hors des taux et des
    comparaisons appariées, story 9.3)."""
    sortie: dict[str, bool] = {}
    for c, v in ex.verdicts_par_reponse.get(answer_id, {}).items():
        oui = oui_non(v.verdict)
        if oui is not None:
            sortie[c] = oui
    return sortie


def _nombre_na(ex: Execution, a: Answer, critere: str) -> int:
    v = ex.verdicts_par_reponse.get(a.answer_id, {}).get(critere)
    return int(v is not None and v.verdict == NA)


def _verdicts(ex: Execution, a: Answer) -> dict[str, bool]:
    return verdicts_oui_non(ex, a.answer_id)


def _graine(ex: Execution, g: CleGroupe, *cles: str) -> int:
    return graine_derivee(ex.experience.seed, g[0], g[1], etiquette_palier(g[2]), g[3], *cles)


def _scores_groupe(
    ex: Execution,
    g: CleGroupe,
    reponses: list[tuple[Answer, Question]],
    *,
    par_type: bool,
    na_seuls: dict[tuple[CleGroupe, str], int] | None = None,
) -> list[LigneScore]:
    """Qualité et taux de chaque Critère, par Type de question (si `par_type`) et pour tous. Un
    verdict `na` sort du taux et se compte dans `n_na` ; `na_seuls` reçoit le nombre de `na` d'un
    Critère sans aucun `yes` ni `no` (tous Types)."""
    types = sorted({q.type for _, q in reponses}) if par_type else []
    s = ex.experience.stats
    lignes: list[LigneScore] = []
    for critere in (QUALITE, *CRITERES):
        for type_ in (*types, TOUS):
            valeurs: list[float] = []
            n_na = 0
            for a, q in reponses:
                if type_ not in (TOUS, q.type):
                    continue
                v = _verdicts(ex, a)
                oui = qualite(q, v) if critere == QUALITE else v.get(critere)
                if oui is not None:
                    valeurs.append(float(oui))
                elif critere != QUALITE:
                    n_na += _nombre_na(ex, a, critere)
            ic = bootstrap_ci(
                valeurs,
                seed=_graine(ex, g, type_, critere),
                n_resamples=s.resamples,
                confidence=s.confidence,
            )
            if ic is not None:
                lignes.append(LigneScore(g, type_, critere, ic.mean, ic.low, ic.high, ic.n, n_na))
            elif n_na and type_ == TOUS and na_seuls is not None:
                na_seuls[(g, critere)] = n_na
    return lignes


def _metriques_reponse(a: Answer, q: Question, resoudre: Resolveur) -> dict[str, float] | None:
    """rappel@k, MRR et nDCG@k d'une Réponse ; `None` sans métrique (méthode `none`, Question
    sans Ancrage de référence)."""
    if a.retrieval_method == "none":
        return None
    ancres = resoudre(a.config_id, a.phase, q)
    s = retrieval_metrics(a.retrieved, ancres, a.retrieval_method, K_PAR_DEFAUT)
    if s.recall is None or s.mrr is None or s.ndcg is None:
        return None
    return {"recall": s.recall, "mrr": s.mrr, "ndcg": s.ndcg}


def _recherche_groupe(
    ex: Execution,
    g: CleGroupe,
    reponses: list[tuple[Answer, Question]],
    resoudre: Resolveur,
    vecteur: Vecteurs,
) -> list[LigneRecherche]:
    """Métriques de recherche par Question puis par Type et méthode ; remplit `vecteur`.

    Seulement en Condition standard : en contexte parfait, le runner fournit les Ancrages de
    référence eux-mêmes (`provided`), la recherche n'y est pas mesurée (rappel 1 par construction,
    y compris pour `no_context`, qui n'a pas de recherche)."""
    if g[1] != "standard":
        return []
    par_methode: dict[str, list[tuple[Question, dict[str, float]]]] = defaultdict(list)
    for a, q in reponses:
        valeurs = _metriques_reponse(a, q, resoudre)
        if valeurs is None:
            continue
        par_methode[a.retrieval_method].append((q, valeurs))
        for m, x in valeurs.items():
            vecteur[m][q.id] = x
    s = ex.experience.stats
    lignes: list[LigneRecherche] = []
    for methode, items in sorted(par_methode.items()):
        for type_ in (*sorted({q.type for q, _ in items}), TOUS):
            choisis = [v for q, v in items if type_ in (TOUS, q.type)]
            for m in METRIQUES_RECHERCHE:
                ic = bootstrap_ci(
                    [v[m] for v in choisis],
                    seed=_graine(ex, g, type_, m, methode),
                    n_resamples=s.resamples,
                    confidence=s.confidence,
                )
                if ic is not None:
                    lignes.append(
                        LigneRecherche(
                            g, type_, m, K_PAR_DEFAUT, ic.mean, ic.low, ic.high, ic.n, methode
                        )
                    )
    return lignes


def _paire(
    ex: Execution,
    cle: CleApparie,
    a: str,
    b: str,
    metric: str,
    va: dict[str, float],
    vb: dict[str, float],
) -> LignePaire | None:
    condition, tier, phase = cle
    s = ex.experience.stats
    continu = metric in METRIQUES_RECHERCHE
    test = "bootstrap_apparie" if continu else "mcnemar_exact"
    resultat: tuple[float, float, int] | None = None
    if continu:
        d = compare_continu(
            va,
            vb,
            seed=graine_derivee(
                ex.experience.seed, a, b, condition, etiquette_palier(tier), phase, metric
            ),
            n_resamples=s.resamples,
            confidence=s.confidence,
        )
        if d is not None:
            resultat = (d.diff, d.p_value, d.n_common)
    else:
        m = mcnemar_compare(
            {k: bool(x) for k, x in va.items()}, {k: bool(x) for k, x in vb.items()}
        )
        if m is not None:
            communes = sorted(set(va) & set(vb))
            diff = sum(va[k] - vb[k] for k in communes) / len(communes)
            resultat = (diff, m.p_value, m.n_common)
    if resultat is None:
        if not (va or vb):
            return None  # métrique sans donnée des deux côtés : rien à comparer
        return LignePaire(a, b, metric, None, None, test, 0, condition, tier, phase)
    return LignePaire(
        a, b, metric, resultat[0], resultat[1], test, resultat[2], condition, tier, phase
    )


def _paires(ex: Execution, vecteurs: dict[CleApparie, dict[str, Vecteurs]]) -> list[LignePaire]:
    """Une paire (A, B) par couple de Configurations, dans chaque (condition, tier, phase), sur
    les Questions communes. Sans Question commune : ligne à `n_common` 0 et sans p-valeur, jamais
    de « Qualité égale » déduite d'une absence de donnée."""
    lignes: list[LignePaire] = []
    ordre = sorted(vecteurs, key=lambda k: (k[0], -1 if k[1] is None else k[1], k[2]))
    for cle in ordre:
        par_config = vecteurs[cle]
        for a, b in itertools.combinations(sorted(par_config), 2):
            for metric in (QUALITE, *CRITERES, *METRIQUES_RECHERCHE):
                ligne = _paire(
                    ex,
                    cle,
                    a,
                    b,
                    metric,
                    par_config[a].get(metric, {}),
                    par_config[b].get(metric, {}),
                )
                if ligne is not None:
                    lignes.append(ligne)
    return lignes


def evaluer(ex: Execution, resoudre: Resolveur) -> Resultats:
    """Toutes les grandeurs de la story 4.11."""
    res = Resultats()
    groupes: dict[CleGroupe, list[tuple[Answer, Question]]] = defaultdict(list)
    for a in sorted(ex.reponses.values(), key=lambda r: r.question_id):
        g = groupe_de(a)
        c = res.comptes.setdefault(g, Comptes())
        q = ex.jeu.get(a.question_id)
        if q is None:
            continue  # Réponse d'une Question absente du Jeu : jamais notée
        if a.status != "ok":
            setattr(c, a.status, getattr(c, a.status) + 1)
            continue
        groupes[g].append((a, q))
        if q.contaminated_by:
            c.contaminees += 1
            continue
        c.ok += 1
        if any((a.answer_id, k) not in ex.panel for k in CRITERES):
            c.non_jugees += 1

    vecteurs: dict[CleApparie, dict[str, Vecteurs]] = defaultdict(dict)
    for g in sorted(groupes, key=_ordre):
        principales = [(a, q) for a, q in groupes[g] if not q.contaminated_by]
        contaminees = [(a, q) for a, q in groupes[g] if q.contaminated_by]
        res.scores += _scores_groupe(ex, g, principales, par_type=True, na_seuls=res.na_seuls)
        res.contaminees += [
            ligne
            for ligne in _scores_groupe(ex, g, contaminees, par_type=False)
            if ligne.critere == QUALITE
        ]
        v: Vecteurs = defaultdict(dict)
        for a, q in principales:
            verdicts = _verdicts(ex, a)
            if (oui := qualite(q, verdicts)) is not None:
                v[QUALITE][q.id] = float(oui)
            for critere in CRITERES:
                if critere in verdicts:
                    v[critere][q.id] = float(verdicts[critere])
        res.recherche += _recherche_groupe(ex, g, principales, resoudre, v)
        vecteurs[(g[1], g[2], g[3])][g[0]] = v
    res.paires = _paires(ex, vecteurs)
    return res
