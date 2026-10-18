---
story: "4.7"
title: Phase après mise à jour
status: done
---

# Story 4.7 : Phase après mise à jour

## Code Map

- `src/wavelibrarian/runner/execute.py` : `_Runner._phase_apres_mise_a_jour` (après la phase `base` d'une Configuration, une cellule `_cellule(..., maj=(changement, corpus de base))` par Condition), `_Runner.apres_mise_a_jour(parser)` (`appliquer_fichier` de la 2.6 avec `lang` du `corpus.yaml` et `parser` de la Configuration, Profil du Corpus après mise à jour, une fois par parser), `_index_de_base` (dossier de l'index de la base, construit d'abord s'il manque). `cibles_du_scenario` : Documents de base modifiés ou supprimés par le Scénario, requis dans chaque Palier (runner et `verifier_paliers`). Le Scénario est validé (`charger`) avant la création du dossier d'Exécution.
- `src/wavelibrarian/runner/index_cache.py` : `IndexCache.build(..., post="update", change=, old_dir=)` ; un index absent est produit par `arch.update(change, corpus_after, old_dir, .tmp-<clé>)` puis `os.replace` vers la clé du Corpus après mise à jour ; présent, il est servi par le cache.
- Tests : `tests/unit/runner/test_story_4_7.py`.

## Design Notes

- Ordre : pour chaque Configuration, Conditions et Paliers de la phase `base`, puis `after_update`. Le Scénario est appliqué et validé (`ConfigError`, code 2) avant tout appel payant, pour chaque parser utilisé.
- Questions reposées en `after_update` : toutes les Questions posées (décision n° 1 de l'orchestrateur, revue), par Condition et par Palier. La Fraîcheur lit celles à `scenario_target` ; les autres mesurent la régression. Le contrôle `doc_id` de l'AC 3 reste limité aux Questions liées.
- Postes : `update` pour `index`/`update`/`load` (spans `wl.post=update`, `wl.phase=after_update`), `query` pour les Questions. Énergie locale relevée par `energie_de_phase(conf, "update")`, répartie comme pour l'indexation (report 4.5).
- `update` par défaut (`incremental_update: false`) réindexe `corpus_after` dans le dossier temporaire ; l'ancien dossier n'est qu'ouvert en lecture (testé par empreinte avant/après `update`, et par une Exécution sans Scénario qui le sert encore en cache).
- Contexte parfait : pas d'index ni de `update`. En `after_update`, les Ancrages de référence se résolvent dans le Corpus après mise à jour (nouveaux `doc_id` des Documents modifiés). Un Ancrage de Document supprimé (`scenario_target.state: before`, ex. `q-047`) donne `inapplicable` (raison nommant le Scénario), symétrique du cas `state: after` en `base` (4.6).
- Phase `base` inchangée : les Questions `state: after` y restent posées en Condition standard (décision de la 4.6).
- `applicability.json` : une Configuration inapplicable au Corpus après mise à jour porte la clé `<config_id>@after_update` (avec `phase`).
- `answer_id` : `.../<condition>/<palier ou all>/after_update/<question_id>`.
- Scénario et Paliers (revue, décision n° 2) : le Palier est tiré sur le Corpus de base, avec les Documents modifiés ou supprimés par le Scénario dans `required_paths` ; le Scénario s'applique ensuite au sous-corpus du Palier, ses ajouts y entrent (un Palier de n Documents devient n + ajouts − suppressions). `update` part de l'index de base du Palier. Conséquence : avec un Scénario, la composition des Paliers de la phase `base` diffère de celle d'une Expérience sans Scénario. Cibles trop nombreuses pour le plus petit Palier : code 2 au tirage à blanc. Clé d'applicabilité `<config_id>@<palier>@after_update`.

## Tâches et critères

- [x] AC 1 : `update(change, corpus_after, old_dir, tmp_dir)` appelé avec le changement net de la 2.6, renommage vers la nouvelle clé, instance neuve + `load`, Questions reposées en `after_update` : `test_phase_apres_mise_a_jour_pose_les_questions_liees_et_ne_touche_pas_l_ancien_index`.
- [x] AC 1 : ancien dossier d'index intact et réutilisable par une autre Exécution : même test (empreinte pendant `update`), `test_ancien_index_reste_reutilisable_par_une_autre_execution`.
- [x] AC 2 : réindexation complète par défaut, spans `wl.post=update`, énergie de la phase : `test_reindexation_complete_par_defaut_spans_au_poste_update_et_energie`.
- [x] AC 3 : aucun Passage ni Citation vers un ancien `doc_id`, Ancrages des Documents modifiés sous leur nouveau `doc_id` : `test_apres_mise_a_jour_aucun_ancien_doc_id_et_ancrages_vers_les_nouveaux`, `test_contexte_parfait_apres_mise_a_jour_ancrages_nouveaux_et_ancrage_supprime_inapplicable`.
- [x] AC 4 : rejeu avec les mêmes caches, `wl.index_cache_hit=true`, aucun `update` rappelé : `test_rejeu_l_index_apres_mise_a_jour_est_servi_par_le_cache`.
- [x] Report « Runner, Scénario » (`lang` et `parser` passés à `corpus_apres`) : `test_scenario_applique_avec_la_langue_du_corpus_et_le_parser_de_la_configuration`.
- [x] Report « 4.7 : `IndexCache.build(post="update")` » : tests d'AC 1, 2 et 4.
- [x] Report « énergie de `update` » : test d'AC 2.
- [x] Scénario + Paliers : `test_scenario_avec_paliers_applique_le_scenario_au_sous_corpus_de_chaque_palier`, `test_scenario_avec_paliers_refuse_en_2_si_les_cibles_ne_tiennent_pas`. Scénario invalide refusé en 2 sans dossier d'Exécution : `test_scenario_invalide_refuse_en_2`. Sans Question liée, Questions reposées quand même : `test_scenario_sans_question_liee_repose_quand_meme_les_questions`.
- [x] Architecture incrémentale (`naive_rag`) : son `update` est appelé, `index` seulement en base, moins de Passages encodés : `test_architecture_incrementale_naive_rag_appelle_son_update_sans_reindexer`.

## Auto Run Result

- Statut : review. Vérifications : voir le rapport de l'orchestrateur.
- Reports traités : `lang`/`parser` de `corpus_apres` ; `IndexCache.build(post="update")` ; énergie de `update`.
- Reports laissés : Fraîcheur dans le Rapport (4.13) ; reprise et `budget_exceeded` de la phase `after_update` (4.8) ; Panel (4.9) ; `update` incrémental testé sur le vrai Scénario par Architecture à embeddings dans la conformité (4.14).
- Risques : les Questions `state: after` restent posées en `base` (coût inutile).

## Revue

- medium, orchestrateur n° 1 et second avis n° 4 : seules les Questions à `scenario_target` étaient reposées, et le test figeait ce filtre. Corrigé : toutes les Questions posées sont reposées ; tests mis à jour, contrôle `doc_id` de l'AC 3 limité aux liées.
- medium, orchestrateur n° 2 : Scénario + Paliers refusé, alors que la 4.13 en a besoin. Corrigé : Palier tiré sur la base avec les cibles du Scénario requises, Scénario appliqué au sous-corpus, `update` depuis l'index de base du Palier ; testé (tous les Paliers, refus en 2 si les cibles ne tiennent pas).
- medium, second avis n° 3 : aucune Architecture incrémentale testée, alors que `naive_rag` en est une. Corrigé : test `naive_rag` (embedder `fake`) qui vérifie `update` appelé, pas de réindexation, encodage partiel.
- low, second avis n° 5 : le Scénario était validé après `create_run_dir` (dossier `failed` laissé). Corrigé : `charger` avant le dossier ; le test vérifie qu'aucun dossier n'est créé.
- low, second avis n° 6 : asymétrie de Fraîcheur. Reporté en 4.13 : en contexte parfait, une Question liée `state: before` (q-047) est `inapplicable` en `after_update`, alors qu'en Condition standard elle est posée et jugée. La 4.13 doit exclure les `inapplicable` du dénominateur de la Fraîcheur par Condition, et le dire dans le Rapport.
- info, revue : le Scénario est appliqué une fois par (parser, Palier) ; une erreur d'application à un Palier (par ex. contenu identique à un Document du Palier) donne des Réponses `error` pour la cellule, pas un code 2.
