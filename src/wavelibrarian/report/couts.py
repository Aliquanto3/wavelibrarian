"""Coûts, énergie, latence, débit et point mort du Rapport (story 4.12, FR-31, FR-32, FR-34, FR-29).

Tout se calcule de `traces.jsonl` (spans, contracts.md §6) et d'`answers.jsonl` (latence des
Réponses). Un span `wl.resumed` (reprise, story 4.8) n'est compté ni dans les appels, ni dans la
latence, ni dans la durée de calcul local, ni dans l'énergie ; son coût réel (nul : hit du cache)
reste dans la somme de `wl.cost`, mais pas son `wl.cost_uncached`, déjà porté par l'appel
d'origine. Les énergies `measured` et `estimated` ne s'additionnent jamais (AD-17).
"""

import logging
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from wavelibrarian.config.schemas import CostSettings
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.jsonl import lire_jsonl
from wavelibrarian.measure.tco import possession_cost
from wavelibrarian.report.lecture import CleGroupe, Execution
from wavelibrarian.report.scores import QUALITE, Resultats

log = logging.getLogger(__name__)

POSTES_CONFIGURATION = ("indexing", "update", "query")
POSTES_A_PART = ("judging", "evalset")  # hors coût d'une Configuration
LOCAUX = frozenset({"local", "embed", "rerank"})
ENTETE_COUTS = [
    "config_id", "post", "cost_eur_real", "cost_eur_uncached", "kwh_measured", "kwh_estimated",
    "co2e_g", "n_calls", "condition", "tier", "phase", "possession_eur", "co2e_g_estimated",
]  # fmt: skip
_MICRO = Decimal("0.000001")
_ZERO = Decimal(0)

CleCout = tuple[str, str, int | None, str, str]  # (config_id, condition, tier, phase, post)
CleBornes = tuple[str, str, int | None, str]


@dataclass
class LigneCout:
    """Un Poste d'une Configuration dans un groupe. `real` et `uncached` incluent la possession."""

    cle: CleCout
    api_real: Decimal = _ZERO  # somme des `wl.cost` convertie, sans possession (FR-29)
    api_uncached: Decimal = _ZERO
    possession: Decimal = _ZERO
    kwh_measured: Decimal = _ZERO
    kwh_estimated: Decimal = _ZERO
    co2e_measured_g: Decimal = _ZERO
    co2e_estimated_g: Decimal = _ZERO
    n_calls: int = 0
    kwh_local: Decimal = _ZERO
    secondes_locales: Decimal = _ZERO

    @property
    def real(self) -> Decimal:
        return self.api_real + self.possession

    @property
    def uncached(self) -> Decimal:
        return self.api_uncached + self.possession


@dataclass(frozen=True)
class LigneLatence:
    groupe: CleGroupe
    n: int  # Réponses `ok` du groupe
    p50: float | None
    p95: float | None
    debit_qpm: float | None  # Questions par minute (durée murale de la phase query)
    cout_requete: Decimal | None
    cout_1000: Decimal | None


@dataclass(frozen=True)
class PointMort:
    """`n_star` (requêtes) ou, à défaut, la `raison` pour laquelle il n'y en a pas."""

    config_a: str
    config_b: str
    tier: int | None
    n_star: int | None
    raison: str = ""


@dataclass
class Couts:
    lignes: list[LigneCout] = field(default_factory=list)
    latences: list[LigneLatence] = field(default_factory=list)
    points_morts: list[PointMort] = field(default_factory=list)
    traces_presentes: bool = True
    spans_sans_energie: int = 0
    valeurs_invalides: int = 0  # `wl.cost` ou `wl.cost_uncached` illisibles, comptés 0 (FR-29)

    def total_api(self) -> Decimal:
        """Somme des `wl.cost` de tous les spans, convertie en euros (FR-29)."""
        return sum((ligne.api_real for ligne in self.lignes), _ZERO)

    def total_possession(self) -> Decimal:
        return sum((ligne.possession for ligne in self.lignes), _ZERO)

    def total_configuration(self, config: str, condition: str, tier: int | None) -> Decimal:
        """Coût total d'une Configuration (indexation + mise à jour + requête, possession
        comprise), `judging` et `evalset` exclus ; réutilisé par les fronts de Pareto (4.13)."""
        return sum(
            (
                ligne.real
                for ligne in self.lignes
                if ligne.cle[:3] == (config, condition, tier)
                and ligne.cle[4] in POSTES_CONFIGURATION
            ),
            _ZERO,
        )


def taux_vers_euro(costs: CostSettings, devise: str) -> Decimal:
    if devise in ("EUR", ""):  # un span local n'a pas de devise
        return Decimal(1)
    try:
        return costs.fx.rates_to_eur[devise]
    except KeyError:
        raise ConfigError(
            "costs.fx.rates_to_eur", f"aucun taux de change vers l'euro pour la devise `{devise}`"
        ) from None


def quantile(valeurs: list[float], q: float) -> float | None:
    """Quantile par interpolation linéaire (méthode par défaut de numpy) ; `None` si vide."""
    if not valeurs:
        return None
    s = sorted(valeurs)
    rang = (len(s) - 1) * q
    bas = math.floor(rang)
    haut = math.ceil(rang)
    return s[bas] + (s[haut] - s[bas]) * (rang - bas)


def _est_local(span: dict[str, Any]) -> bool:
    return span.get("wl.kind") in LOCAUX or (
        span.get("wl.kind") == "llm" and span.get("gen_ai.provider.name") == "ollama"
    )


def _decimal(valeur: Any, couts: Couts | None = None) -> Decimal:
    """`Decimal` fini, ou 0 pour une valeur illisible, comptée dans `couts.valeurs_invalides`."""
    try:
        d = Decimal(str(valeur))
        if d.is_finite():
            return d
    except ArithmeticError:
        pass
    log.warning("valeur numérique illisible dans traces.jsonl, comptée 0 : %r", valeur)
    if couts is not None:
        couts.valeurs_invalides += 1
    return _ZERO


def _ordre_cle(c: CleCout) -> tuple[str, str, int, str, str]:
    return (c[0], c[1], -1 if c[2] is None else c[2], c[3], c[4])


def _agreger(
    spans: Iterable[dict[str, Any]], costs: CostSettings, couts: Couts
) -> dict[CleBornes, tuple[int, int]]:
    """Remplit `couts.lignes` ; rend les bornes (ns) de la phase query par groupe."""
    lignes: dict[CleCout, LigneCout] = {}
    bornes: dict[CleBornes, tuple[int, int]] = {}
    gco2 = costs.carbon.gco2e_per_kwh
    for s in spans:
        config, post = s.get("wl.config_id"), s.get("wl.post")
        if not config or not post:
            log.warning("span sans config_id ou sans poste ignoré : %s", s.get("name"))
            continue
        tier = s.get("wl.tier")
        cle: CleCout = (
            str(config),
            str(s.get("wl.condition", "standard")),
            tier if isinstance(tier, int) else None,
            str(s.get("wl.phase", "base")),
            str(post),
        )
        ligne = lignes.setdefault(cle, LigneCout(cle))
        taux = taux_vers_euro(costs, str(s.get("wl.currency", "EUR")))
        ligne.api_real += _decimal(s.get("wl.cost", 0), couts) * taux
        if s.get("wl.resumed") is True:
            # Appel refait à la reprise : ni appel, ni latence, ni énergie, et son coût hors
            # cache est déjà porté par le span de l'appel d'origine.
            continue
        ligne.api_uncached += _decimal(s.get("wl.cost_uncached", s.get("wl.cost", 0)), couts) * taux
        hit = s.get("wl.llm_cache_hit") is True
        if s.get("wl.kind") != "local":
            ligne.n_calls += 1
        energie = s.get("wl.energy_kwh")
        methode = s.get("wl.energy_method")
        if isinstance(energie, int | float) and methode in ("measured", "estimated"):
            kwh = _decimal(energie)
            if methode == "measured":
                ligne.kwh_measured += kwh
                ligne.co2e_measured_g += kwh * gco2
            else:
                ligne.kwh_estimated += kwh
                ligne.co2e_estimated_g += kwh * gco2
            if _est_local(s):
                ligne.kwh_local += kwh
        elif _est_local(s):
            couts.spans_sans_energie += 1
        if _est_local(s) and not hit:  # un hit porte la latence d'origine : rien n'a tourné
            ligne.secondes_locales += _decimal(s.get("wl.latency_s", 0))
        if post == "query":
            fin = s.get("end_time")
            debut = fin if hit else s.get("start_time")
            if isinstance(debut, int) and isinstance(fin, int):
                g = cle[:4]
                b = bornes.get(g)
                bornes[g] = (debut, fin) if b is None else (min(b[0], debut), max(b[1], fin))
    for ligne in lignes.values():
        # Le stockage de l'index n'est pas dans les fichiers de l'Exécution : index_gb = 0.
        ligne.possession = possession_cost(
            costs, kwh=ligne.kwh_local, compute_seconds=ligne.secondes_locales, index_gb=0
        )
    couts.lignes = [lignes[c] for c in sorted(lignes, key=_ordre_cle)]
    return bornes


def _latences(
    ex: Execution, couts: Couts, bornes: dict[CleBornes, tuple[int, int]]
) -> list[LigneLatence]:
    par_groupe: dict[CleGroupe, list[float]] = defaultdict(list)
    for a in ex.reponses.values():
        if a.status == "ok":
            par_groupe[(a.config_id, a.condition, a.tier, a.phase)].append(a.latency_s)
    cout_query = {c.cle[:4]: c.real for c in couts.lignes if c.cle[4] == "query"}
    lignes: list[LigneLatence] = []
    for g in sorted(par_groupe, key=lambda g: (g[0], g[1], -1 if g[2] is None else g[2], g[3])):
        valeurs = par_groupe[g]
        n = len(valeurs)
        b = bornes.get(g)
        minutes = (b[1] - b[0]) / 6e10 if b else 0.0
        cout = cout_query.get(g, _ZERO) / n
        lignes.append(
            LigneLatence(
                g,
                n,
                quantile(valeurs, 0.5),
                quantile(valeurs, 0.95),
                n / minutes if minutes > 0 else None,
                cout,
                cout * 1000,
            )  # fmt: skip
        )
    return lignes


def _points_morts(ex: Execution, res: Resultats, couts: Couts) -> list[PointMort]:
    """Point mort N* de chaque couple (A, B) où A coûte plus à l'indexation, en Condition standard
    et phase `base`, palier par palier (contracts.md §7)."""
    index: dict[tuple[str, int | None], Decimal] = defaultdict(Decimal)
    for ligne in couts.lignes:
        config, condition, tier, phase, post = ligne.cle
        if condition == "standard" and phase == "base" and post == "indexing":
            index[(config, tier)] += ligne.real
    requete = {
        (lat.groupe[0], lat.groupe[2]): lat.cout_requete
        for lat in couts.latences
        if lat.groupe[1] == "standard" and lat.groupe[3] == "base"
    }
    paires = {
        (p.config_a, p.config_b, p.tier): p
        for p in res.paires
        if p.metric == QUALITE and p.condition == "standard" and p.phase == "base"
    }
    alpha = ex.experience.stats.alpha
    sortie: list[PointMort] = []
    cles = sorted(requete, key=lambda k: (k[1] is not None, k[1] or 0, k[0]))
    for a in cles:
        for b in cles:
            if a == b or a[1] != b[1] or index[a] <= index[b]:
                continue
            tier = a[1]
            qa, qb = requete[a], requete[b]
            p = paires.get((a[0], b[0], tier)) or paires.get((b[0], a[0], tier))
            raison = ""
            if qa is None or qb is None:
                raison = "aucune Réponse à comparer"
            elif p is None or p.diff is None or p.p_value is None:
                raison = "Qualité non comparable : aucune Question commune"
            elif p.p_value < alpha and (p.diff if p.config_a == a[0] else -p.diff) < 0:
                raison = "Qualité de A significativement inférieure à celle de B"
            elif qa >= qb:
                raison = "le coût par requête de A n'est pas inférieur à celui de B"
            if raison or qa is None or qb is None:
                sortie.append(PointMort(a[0], b[0], tier, None, raison))
            else:
                sortie.append(
                    PointMort(a[0], b[0], tier, math.ceil((index[a] - index[b]) / (qb - qa)))
                )
    return sortie


def calculer_couts(ex: Execution, res: Resultats) -> Couts:
    """Coûts par Poste, énergie, latence, débit et point mort de l'Exécution."""
    couts = Couts()
    chemin = ex.run_dir / "traces.jsonl"
    couts.traces_presentes = chemin.is_file()
    bornes = _agreger(lire_jsonl(chemin), ex.experience.costs, couts)
    couts.latences = _latences(ex, couts, bornes)
    couts.points_morts = _points_morts(ex, res, couts)
    return couts


def _q(x: Decimal) -> str:
    return f"{x.quantize(_MICRO):f}"


def ligne_csv(ligne: LigneCout) -> list[Any]:
    config, condition, tier, phase, post = ligne.cle
    return [
        config, post, _q(ligne.real), _q(ligne.uncached), f"{ligne.kwh_measured:.9f}",
        f"{ligne.kwh_estimated:.9f}", f"{ligne.co2e_measured_g:.6f}", ligne.n_calls, condition,
        "all" if tier is None else tier, phase, _q(ligne.possession),
        f"{ligne.co2e_estimated_g:.6f}",
    ]  # fmt: skip
