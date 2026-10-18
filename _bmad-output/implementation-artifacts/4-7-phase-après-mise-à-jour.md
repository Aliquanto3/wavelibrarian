---
story: "4.7"
title: Phase après mise à jour
status: review
---

# Story 4.7 : Phase après mise à jour

## Code Map

- `src/wavelibrarian/runner/execute.py` : `_Runner._phase_apres_mise_a_jour` (après la phase `base` d'une Configuration, une cellule `_cellule(..., maj=(changement, corpus de base))` par Condition), `_Runner.apres_mise_a_jour(parser)` (`appliquer_fichier` de la 2.6 avec `lang` du `corpus.yaml` et `parser` de la Configuration, Profil du Corpus après mise à jour, une fois par parser), `_index_de_base` (dossier de l'index de la base, construit d'abord s'il manque). `_hors_perimetre` ne refuse plus que Scénario + `tier`.
- `src/wavelibrarian/runner/index_cache.py` : `IndexCache.build(..., post="update", change=, old_dir=)` ; un index absent est produit par `arch.update(change, corpus_after, old_dir, .tmp-<clé>)` puis `os.replace` vers la clé du Corpus après mise à jour ; présent, il est servi par le cache.
- Tests : `tests/unit/runner/test_story_4_7.py`.

## Design Notes

- Ordre : pour chaque Configuration, Conditions et Paliers de la phase `base`, puis `after_update`. Le Scénario est appliqué et validé (`ConfigError`, code 2) avant tout appel payant, pour chaque parser utilisé.
- Questions reposées en `after_update` : celles dont `scenario_target` est défini (parmi les Questions posées), par Condition. Ce sont elles que la Fraîcheur lit (contracts.md §6) ; reposer les autres coûterait sans rien mesurer de plus. Sans Question liée, la phase n'est pas exécutée (avertissement dans `run.log`).
- Postes : `update` pour `index`/`update`/`load` (spans `wl.post=update`, `wl.phase=after_update`), `query` pour les Questions. Énergie locale relevée par `energie_de_phase(conf, "update")`, répartie comme pour l'indexation (report 4.5).
- `update` par défaut (`incremental_update: false`) réindexe `corpus_after` dans le dossier temporaire ; l'ancien dossier n'est qu'ouvert en lecture (testé par empreinte avant/après `update`, et par une Exécution sans Scénario qui le sert encore en cache).
- Contexte parfait : pas d'index ni de `update`. En `after_update`, les Ancrages de référence se résolvent dans le Corpus après mise à jour (nouveaux `doc_id` des Documents modifiés). Un Ancrage de Document supprimé (`scenario_target.state: before`, ex. `q-047`) donne `inapplicable` (raison nommant le Scénario), symétrique du cas `state: after` en `base` (4.6).
- Phase `base` inchangée : les Questions `state: after` y restent posées en Condition standard (décision de la 4.6).
- `applicability.json` : une Configuration inapplicable au Corpus après mise à jour porte la clé `<config_id>@after_update` (avec `phase`).
- `answer_id` : `.../<condition>/all/after_update/<question_id>` (pas de Palier).
- Scénario et Paliers : refus en code 2 (le Scénario s'applique au Corpus entier ; un Palier est un sous-corpus tiré avant la mise à jour). À lever si la 4.13 a besoin de Paliers après mise à jour.

## Tâches et critères

- [x] AC 1 : `update(change, corpus_after, old_dir, tmp_dir)` appelé avec le changement net de la 2.6, renommage vers la nouvelle clé, instance neuve + `load`, Questions reposées en `after_update` : `test_phase_apres_mise_a_jour_pose_les_questions_liees_et_ne_touche_pas_l_ancien_index`.
- [x] AC 1 : ancien dossier d'index intact et réutilisable par une autre Exécution : même test (empreinte pendant `update`), `test_ancien_index_reste_reutilisable_par_une_autre_execution`.
- [x] AC 2 : réindexation complète par défaut, spans `wl.post=update`, énergie de la phase : `test_reindexation_complete_par_defaut_spans_au_poste_update_et_energie`.
- [x] AC 3 : aucun Passage ni Citation vers un ancien `doc_id`, Ancrages des Documents modifiés sous leur nouveau `doc_id` : `test_apres_mise_a_jour_aucun_ancien_doc_id_et_ancrages_vers_les_nouveaux`, `test_contexte_parfait_apres_mise_a_jour_ancrages_nouveaux_et_ancrage_supprime_inapplicable`.
- [x] AC 4 : rejeu avec les mêmes caches, `wl.index_cache_hit=true`, aucun `update` rappelé : `test_rejeu_l_index_apres_mise_a_jour_est_servi_par_le_cache`.
- [x] Report « Runner, Scénario » (`lang` et `parser` passés à `corpus_apres`) : `test_scenario_applique_avec_la_langue_du_corpus_et_le_parser_de_la_configuration`.
- [x] Report « 4.7 : `IndexCache.build(post="update")` » : tests d'AC 1, 2 et 4.
- [x] Report « énergie de `update` » : test d'AC 2.
- [x] Refus avant tout appel : Scénario + Paliers `test_scenario_avec_paliers_refuse_en_2_avant_tout_appel`, Scénario invalide `test_scenario_invalide_refuse_en_2` ; sans Question liée `test_scenario_sans_question_liee_n_execute_pas_la_phase`.

## Auto Run Result

- Statut : review. Vérifications : voir le rapport de l'orchestrateur.
- Reports traités : `lang`/`parser` de `corpus_apres` ; `IndexCache.build(post="update")` ; énergie de `update`.
- Reports laissés : Fraîcheur dans le Rapport (4.13) ; reprise et `budget_exceeded` de la phase `after_update` (4.8) ; Panel (4.9) ; `update` incrémental testé sur le vrai Scénario par Architecture à embeddings dans la conformité (4.14).
- Risques : Scénario + Paliers refusé ; les Questions `state: after` restent posées en `base` (coût inutile) ; `update` d'une Architecture incrémentale n'est exercé ici que par la réindexation par défaut (aucune Architecture incrémentale n'est dans la branche).
