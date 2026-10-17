---
story: "1.9"
title: Passerelle mesurée
status: review
---

# Story 1.9 : Passerelle mesurée

## Code Map

- `src/wavelibrarian/llm/gateway.py` : `MeteredGateway` (`complete`, `complete_structured`), seul module (avec `preflight` à venir) à importer `llm.providers`.
- `src/wavelibrarian/llm/providers/base.py` : protocole `Provider` (`complete(request, *, timeout_s)`) et `ProviderResponse(text, usage)`.
- `src/wavelibrarian/runner/wiring.py` : `build_gateway(...)`, câblage depuis un profil (`make_tokenizer`, `tokenizer_for`, `make_estimator`, `call_timeout_s`). `llm` et `measure` sont deux couches sœurs : seul `runner` peut les joindre.
- `tests/unit/llm/test_gateway.py`.

## Design Notes

- Ordre : marqueur `[[wl:role=…]]` (refus `WlError` si le Composant l'a déjà posé), `cache_key` après marquage, lecture du cache, estimation, `reserve`, appel, coût du Catalogue, `settle`, `put`, span.
- Estimation : tokens du `tokenizer_for(model)` ; `token_factor` appliqué par la passerelle seulement si le Catalogue déclare `tokenizer: reference` (sinon `tokenizer_for` l'a déjà appliqué, pas de double compte) ; plus `max_tokens` en sortie ; coût par `ModelCatalog.cost` (palier compris). Un prompt cacheable (`cache_system` ou `Message.cache` sur un modèle `prompt_cache`) est compté au tarif d'écriture de cache, majorant.
- Essais : `tenacity` (`Retrying`, `wait_exponential(backoff_s, max_backoff_s)`, `stop_after_attempt(max_attempts)`), seules les `ProviderError(retryable=True)` sont réessayées ; `sleep` et `timer` injectables. Une seule réservation couvre tous les essais. Échec final : `release`, span `wl.status=error`, exception relancée.
- Plafond : `BudgetExceeded` de `reserve` produit un span `budget_refused` (coût 0) avant de remonter, sans appel.
- Cache : seuls les succès sont stockés. En structuré, la sortie est validée avant `put` ; le second essai saute la lecture du cache (sinon il relirait la même sortie) ; une sortie non conforme est tracée `non_conformant` à chaque essai, payée et réglée, jamais mise en cache. Limite : si une sortie invalide était déjà en cache (via `complete`), `put` (`INSERT OR IGNORE`) ne la remplace pas.
- Modèle local : coût 0, devise `EUR` (coût de possession). Énergie : `FakeEstimator`/`EcoLogitsEstimator` pour un modèle d'API (`wl.energy_method=estimated` et `wl.energy_kwh`, ou `unknown` sans valeur) ; pour un modèle local, `unknown` (mesure par phase répartie par le runner, AD-17) ; un hit de cache n'a pas d'attribut d'énergie.
- Délai : `request.timeout_s`, sinon `call_timeout_s` du profil.
- `cache_write_1h` : non facturé (`Usage` n'a pas de poste 1 h, le contrat actuel n'en demande pas) ; reporté tant que les providers (1.11) n'écrivent que le cache 5 min.

## Tâches et critères

- [x] Marqueur de rôle posé par la passerelle ; 1er appel réserve, règle au coût du Catalogue (`Decimal`), stocke, span `wl.llm_cache_hit=false` ; 2e servi du cache (`cost` 0, `cost_uncached` = coût 1, hit `true`, sans réservation) : `test_deux_appels_identiques`, `test_composant_qui_pose_le_marqueur_est_refuse`, `test_le_role_entre_dans_la_cle`.
- [x] Solde insuffisant : span `budget_refused`, `BudgetExceeded`, provider non appelé : `test_budget_refuse_sans_appel` ; estimation tokens × `token_factor` + `max_tokens`, palier : `test_estimation_applique_token_factor`, `test_estimation_palier_tarifaire`, `test_prompt_cacheable_estime_au_tarif_d_ecriture`.
- [x] Deux erreurs retryables puis succès au 3e essai, attente exponentielle ; non retryable non réessayée, réservation libérée : `test_deux_erreurs_retryables_puis_succes`, `test_erreur_non_retryable_libere_la_reservation`, `test_essais_epuises`, `test_reglement_au_cout_reel`.
- [x] `complete_structured` : deux sorties non conformes, réessai une fois puis `NonConformantOutput`, span `non_conformant` : `test_sortie_non_conforme_deux_fois`, `test_sortie_conforme_au_second_essai`, `test_sortie_invalide_en_cache_est_contournee_au_second_essai`.
- [x] `lint-imports` : seuls `llm.gateway` et `llm.preflight` importent `llm.providers` : contrat « Providers atteints par la seule passerelle » vérifié par `tests/unit/test_garde_fous.py::test_lint_imports_passe` (la passerelle importe `llm.providers.base`).
- [x] Reports 1.4/1.7/1.8 : câblage du profil et de l'estimateur (`test_build_gateway_depuis_le_profil_test`), énergie (`test_energie_estimee_par_appel`, `test_modele_local_cout_nul_et_energie_inconnue`), succès seuls en cache (`test_seuls_les_succes_sont_mis_en_cache`).

## Auto Run Result

- Statut : prêt pour revue.
- Reports traités : `tokenizer_for`/`make_tokenizer`/`Tracer` câblés (`runner/wiring.py`) ; `token_factor` dans l'estimation ; `wl.energy_*` ; `cache_key` après `role_marker` ; succès seuls en cache ; `cache_write_1h` consigné (non facturé).
- Reports restants : `RunContext` concret (epic 4) doit exposer `tokenizer_for(model_id)` et appeler `build_gateway` ; `run.lock` et `recover_orphans=True` (runner) ; énergie locale par phase (runner) ; providers réels (1.11) et Faux LLM (1.10) à brancher dans `providers`.
- Aucun réseau, Ollama ni GPU ; threads à 4.
