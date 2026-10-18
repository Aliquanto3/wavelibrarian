---
story: "4.13"
title: "Rapport : Fraîcheur, Paliers, fronts de Pareto et export du front"
status: review
---

# Story 4.13 : Rapport : Fraîcheur, Paliers, fronts de Pareto et export du front

## Code Map

- `src/wavelibrarian/report/fronts.py` (nouveau) : `construire_fronts(ex, res, couts)` assemble Qualité et taux par Critère (4.11), `Couts.total_configuration` et `Couts.latences` (4.12) et appelle `stats/pareto.front_pareto` (4.10) ; `lignes_pareto` écrit `pareto.csv` (`front, config_id, x, y`).
- `src/wavelibrarian/report/fraicheur.py` (nouveau) : `calculer_fraicheur(ex)` et `qualite_par_palier(res)`.
- `src/wavelibrarian/report/section_fronts.py` (nouveau) : sections `report.md` « Configurations non dominées », « Résultats par Palier », « Fraîcheur ».
- `src/wavelibrarian/report/export.py` (nouveau) : `exporter_front(run_dir, front, vers)` lit `report/pareto.csv` et `experiment.resolved.yaml`, écrit la liste `configurations:`.
- `src/wavelibrarian/report/generer.py` : écrit `pareto.csv`, place la synthèse juste après l'en-tête, puis Paliers et Fraîcheur après les scores ; `construire_markdown(ex, res, couts, fronts, fraicheur)` (les deux derniers facultatifs, 4.11 et 4.12 inchangés).
- `src/wavelibrarian/cli.py` : `wl rapport <run_id> [--exporter-front <front> --vers <fichier>]`.
- Tests : `tests/unit/report/test_story_4_13.py`.

## Design Notes

- Un front est calculé par groupe (Condition, Palier), jamais en mêlant les groupes. Qualité et taux par Critère : phase `base`, toutes Questions, hors contaminées. Coût total : indexation + mise à jour + requête, phases cumulées, possession comprise, `judging`/`evalset` exclus. Latence : p95 de la phase `base`. Axe x = grandeur minimisée (euros, kWh, secondes), axe y = Qualité ou taux (maximisé).
- Noms de front : `qualite-cout`, `qualite-energie-mesuree`, `qualite-energie-estimee`, `qualite-latence-p95`, `critere-<critère>-cout`. Suffixes : `@perfect_context` (Condition hors `standard`) et `@palier-N` (tout Palier sauf le plus grand, le Corpus complet). `qualite-cout` sans suffixe est donc le front (standard, plus grand Palier) : celui du tableau de synthèse et de l'export.
- L'énergie mesurée et l'énergie estimée ne s'additionnent jamais (AD-17) : deux fronts, chacun limité aux Configurations qui ont des kWh de cette méthode. Sans `traces.jsonl` (ou `Couts` absent), pas de front de coût ni d'énergie (un coût nul pour tous ne départagerait rien) ; le Rapport le dit.
- Synthèse : sous le titre « Configurations non dominées (Qualité × coût total) », après l'en-tête (titre, statut, Expérience) et avant le profil de corpus ; colonnes `config_id`, Qualité [IC 95 %], coût total (€), latence p95 (s). Pas de score global, pas de pondération.
- Fraîcheur : parmi les Questions à `scenario_target`, part des Questions correctes (Qualité) en phase `after_update`, par (Configuration, Condition, Palier), avec IC bootstrap. `inapplicable` est retiré du dénominateur et compté à part (report 4.7 : en contexte parfait, q-047 dont l'Ancrage est supprimé) ; `error` et `budget_exceeded` aussi, et les Questions contaminées sont exclues, comme partout ailleurs dans le Rapport. Sans Scénario : une phrase.
- Palier : tableau Qualité [IC], coût total et p95 par (Configuration, Condition, Palier), phase `base`. Les Paliers ne se mêlent jamais dans un score.
- Citation « hors du Corpus » sur le sous-corpus du Palier (report 4.9) : pas de recalcul. Le Generator retire de `citations` toute étiquette absente du contexte étiqueté (comptée en `invalid_citations`, ce qui rend le Critère faux), et le contexte vient de l'index du Palier : une Citation conservée désigne toujours un Ancrage du sous-corpus. Lire le Critère sur le Corpus entier et sur le sous-corpus donne le même résultat ; la note est dans le Rapport. Recalculer exigerait de retirer le Palier au Rapport (`tirer`, `tiers`, Questions requises), donc de dupliquer le runner.
- Export : `wl rapport <run_id> --exporter-front <nom> --vers <fichier>` régénère le Rapport puis écrit les `config_id` du front lus dans `pareto.csv` (même front que le Rapport), avec leurs champs `id`, `architecture`, `parser`, `params` (et `reuse_index` seulement si sa cible est exportée aussi). `qualite-cout` ou tout nom de `pareto.csv` ; nom inconnu = code 2 avec la liste des noms ; une seule des deux options = code 2. Un Parser résolu par format (`markdown+pdf_text`, qui n'est pas un nom de Parser) redevient `auto`. Le fichier ne contient que `configurations:` : à coller dans une Expérience, où `config/load.py` l'accepte telle quelle.

## Acceptance Criteria

- [x] AC 1 : Fraîcheur et résultats par Palier ont leur section : `test_fraicheur_denominateur_sans_inapplicables_et_comptes_a_part`, `test_fraicheur_calcul_a_la_main`, `test_section_paliers`.
- [x] AC 2 : `pareto.csv` (fronts Qualité × coût, énergie, latence p95, un front par Critère ; format `front, config_id, x, y`) : `test_fronts_non_dominees_cout_energie_latence_et_critere`, `test_pareto_csv_format_noms_et_non_dominance`, `test_front_qualite_cout_recalcule_depuis_les_csv`, `test_points_identiques_restent_et_plus_grand_palier_sans_suffixe`, `test_sans_traces_ni_front_de_cout_ni_d_energie`.
- [x] AC 3 : synthèse en tête, même front que `pareto.csv` : `test_report_s_ouvre_sur_la_synthese_du_front`.
- [x] AC 4 : export accepté par `config/load.py` : `test_export_front_accepte_par_config_load`, `test_export_front_refus`, `test_export_garde_reuse_index_seulement_si_la_cible_est_exportee`, `test_wl_rapport_regenere_pareto_csv_identique`.
- [x] Reports 4.9 (Citation et Palier), 4.7 (`inapplicable` hors dénominateur), 4.12 (`total_configuration`, `latences`) : voir Design Notes.

## Reports

- 4.14 : `mini-test.yaml` et SM-3 doivent produire `pareto.csv` avec au moins `qualite-cout` ; le test e2e peut relire `report.md` (synthèse en tête) et `--exporter-front qualite-cout`.
- 4.14 : une Configuration `llm_wiki` ou `raptor` paie son indexation au Poste `indexing` ; vérifier sur `mini-test.yaml` que les fronts restent lisibles quand le coût fake est nul (tous à 0 € : seule la Qualité départage).
- 4.14 : `reuse_index` n'est exporté que si sa cible l'est aussi ; une Configuration `reuse_index` hors front reconstruit son index dans la nouvelle Expérience.
- Fraîcheur absente de `scores.csv` et de `pareto.csv` (le contrat ne la liste pas parmi les fichiers) ; elle n'est que dans `report.md`.
- Les Qualités des fronts ne portent pas toutes sur les mêmes Questions si l'Exécution est partielle (plafond atteint) : à lire avec `n` des tableaux de scores.

## Auto Run Result

- Statut : review. Résultats des vérifications dans le rapport de l'agent.
