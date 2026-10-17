---
story: "1.9"
title: Passerelle mesurée
status: done
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
- Cache : seuls les succès sont stockés. En structuré, la sortie est validée avant `put` ; le second essai saute la lecture du cache (sinon il relirait la même sortie) ; une sortie non conforme est tracée `non_conformant` à chaque essai, payée et réglée, jamais mise en cache. Si une sortie invalide était déjà en cache (via `complete`), la sortie conforme du second essai la remplace (`put(..., replace=True)`).
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

## Revue

Revue Opus en une passe (base `a44bf20`, commit `c9130f8`), liste du second avis vérifiée point par point.

- medium, second avis 1 et 7 : **corrigé**. Une sortie invalide en cache n'était jamais remplacée (`INSERT OR IGNORE`), chaque `complete_structured` repayait un appel (reproduit : 1 `complete` puis 3 `complete_structured` = 4 appels). `ResponseCache.put(..., replace=True)` sur l'essai qui contourne le cache ; le test compte désormais 2 appels et échoue sur l'ancien code.
- medium, second avis 2 et 4 : **corrigé**. Un échec de `catalog.cost`, de `settle` ou de `cache.put` après un appel payé ne laissait aucun span. Désormais : coût réel, à défaut l'estimation, réglé puis tracé `wl.status=error` ; le span `ok` part avant `put`. Tests `test_cout_introuvable_apres_appel_paye_trace_l_estimation`, `test_panne_du_cache_ne_perd_pas_le_span`. Un échec du Tracer lui-même reste sans span (rien d'autre à écrire).
- medium, second avis 3 : **rejeté, reporté à 1.11**. Le contrat (spine §Passerelle, AD-9 : « réserver, puis régler ou libérer », une réservation pour « 3 essais ») est suivi, et la réservation reste ouverte pendant les essais, donc comptée au plafond. Seul un délai dépassé après envoi peut être facturé : à l'adaptateur `anthropic` (1.11) de le signaler, et à la passerelle de régler alors à l'estimation au lieu de libérer. Vérification à faire en 1.11 avec un vrai appel interrompu.
- low, second avis 5 : **consigné**. L'estimation ignore le schéma de `complete_structured` ; son poids dépend de la façon dont 1.11 l'envoie (outil ou `format`), à intégrer à ce moment.
- low, second avis 6 : **corrigé**. `contracts.md` précise que `tokens_for` compte le corpus sans facteur et que l'estimation de la passerelle applique `token_factor` une fois.
- low, second avis 9 : **consigné**. Un plafond `ollama` dans une autre devise qu'EUR lève `ConfigError` à chaque appel local ; erreur explicite, à refuser plutôt à la validation de l'Expérience (epic 4).
