---
story: "4.10"
title: Statistiques : bootstrap, McNemar et fronts de Pareto
status: done
---

# Story 4.10 : Statistiques : bootstrap, McNemar et fronts de Pareto

## Code Map

- `src/wavelibrarian/stats/appariement.py` : `questions_communes(a, b)` (intersection triée).
- `src/wavelibrarian/stats/bootstrap.py` : `bootstrap_ci -> Intervalle | None`, `paired_bootstrap -> DifferenceAppariee | None`, `compare_continu(a, b)` sur dicts par Question.
- `src/wavelibrarian/stats/mcnemar.py` : `mcnemar_exact(b, c)`, `compare(a, b) -> ResultatMcNemar` (b, c, p_value, n_common).
- `src/wavelibrarian/stats/pareto.py` : `Point(config_id, qualite, cout)`, `domine`, `front_pareto`.
- Tests : `tests/unit/stats/test_bootstrap_mcnemar_pareto.py`.

## Design Notes

- Fonctions pures, sans import du projet hors `stats/` (AD-22). Graine entière fournie par l'appelant (AD-20) ; `numpy.random.default_rng(seed)`.
- IC : un seul tirage `rng.integers(0, n, (B, n))`, comme `scipy.stats.bootstrap` ; percentiles `np.percentile` aux niveaux alpha/2 et 1-alpha/2. Défauts : B = 2 000, 95 %.
- P-valeur du bootstrap apparié : 2 * min(part <= 0, part >= 0) des moyennes rééchantillonnées, corrigée (+1)/(B+1) et plafonnée à 1. Le contrat §7 ne fixe pas la méthode ; choix consigné ici.
- McNemar exact : `binomtest(min(b, c), b + c, 0.5)` ; b = c = 0 donne 1. Pas de correction de multiplicité (Holm/Bonferroni absents du contrat §7).
- Front de Pareto : un point en domine un autre s'il est au moins aussi bon sur les deux axes et strictement meilleur sur un ; les points identiques restent tous. Ordre : coût croissant, Qualité décroissante, `config_id`. Le même `front_pareto` sert aux fronts énergie, latence et par Critère (l'appelant passe la grandeur en `cout`).

## Tâches et critères

- [x] IC percentile = `scipy.stats.bootstrap` à 1e-9 (100 valeurs, 70 succès, 2 000, graine 42) ; même graine, même IC : `test_ic_identique_a_scipy`, `test_meme_graine_meme_ic_et_vide`.
- [x] Bootstrap apparié : différence, IC, p bilatérale sur données connues : `test_bootstrap_apparie_donnees_connues`.
- [x] McNemar exact b = 12, c = 3 = `binomtest(3, 15, 0.5)` ; b = c = 0 donne 1 : `test_mcnemar_exact`.
- [x] `compare` sur Questions communes avec `n_common` : `test_compare_questions_communes`.
- [x] Front de Pareto avec dominé et ex æquo, ordre déterministe : `test_pareto_domine_et_egalite`.

## Auto Run Result

- Statut : review. Comptes de tests, pyright et contrôle rapide dans le rapport de l'agent.
- Reports : agrégation par groupe, `pairs.csv`, `pareto.csv`, critère « Qualité égale » : stories de Rapport (4.11 et suivantes). Aucune correction de multiplicité.

## Revue

Revue Opus en une passe, après rebasage sur `main` (8b30f60), avec la liste du second avis (Haiku).

- medium, second avis 1, corrigé : le test apparié n'avait qu'une différence constante. Ajout de `test_bootstrap_apparie_ic_scipy_et_p_analytique` : IC apparié contre `scipy.stats.bootstrap` sur des différences non constantes (1e-9), et p-valeur contre la valeur théorique 14/27 du cas d = [1, 1, -1].
- medium, second avis 2, corrigé : AD-20 demande `default_rng(int(sha16(seed, *clés), 16))`. Les fonctions gardent une graine entière (le critère 1 exige `default_rng(42)`), et `graine_derivee(seed, *clés)` est ajoutée dans `stats/bootstrap.py`. Le Rapport (4.11) doit l'appeler avec des clés propres à chaque grandeur (config_id, condition, tier, phase, critère ou paire).
- medium, revue (prolonge le second avis 5), corrigé : `compare()` sans Question commune renvoyait p = 1, ce qui ferait conclure à une « Qualité égale » (p ≥ 0,05) sans donnée et ouvrirait le calcul du point mort. Elle renvoie désormais `None`, comme `compare_continu()`.
- low, second avis 4, corrigé : un NaN échappait à la dominance et entrait dans le front. `front_pareto` refuse les points non finis, et le bootstrap refuse les valeurs non finies.
- low, second avis 3, rejeté : `Point.cout` reste le nom de l'axe minimisé. La docstring précise qu'il porte le coût total, l'énergie ou la latence p95, et le Rapport l'écrit en `x` dans `pareto.csv`.
- low, second avis 6, rejeté : le type `Mapping[str, bool]` exclut `None`. La docstring de `compare` laisse à l'appelant le choix d'exclure une Réponse absente ou de la compter fausse.
- low, second avis 7, reporté (4.11) : pas de correction de multiplicité, absente de `contracts.md` §7. À signaler dans le Rapport, à côté de `pairs.csv`.
