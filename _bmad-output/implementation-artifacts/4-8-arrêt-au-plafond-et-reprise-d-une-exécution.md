---
story: "4.8"
title: Arrêt au plafond et reprise d'une Exécution
status: done
---

# Story 4.8 : Arrêt au plafond et reprise d'une Exécution

## Code Map

- `src/wavelibrarian/runner/execute.py` : `run_experiment(..., reprendre=<run_id>)` ; `_Runner.marquer_budget_exceeded` (grille Configuration x phase x Condition x Palier x Question, une ligne `budget_exceeded` par clé sans Réponse) ; `_Runner.reprendre` (relit `answers.jsonl`, `applicability.json`, repère les Questions interrompues) ; `_Runner.compter` (décompte du manifeste depuis les Réponses effectives) ; `_cellule` saute les clés présentes (avant `check()` et index si la cellule est complète).
- `src/wavelibrarian/runner/resume.py` (nouveau) : `verifier_reprise` (code 2 : Exécution introuvable ou terminée, Gel différent, empreinte différente), `charger_resolue` (`experiment.resolved.yaml` relu comme `ResolvedExperiment`), `cles_tracees`.
- `src/wavelibrarian/runner/rundir.py` : `read_answers` (dernière ligne d'une clé), `reopen_run_dir` (manifeste `running`, sans `finished_at`, `resumptions`).
- `src/wavelibrarian/measure/tracing.py` : `Tracer.reprises` et attribut de span `wl.resumed`.
- `src/wavelibrarian/cli.py` : option `wl run --reprendre <run_id>`, contrôle de la reprise avant le préflight (code 2).
- Tests : `tests/unit/runner/test_story_4_8.py`. `test_story_4_4.py::test_plafond_atteint_code_3_et_manifeste_budget_exceeded` attend désormais les lignes `budget_exceeded`, que la 4.4 reportait à la 4.8.

## Design Notes

- Lecture fidèle d'AC 2 et d'AC 4 : l'empreinte de `experiment.sha256` couvre `budget` (`config/resolve.py::fingerprint`), alors que la reprise doit accepter un plafond relevé. `verifier_reprise` compare donc l'Expérience demandée à l'empreinte écrite **à plafonds égaux** (le `budget` de l'Expérience relue est substitué avant le calcul). Tout autre écart (graine, Configurations, split, modèles, Corpus…) est refusé en code 2. Les fichiers `experiment.resolved.yaml` et `experiment.sha256` ne sont pas réécrits ; le plafond en vigueur est consigné dans `manifest.json` (`resumptions`).
- `answers.jsonl` reste en ajout seulement. Une ligne `budget_exceeded` n'est pas une clé « présente » : la reprise la repose et ajoute une nouvelle ligne ; la dernière ligne d'une clé fait foi (`read_answers`, à réutiliser par le Rapport et le Panel). Les autres statuts (`ok`, `error`, `inapplicable`) sont sautés. Si le plafond rebloque, les clés déjà `budget_exceeded` ne sont pas réécrites.
- Les Réponses d'une cellule sont écrites à la fin de sa phase (4.5). Un plafond atteint les écrit avant l'arrêt ; un arrêt brutal les perd avec les spans locaux retenus, et la reprise repose alors toute la cellule depuis le Cache de réponses (coût 0). Les appels payés d'une Question non terminée restent dans `traces.jsonl` (source des coûts) ; leur rejeu porte `wl.resumed: true` (cache hit sur une Question tracée sans Réponse). Le Rapport (4.11, 4.12) compte alors cet appel et sa latence une seule fois : il ignore les spans `wl.resumed` hors coût (qui est de 0).
- Verrou puis registre : `Context(execution=True)` prend `run.lock` puis règle toute réservation ouverte à l'estimé (`recover_orphans`), avant `reopen_run_dir`. Une reprise concurrente sort en 1 (« Exécution <run_id> en cours ») sans toucher au dossier.
- Ordre de la CLI : validation, Gel, Paliers, contrôle de la reprise (code 2), préflight (code 4), exécution (codes 1 et 3).
- Écart assumé (AC 3 contre AC 2) : après un arrêt brutal, la réservation orpheline est réglée à l'estimé dans le registre. Si l'arrêt tombe pendant l'appel, aucun span ne la porte ; s'il tombe pendant le règlement, le span porte le coût réel. Dans les deux cas la somme des `wl.cost` diffère du registre de l'écart estimé moins tracé, pour cet appel seulement. Elle égale la dépense du registre pour un arrêt au plafond (AC 2). Une réponse reçue et conforme au schéma est mise en cache même si le règlement est interrompu (`MeteredGateway._cacher_si_conforme`) : la reprise ne la repaie pas.
- Empreintes d'entrée (revue) : `experiment.sha256` ne couvre que les chemins. Le manifeste porte donc `inputs` (`corpus_fingerprint` du Corpus ingéré, `scenario_fingerprint` du Corpus après Scénario, `catalog_fingerprint` du Catalogue entier, tarifs compris), comparé à la reprise : tout écart sort en code 2.
- Reprise d'une Exécution `completed` : code 0 et « rien à reprendre » (la CLI vérifie d'abord Gel, empreinte et entrées ; une Expérience différente sort toujours en 2). `run_experiment` appelé directement refuse encore (`ConfigError`).

## Tâches et critères

- [x] AC 1 : sixième appel refusé avant émission (5 réservations réglées, un span `budget_refused`), Réponses déjà produites conservées, Questions non traitées `budget_exceeded` (y compris celles des Configurations non atteintes), manifeste `budget_exceeded`, code 3 : `test_sixieme_appel_refuse_les_restantes_budget_exceeded_et_code_3`.
- [x] AC 2 : reprise qui saute les clés présentes et ne fait que les appels manquants, `answers.jsonl` et `traces.jsonl` seulement complétés, somme des `wl.cost` = dépense du registre pour le `run_id` : `test_reprise_saute_les_cles_presentes_et_ne_fait_que_les_appels_manquants`. Appels refaits sortis du cache à coût nul : `test_arret_brutal_reservation_orpheline_reglee_puis_running_et_completed` (cache hits `wl.cost` = 0). Nouvel arrêt sans doublon de lignes : `test_un_nouvel_arret_n_ecrit_pas_deux_fois_les_budget_exceeded`.
- [x] AC 3 : arrêt brutal simulé, réservation orpheline réglée à l'estimé, manifeste `running` puis `completed` : `test_arret_brutal_reservation_orpheline_reglee_puis_running_et_completed`.
- [x] AC 4 : empreinte différente refusée en code 2 (`seed`, `configurations`, `split`) : `test_reprise_d_une_experience_differente_refusee_code_2` ; Exécution inconnue ou terminée : `test_reprise_d_une_execution_inconnue_ou_terminee_refusee_code_2` ; Gel différent : `test_reprise_apres_degel_du_jeu_refusee_code_2`. Plafond relevé accepté : test d'AC 2.
- [x] AC 5 : seconde commande pendant une Exécution, code 1 et « Exécution <run_id> en cours », dossier intact : `test_reprise_pendant_une_autre_execution_code_1_et_dossier_intact` (cas sans reprise : `test_second_wl_run_code_1_sans_regler_les_reservations_du_premier`, 4.4).
- [x] Report 4.3 : `experiment.resolved.yaml` relu comme `ResolvedExperiment` (parser composite `markdown+pdf_text` accepté tel quel) : `charger_resolue`, exercé par tous les tests de reprise.
- [x] Report 4.5 : spans `query` d'une Question interrompue non comptés deux fois : `wl.resumed`, test d'arrêt brutal.
- [x] Report 4.4 : Questions restantes en `budget_exceeded` : test d'AC 1 et `test_plafond_atteint_code_3_et_manifeste_budget_exceeded` (4.4, mis à jour).
- [x] Lecture « dernière ligne d'une clé » : `test_read_answers_la_derniere_ligne_d_une_cle_fait_foi`.

## Auto Run Result

- Statut : review. Vérifications et décompte des tests : voir le rapport de l'orchestrateur.
- Reports traités : relecture de `experiment.resolved.yaml` (4.3), spans `query` non recomptés (4.5), Questions restantes `budget_exceeded` (4.4), réservation orpheline réglée à la reprise (1.8, 3.2).
- Reports non traités : libération manuelle d'une réservation `hors_execution` orpheline (ne relève pas de la reprise : elle compte déjà à l'estimé et ne fait jamais dépasser un plafond) ; reprise de `verdicts.jsonl` et de `panel.jsonl` : story 4.9 ; Rapport partiel avant le code 3 : story 4.11.
- Convention à reprendre par 4.9 et 4.11 : lire les Réponses par `read_answers` (la dernière ligne d'une clé fait foi, `budget_exceeded` jamais jugé) ; ignorer les spans `wl.resumed` pour les appels et la latence.
- Risque : la reprise est refusée si l'Expérience résolue change d'un détail sans rapport avec le plafond (par exemple une mise à jour du Catalogue qui change `catalog_date` ou `models_frozen_at`) : c'est voulu, mais à signaler à Anaël si le cas se présente.

## Revue

Revue Opus du 2026-10-18, après rebase sur `main` (7.1), sans conflit.

- medium, second avis 1 (règlement interrompu) : corrigé. Une réponse payée dont le `settle` échoue est mise en cache si elle est conforme au schéma ; la 4e Question n'est plus repayée à la reprise. L'écart registre / traces de l'appel orphelin (estimé contre réel) est inhérent à AC 3 et documenté. Tests : `test_arret_brutal_reel_manifeste_failed_puis_reprise_sans_repayer`, `test_reglement_interrompu_ne_cache_que_les_succes_de_schema`.
- medium, second avis 2 (contenu du Corpus et du Scénario) : corrigé. `inputs.corpus_fingerprint` et `inputs.scenario_fingerprint` au manifeste, comparés à la reprise (code 2). Test : `test_reprise_refusee_si_le_contenu_du_corpus_change`.
- medium, second avis 3 (Catalogue) : corrigé. `catalog_date` et `models_frozen_at` étaient couverts, pas les tarifs ; `inputs.catalog_fingerprint` couvre le Catalogue entier. Test : `test_reprise_refusee_si_un_tarif_du_catalogue_change`.
- low, second avis 4 (`experiment.sha256` hors `try`, `--reprendre ../x`) : corrigé, code 2 dans les deux cas (`run_id` validé par `RUN_ID`).
- low, second avis 5 (dernière ligne tronquée de `answers.jsonl` / `traces.jsonl`) : reporté. Ignorer la ligne ne suffit pas : l'ajout suivant se collerait à la ligne tronquée faute de saut de ligne final, et le contrat (§5, append-only) ne dit rien. À traiter avec les lecteurs du Rapport (4.11) : tolérer une ligne invalide non terminée et terminer le fichier par `
` avant d'ajouter.
- low, second avis 6 (`budget_exceeded` sur des cellules jamais vérifiées) : rejeté. Une cellule non atteinte n'a pas été traitée faute de budget ; la reprise la vérifie et l'écrit `inapplicable` si besoin (la dernière ligne fait foi).
- low, second avis 7 (`applicability.json` écrit seulement en `finally`) : corrigé, réécrit dès qu'une Configuration est jugée inapplicable.
- low, second avis 8 (reprise d'un run `completed`) : corrigé, code 0 et « rien à reprendre » ; §8 ne fixe rien, et une relance de run de nuit doit être idempotente.
- low, second avis 9 (test d'arrêt brutal qui fabrique son état) : corrigé, test du chemin réel (`set_status("failed")` puis reprise).
