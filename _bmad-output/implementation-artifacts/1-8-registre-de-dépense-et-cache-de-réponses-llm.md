---
story: "1.8"
title: Registre de dépense et Cache de réponses LLM
status: review
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
- Réservations orphelines : réglées à l'estimation à l'ouverture (`recover_orphans=True`), valable car `run.lock` garantit une seule Exécution (AD-11). `recover_orphans=False` pour les tests de concurrence.
- `settle` peut dépasser l'estimation (appel déjà payé) ; `settle`/`release` d'une réservation déjà close lèvent `WlError`.
- Clé du cache : `sha256(canonical_json({model, params{max_tokens, temperature, seed}, system, messages(role, content), pass_id}))`. `step`, `role`, `cache_system`, `Message.cache`, `timeout_s` hors clé. `inputs` entre dans la clé seulement si `provider == "fake"` (paramètre explicite de `cache_key`). La passerelle (1.9) doit passer le `system` déjà marqué `[[wl:role=…]]`.
- Contradiction d'énoncé : le 2e scénario somme deux Exécutions de 1,50 (3,00) sous un plafond de période qui serait de 2,00 comme au 1er scénario, ce qui refuserait la 2e. Lecture retenue : plafond de période de 3,00 dans ce scénario (3,00 + 0,10 refusé ; accepté au mois suivant).

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
