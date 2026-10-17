---
story: "1.8"
title: Registre de dépense et Cache de réponses LLM
status: done
---

# Story 1.8 : Registre de dépense et Cache de réponses LLM

## Code Map

- `src/wavelibrarian/llm/budget.py` : `Ledger` (`reserve`, `settle`, `release`, `balance`, `recover_orphans`), `Balance`.
- `src/wavelibrarian/llm/cache.py` : `cache_key`, `ResponseCache` (`get`, `put`), `CachedResponse`.
- `src/wavelibrarian/llm/_db.py` : connexion SQLite, `transaction` (`BEGIN IMMEDIATE`), `resolve_wl_home`.
- `tests/unit/llm/test_ledger_cache.py`.

## Design Notes

- `ledger.sqlite` : une table `reservations` (Exécution, fournisseur, devise, mois UTC, estimé, réel, statut). Montants en chaîne `Decimal`. Plafond par Exécution = réglé + réservé de l'Exécution ; plafond de période = idem sur le mois civil UTC (mois pris à la réservation, horloge injectée), toutes Exécutions confondues. Fournisseur sans plafond : non limité. Devise de la réservation différente de celle du plafond : `ConfigError`.
- Toute écriture passe par `transaction()` (`BEGIN IMMEDIATE`, `ROLLBACK` sur exception). Une réservation refusée n'écrit rien.
- Réservations orphelines : réglées à l'estimation à l'ouverture par `Ledger(..., recover_orphans=True)`, que seul le runner passe, après avoir pris `run.lock` (AD-11). Par défaut `False` : une ouverture simple (affichage du solde, autre processus) ne touche pas aux réservations en cours. Une orpheline non récupérée compte déjà à l'estimation, donc aucun plafond n'est dépassé.
- Sommes filtrées par devise ; des dépenses non libérées dans une autre devise sur l'Exécution ou le mois courant lèvent `ConfigError`. Horloge naïve refusée (`ValueError`).
- `settle` peut dépasser l'estimation (appel déjà payé) ; `settle`/`release` d'une réservation déjà close lèvent `WlError`.
- Clé du cache : `sha256(canonical_json({model, params{max_tokens, temperature, seed}, system, messages(role, content), pass_id}))`. `step`, `role`, `cache_system`, `Message.cache`, `timeout_s` hors clé. `inputs` entre dans la clé seulement si `provider == "fake"` (paramètre explicite de `cache_key`). `cache_key` exige que `system` commence par `role_marker(request.role)` (`ValueError` sinon) : la passerelle (1.9) marque avant de calculer la clé, et c'est ce marqueur qui fait entrer le rôle dans la clé.
- Contradiction d'énoncé (à arbitrer par Anaël) : le 2e scénario somme deux Exécutions de 1,50 (3,00) sous un plafond de période qui serait de 2,00 comme au 1er scénario, ce qui refuserait la 2e. Lecture retenue : plafond de période de 3,00 dans ce scénario (3,00 + 0,10 refusé ; accepté au mois suivant).

## Tâches et critères

- [x] Réserver 0,60, régler 0,40, réserver 0,70 refusé, solde 0,60 : `test_reserver_regler_puis_refus`.
- [x] Chaque écriture en `BEGIN IMMEDIATE` : `test_ecriture_toujours_dans_begin_immediate`, `test_reserver_regler_puis_refus` (COMMIT/ROLLBACK).
- [x] Plafond de période, puis accepté au mois suivant (horloge injectée) : `test_plafond_de_periode_et_mois_suivant`.
- [x] Orpheline réglée à l'estimation après réouverture : `test_reservation_orpheline_reglee_a_l_estimation` ; libérée ne compte plus : `test_reservation_liberee_ne_compte_plus`.
- [x] Devises et plafonds par fournisseur : `test_devises_et_plafonds_par_fournisseur`, `test_plafond_par_execution_isole_les_executions`.
- [x] Concurrence (4 threads, 2 processus) sans dépassement : `test_concurrence_threads_jamais_au_dela_du_plafond`, `test_concurrence_deux_processus`.
- [x] Stockage/relecture texte + `Usage` : `test_cache_relit_texte_et_usage`.
- [x] Clé sensible à `pass_id`, message, `temperature`, pas à `step` : `test_cle_sensible_a_pass_id_message_temperature_pas_a_step`.
- [x] `inputs` dans la clé pour `fake` seulement : `test_inputs_dans_la_cle_seulement_pour_le_provider_fake`.
- [x] `WL_HOME` : `test_wl_home_par_variable_d_environnement`.

## Auto Run Result

- Statut : prêt pour revue. Contradiction de plafond de période signalée dans Design Notes.
- Reports : 1.9 doit estimer (tokens × `token_factor` + `max_tokens`, palier), appeler `reserve`/`settle`/`release`, ouvrir `Ledger` avec `Budget` de l'Expérience et le `run_id`, et passer le provider à `cache_key`. Le cache ne stocke ni coût ni latence : `cost_uncached` se recalcule par le Catalogue.
- Aucun réseau, Ollama ni GPU ; threads à 4.

## Revue

Revue Opus du 2026-10-17, second avis Haiku vérifié point par point.

- medium, second avis 1, corrigé : `recover_orphans=True` par défaut réglait à l'ouverture les réservations en cours d'une autre instance (test : le `settle` suivant levait « réservation inconnue »). Défaut passé à `False`, mot-clé seulement, à poser par le runner sous `run.lock` ; tests `test_ouverture_simple_ne_regle_pas_les_reservations_en_cours` et orpheline réglée puis close.
- medium, second avis 2, corrigé : sommes filtrées par devise, et `ConfigError` si l'Exécution ou le mois porte des dépenses dans une autre devise (`test_changement_de_devise_en_cours_de_mois_refuse`).
- medium, second avis 3, corrigé : le contrat (contracts.md §3, contexte d'epic) fait porter le rôle par le marqueur posé avant le cache ; la précondition est désormais vérifiée dans `cache_key` (`role_marker`, `ValueError`), testée.
- low, second avis 4, rejeté : un `model_id` du Catalogue désigne un seul provider (`ModelEntry.provider`), la clé ne peut pas mêler deux providers.
- low, second avis 5, rejeté : la passerelle ne met en cache qu'une réponse réussie ; un texte vide peut être une réponse légitime.
- low, second avis 6, rejeté : `balance()` sert à l'affichage ; le contrôle du plafond se fait dans la transaction de `reserve`.
- low, second avis 7, corrigé : connexion fermée si l'initialisation lève (Ledger et ResponseCache).
- low, second avis 8, corrigé : l'`assert all(...)` remplacé par un parcours qui vérifie que chaque écriture est dans une transaction `BEGIN IMMEDIATE`.
- low, second avis 9, rejeté : avec une transaction différée, la montée en écriture concurrente lève `database is locked` sans attendre, et le test échouerait ; il distingue donc bien les deux.
- low, second avis 10, corrigé : horloge naïve refusée (`test_horloge_naive_refusee`).
- info, orchestrateur, à arbitrer par Anaël : AC 2 contradictoire (2 × 1,50 sous un plafond de période de 2,00) ; test écrit avec un plafond de période de 3,00.

### Reports pour la 1.9 et le runner

- Le runner ouvre le `Ledger` avec `recover_orphans=True` seulement après avoir pris `WL_HOME/run.lock` (non implémenté à ce jour) ; vérifier par un test qu'un second `wl run` ne règle pas les réservations du premier.
- La passerelle calcule `cache_key` après avoir posé `role_marker(role)` en tête du system, et réutilise `role_marker` plutôt qu'une seconde définition du format.

