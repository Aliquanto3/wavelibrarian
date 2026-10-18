---
story: "4.4"
title: Exécution d'une Expérience par `wl run`
status: review
---

# Story 4.4 : Exécution d'une Expérience par `wl run`

## Code Map

- `src/wavelibrarian/runner/execute.py` : `load_questions(experience)` (Jeu chargé, `verify_frozen`, `select_questions`, tri par `id`, `max_questions`) et `run_experiment(experience, questions, *, wl_home, run_id=None, providers=None)`, qui rend un `RunOutcome` (`run_id`, `run_dir`, `status`, `n_answers`).
- `src/wavelibrarian/cli.py` : `wl run` enchaîne validation, préflight, `load_questions` puis `run_experiment`. Codes de sortie : 2 pour un `ConfigError` (Jeu non Gelé ou modifié), 1 pour une autre `WlError` (Exécution en cours), 3 pour `budget_exceeded`.
- `src/wavelibrarian/core/ids.py` : `answer_id(run_id, config_id, condition, tier, phase, question_id)`, avec `tier = "all"` sans Palier.
- `src/wavelibrarian/runner/context.py` : Cache de réponses jetable (dossier temporaire supprimé à `close`) quand un provider injecté est scénarisé, en Exécution seulement.
- `src/wavelibrarian/llm/providers/fake.py` : propriété `FakeProvider.scripted`.
- Tests : `tests/unit/runner/test_story_4_4.py`. Deux tests antérieurs (`test_installer.py::test_wl_run_preflight_reussi`, `test_validate.py::test_cli_experience_valide`) remplacent désormais l'Exécution par un bouchon, puisque `wl run` exécute réellement.

## Design Notes

- Ordre (AD-11) : `cli.py` charge, valide et passe le préflight. `load_questions` refuse ensuite un Jeu non Gelé ou modifié (`ConfigError`, code 2) avant le verrou, le registre ou tout appel. Puis `run_experiment` exécute `resolve_parsers`, prend un seul `Context.from_experiment(..., execution=True)` gardé vivant par `with` (`run.lock` d'abord, puis `Ledger(recover_orphans=True)`), et appelle `create_run_dir` avec `freeze_sha256` lu dans le Jeu. Viennent ensuite `run.log`, l'ingestion et le Profil (`corpus_profile.json`, avec le parser de la première Configuration). Pour chaque Configuration, dans l'ordre : `check()`, `IndexCache.build`, puis `answer` par Question dans `ctx.scope(post="query", question_id=...)`.
- Un second `wl run` échoue sur `run.lock` avant de créer quoi que ce soit (code 1, « Exécution <run_id> en cours »). Il ne règle pas les réservations ouvertes du premier.
- `ctx.config_id` et `ctx.parser` changent à chaque Configuration. L'ingestion et le Profil sont mis en mémoire par parser résolu. Les étapes sont journalisées au niveau INFO dans `run.log` (« étape ingestion », « étape check : <id> »…) : le niveau du logger `wavelibrarian` est abaissé à INFO pendant l'Exécution, puis restauré.
- Inapplicable : `applicability.json` contient `{config_id: {architecture, applicable: false, reason}}`, ou `{}` si toutes les Configurations s'appliquent. Il est toujours écrit. Chaque Question de la Configuration inapplicable reçoit un `Answer` `status: inapplicable` dont `error` porte la raison. Les autres Configurations s'exécutent.
- Erreurs : toute exception d'une Question, sauf `BudgetExceeded`, donne un `Answer` `status: error`, avec `error` au format `"<Type> : <message>"` et un avertissement dans `run.log`. L'Exécution passe à la Question suivante. Une exception à la construction, au `check` ou à l'index met toutes les Questions de cette Configuration en `error`, sans arrêter les autres Configurations.
- `BudgetExceeded` arrête l'Exécution : le manifeste passe à `budget_exceeded` et la commande sort en 3. Les Questions restantes ne sont pas écrites en `budget_exceeded` (story 4.8). Toute autre exception non rattrapée passe le manifeste à `failed`, puis remonte (code 1).
- Les Réponses `error` ou `inapplicable` gardent la `retrieval_method` de l'Architecture et un texte vide. `latency_s` reste à 0 en attendant la story 4.5, où il devient la somme des spans `query`.
- Le Faux LLM n'est pas injecté par `wl run` : `build_providers` construit déjà `FakeProvider` et le passe à `MeteredGateway`. Un Faux LLM scénarisé, injecté par les tests, reçoit un Cache de réponses jetable, si bien qu'une sortie scénarisée ne sert jamais une Exécution suivante.
- Hors périmètre, refusé explicitement plutôt qu'exécuté faux (`ConfigError`, code 2) : `conditions` autres que `[standard]` et `tier` non nul (story 4.6), `scenario` (story 4.7).

## Tâches et critères

- [x] AC 1 : `wl run` sur les trois Baselines (profil `test`, Mini-corpus, `split: dev`). Ordre d'AD-11 vérifié dans `run.log` et dans la sortie, un `Answer` par clé, `answer_id` au format §1 avec `tier = all`, manifeste `completed`, sortie 0 : `test_wl_run_trois_baselines_de_bout_en_bout`.
- [x] AC 2 : Jeu non Gelé ou modifié refusé en code 2 avant tout appel, sans dossier ni registre : `test_jeu_non_gele_ou_modifie_refuse_avant_tout_appel[non_gele|modifie]`. Seules les Questions `validated` et `corrected` de la partie demandée sont posées : `test_seules_les_questions_validees_ou_corrigees_de_la_partie_sont_posees`, ainsi que le test d'AC 1 pour `dev`.
- [x] AC 3 : `long_context` inapplicable figure dans `applicability.json` avec sa raison, ses Questions sont `inapplicable` et les autres Configurations s'exécutent : `test_long_context_inapplicable_les_autres_s_executent`.
- [x] AC 4 : `NonConformantOutput` scénarisé donne `status: error` avec son message, et les Questions suivantes passent en `ok` : `test_sortie_non_conforme_status_error_et_l_execution_continue`.
- [x] AC 5 : `max_questions: 3` pose les trois premières Questions par `id` : `test_max_questions_trois_premieres_par_id`.
- [x] Report sur `run.lock` puis `Ledger(recover_orphans=True)` : un second `wl run` sort en 1 sans régler les réservations du premier, testé par `test_second_wl_run_code_1_sans_regler_les_reservations_du_premier`.
- [x] Report sur le contexte gardé vivant (`with`) : le verrou est tenu pendant `answer`, vérifié dans le test d'AC 4.
- [x] Reports `verify_frozen` / `select_questions` : couverts par les tests d'AC 2.
- [x] Report Faux LLM et cache isolé des runs scénarisés : `test_sortie_scenarisee_ne_persiste_pas_dans_le_cache_de_wl_home`. Le Faux LLM par défaut est couvert par le test d'AC 1, qui passe par la CLI sans injection.
- [x] Refus explicite de ce qui relève des stories 4.6 et 4.7 : `test_conditions_et_paliers_refuses_explicitement`.

## Auto Run Result

- Statut : review. Vérifications et décompte des tests : voir le rapport de l'orchestrateur.
- Reports traités : `run.lock` puis `Ledger(recover_orphans=True)` avec le test d'un second `wl run`, contexte gardé vivant par `with`, `verify_frozen` / `select_questions`, Faux LLM (construit par `build_providers`) et cache isolé des runs scénarisés. Sont aussi couverts `parser` fixé depuis la Configuration et l'écriture de `manifest.json`, `run.log` et `experiment.resolved.yaml` dans `wl run`.
- Reports laissés aux stories suivantes :
  - Panel, `JudgeInput` et `scope(post="judging")` : story 4.9.
  - Span `local` `answer`, `latency_s`, énergie par phase et `token_factor` : story 4.5.
  - Questions restantes `budget_exceeded` et reprise : story 4.8.
  - Contexte parfait et `required_paths` des Paliers : story 4.6.
  - Scénario (`lang` et `parser` passés à `corpus_apres`) : story 4.7.
  - Rapport enchaîné par `cli.py` : story 4.11.
  - Libération manuelle d'une réservation `hors_execution` orpheline, plafond `ollama` hors EUR à la validation, contrôle du réservoir de Juges au préflight (déjà fait en 1.12 pour `wl run`) : non traités.
- Écart : AD-11 place le Gel dans « chargement, validation ». Il est vérifié après le préflight, mais avant tout appel payant, avant `run.lock` et avant le dossier d'Exécution. Les tests du préflight, qui utilisent des Expériences factices, gardent ainsi leur sens.
- Risque : abaisser le niveau du logger `wavelibrarian` est une modification globale. Elle est restaurée en fin d'Exécution, mais un appelant concurrent (hors AD-11) la verrait.
