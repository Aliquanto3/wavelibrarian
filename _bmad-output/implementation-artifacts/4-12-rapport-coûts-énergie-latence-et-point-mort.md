---
story: "4.12"
title: "Rapport : coûts, énergie, latence et point mort"
status: review
---

# Story 4.12 : Rapport : coûts, énergie, latence et point mort

## Code Map

- `src/wavelibrarian/report/couts.py` (nouveau) : `calculer_couts(ex, res) -> Couts` lit `traces.jsonl` (`lire_jsonl`, tolérant à une ligne tronquée) et `answers.jsonl` ; lignes par (config_id, condition, tier, phase, post), latences, points morts. `total_configuration(config, condition, tier)` (indexation + mise à jour + requête, possession comprise, `judging`/`evalset` exclus) est prévu pour les fronts de Pareto de 4.13.
- `src/wavelibrarian/report/section_couts.py` (nouveau) : section « Coûts, énergie et latence » de `report.md`.
- `src/wavelibrarian/report/generer.py` : écrit `costs.csv` et branche la section ; `construire_markdown(ex, res, couts=None)`.
- Tests : `tests/unit/report/test_story_4_12.py` (traces écrites à la main) ; `test_story_4_11.py` attend désormais `costs.csv`.

## Design Notes

- `costs.csv` : les huit colonnes du contrat, puis le groupe (`condition`, `tier`, `phase`, comme `pairs.csv`), `possession_eur` et `co2e_g_estimated`. `cost_eur_real` et `cost_eur_uncached` incluent la possession ; `possession_eur` la donne à part.
- Conversion : `wl.cost` (Decimal) × `costs.fx.rates_to_eur[wl.currency]` ; devise vide = EUR (span local) ; devise inconnue = `ConfigError`. Taux, source et date affichés en tête de section ; la somme des `wl.cost` convertie est affichée et testée égale à la somme des lignes (FR-29).
- Coût de possession (`measure/tco.py`) : kWh des spans locaux (`local`, `embed`, `rerank`, LLM `ollama`) et leur durée, par ligne. Les spans `wl.llm_cache_hit` sont exclus de la durée (latence d'origine, bornes fictives) ; les spans `wl.resumed` sont exclus des appels, de la latence, de la durée et de l'énergie (leur coût nul reste dans la somme). Stockage de l'index : 0, sa taille n'est dans aucun fichier de l'Exécution (limite écrite dans le Rapport).
- Énergie : `kwh_measured` et `kwh_estimated` sont deux colonnes, jamais additionnées, avec avertissement. `co2e_g` = kWh mesurés × intensité déclarée ; `co2e_g_estimated` est la même chose pour les kWh estimés (jamais additionné non plus). Énergie `unknown` comptée 0.
- `n_calls` : spans non `local` et non `resumed` (un hit du cache est un appel, à coût nul). Les spans `local` (`index`, `answer`) portent la durée et l'énergie, pas un appel.
- `judging` et `evalset` : tableau à part, hors coût d'une Configuration. Le préchargement CAG, facturé à chaque Exécution au Poste `indexing`, est signalé quand une Configuration `cag` existe.
- Latence p50 et p95 : quantiles (interpolation linéaire) de `Answer.latency_s` des Réponses `ok` du groupe, contaminées comprises (le coût des spans les comprend aussi). Débit = Réponses `ok` ÷ durée murale de la phase query (premier début, dernier fin ; un hit du cache a un début égal à sa fin). Coût par requête = Poste `query` (possession comprise) ÷ Réponses `ok` ; × 1 000.
- Point mort : pour chaque couple (A, B), A plus cher à l'indexation (Poste `indexing`, Condition standard, phase `base`, même Palier). Qualité de A tirée de `pairs` (4.11) : « significativement inférieure » = p < alpha et A − B < 0 ; aucune Question commune (`diff` ou `p_value` `None`) = pas de point mort. Sinon requête_A ≥ requête_B = raison. Sinon N* = ⌈(indexation_A − indexation_B) ÷ (requête_B − requête_A)⌉ (Decimal, euros).
- Fidélité du wiki (`section_fidelite`, 7.3) : déjà branchée en 4.11, rien à ajouter.

## Acceptance Criteria

- [x] AC 1 : `costs.csv` et somme convertie : `test_costs_csv_colonnes_et_somme_des_wl_cost_convertie`, `test_somme_des_couts_convertie_egale_le_total_affiche`, `test_devise_inconnue_est_une_erreur_de_configuration` ; possession : `test_possession_du_calcul_local_hors_hits_et_reprises`.
- [x] AC 2 : énergies séparées, avertissement, CO2e : `test_energie_mesuree_et_estimee_jamais_additionnees`.
- [x] AC 3 : p50/p95, débit, coût par requête : `test_quantiles_par_interpolation_lineaire`, `test_latence_debit_et_cout_par_requete`, `test_debit_absent_sans_duree`.
- [x] AC 4 : point mort et raisons : `test_point_mort_a_qualite_egale`, `test_point_mort_paire_orientee_dans_l_autre_sens`, `test_point_mort_raisons_au_lieu_d_un_nombre`, `test_aucun_point_mort_sans_indexation_plus_chere`.
- [x] Reports 4.5, 4.8, 6.5, 7.3 : voir Design Notes ; `test_traces_absentes_sont_signalees`, `test_wl_rapport_regenere_costs_csv_identique`.

## Reports

- 4.13 : `Couts.total_configuration` et `Couts.latences` (p95) alimentent `pareto.csv` ; le coût et l'énergie sont par (config, condition, tier), toutes phases cumulées pour le coût total.
- 4.13 : le point mort ne regarde que la phase `base` ; un coût de mise à jour (`update`) n'entre pas dans N*.
- 4.14 : vérifier sur `mini-test.yaml` que le total du Rapport égale le coût tracé (SM-4, 4.15 au centime près).
- Stockage de l'index : à compter si la taille de l'index entre un jour dans le manifeste de l'Exécution.

## Auto Run Result

- Statut : review. Résultats des vérifications dans le rapport de l'agent.
