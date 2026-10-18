---
story: "4.5"
title: "Mesure de l'Exécution : postes, latence, énergie et rejeu"
status: done
---

# Story 4.5 : Mesure de l'Exécution : postes, latence, énergie et rejeu

## Code Map

- `src/wavelibrarian/runner/execute.py` : `_Runner.poser` (Question posée dans `ctx.scope(post="query", question_id=...)`, span `local` `answer` émis par le runner avec `wl.invalid_citations`, `Answer.latency_s`) et `_Runner.energie_de_phase` (relevé du mesureur par phase et par Configuration). Le mesureur vient de `make_meter(profil.energy)`.
- `src/wavelibrarian/measure/tracing.py` : `Tracer.begin_phase` / `end_phase(kwh, méthode)` (retient les spans locaux d'une phase, les répartit par `spread_energy`, puis les écrit) et `Tracer.latency_total` (latence cumulée de tous les spans).
- `src/wavelibrarian/runner/index_cache.py` : `load` passe sous le Poste `indexing` ; la latence du span `index` exclut celle des spans déjà tracés pendant la construction.
- `src/wavelibrarian/runner/context.py` : `Context.traceur` (Tracer concret réservé au runner ; `Context.tracer` garde le type du port).
- Tests : `tests/unit/runner/test_story_4_5.py`.

## Design Notes

- `traces.jsonl` n'étant jamais réécrit et l'énergie d'une phase n'étant connue qu'à sa fin, le Tracer retient les spans locaux de la phase (kinds `local`, `embed`, `rerank`, et `llm` du provider `ollama`) et les écrit à `end_phase` avec `wl.energy_kwh` et `wl.energy_method`. Hors phase ouverte, `record` écrit tout de suite. Les spans d'API (EcoLogits, par appel) ne sont pas retenus. Un span écrit en fin de phase garde ses bornes d'origine, mais l'ordre des lignes n'est plus l'ordre chronologique.
- Deux phases par Configuration : `index` (construction, `load` et span `index`) et `query` (toutes les Questions). La phase se ferme dans un `finally` : une exception ou un plafond atteint n'efface aucun span retenu.
- Latence : le span `answer` porte le temps propre de `answer` (durée murale moins la latence des spans tracés pendant l'appel : passerelle, embedding). `Answer.latency_s` = latence de ces spans + temps propre, c'est-à-dire la somme des `wl.latency_s` des spans `query` de la Question. Aucun double compte, ni de la latence, ni de l'énergie. Même règle pour le span `index`.
- Une Question en `error` émet son span `answer` (`wl.status=error`, `invalid_citations` 0) et garde sa latence. Un `BudgetExceeded` n'émet pas de span `answer` (le span `budget_refused` de la passerelle suffit) et la phase se ferme. Les Réponses `inapplicable` et les Configurations en échec n'émettent pas de span et ont une latence de 0.
- Énergie sans valeur : `wl.energy_method=unknown`, pas de `wl.energy_kwh` (contrat §6). Énergie relevée mais aucune durée (somme des latences nulle) : répartie à parts égales (revue).
- Rejeu : les caches d'index et de réponses de `WL_HOME` font le travail. Un hit du Cache de réponses retrace la latence de l'appel d'origine (colonne `latency_s` de `llm_cache.sqlite`, review-reconcile §1) ; `Tracer.elapsed_total` (temps réellement passé, hits exclus) sert au temps propre et au prorata d'énergie, `Tracer.latency_total` à `Answer.latency_s`.

## Tâches et critères

- [x] AC 1 : `wl.post=indexing` sur `index` et `load`, `query` sur `answer`, fixés par `ctx.scope` du runner : `test_postes_fixes_par_le_runner_et_span_answer_par_question`, `test_load_est_impute_a_l_indexation`.
- [x] AC 1 : un span `local` `answer` par Question, émis par le runner, avec `wl.question_id` et `wl.invalid_citations` (FR-18) : `test_postes_fixes_par_le_runner_et_span_answer_par_question`, `test_citations_invalides_comptees_dans_le_span_answer`.
- [x] AC 2 : `latency_s` de chaque `Answer` = somme des `wl.latency_s` des spans `query` de la Question : `test_latency_s_egale_somme_des_spans_query_de_la_question`, `test_latence_positive_pour_une_reponse_ok`.
- [x] AC 3 : énergie `fake` relevée par phase et par Configuration, répartie au prorata de la latence, avec `wl.energy_method` : `test_energie_fake_relevee_par_phase_et_repartie_au_prorata`, `test_phase_sans_duree_energie_a_parts_egales`, `test_phase_deja_ouverte_refusee`, `test_question_en_erreur_garde_son_span_answer_et_la_phase_se_ferme`.
- [x] AC 4 : même Expérience relancée avec les mêmes caches, `answers.jsonl` identiques (hors `answer_id` et `latency_s`), aucun coût non nul, `wl.index_cache_hit=true` et `wl.llm_cache_hit=true` : `test_rejeu_memes_reponses_aucun_cout_caches_servis`.

## Auto Run Result

- Statut : review. Vérifications : voir le rapport de l'orchestrateur.
- Reports traités : énergie locale par phase (`spread_energy`) ; span `answer` et `latency_s` laissés par la 4.4 ; `load` imputé à `indexing` (il était hors `ctx.scope`).
- Reports laissés : relevé réel codecarbon (`gpu_ids=[]`, noms `_hardware`/`_mode`, `estimated` sous Windows) après le run autonome ; `token_factor` à l'estimation (déjà fait par la passerelle en 1.9, rien à faire ici) ; phase `update` (story 4.7) et énergie du Poste `judging` (story 4.9) ; énergie du Rapport (story 4.12) ; plafond `ollama` hors EUR à la validation et réservation `hors_execution` orpheline (non traités).
- Écarts : les spans locaux d'une phase sont écrits à la fin de la phase, donc hors ordre chronologique dans `traces.jsonl`. Une Architecture qui lirait `traces.jsonl` en cours de phase ne verrait pas ses propres spans locaux. Le contrat §6 ne fixe pas d'ordre.
- Risque : l'énergie `measured` n'est jamais exercée ici (codecarbon absent) ; `CodecarbonMeter.method` est lu après `stop()` par `getattr`.

## Revue

Revue Opus du 2026-10-18, après rebase sur `main` (story 6.1). Second avis Haiku repris point par point.

- medium, second avis 1, corrigé : `meter.start()` levait après `begin_phase()` hors du `try`, la phase restait ouverte et toutes les Configurations suivantes échouaient en « phase déjà ouverte » (reproduit). `start` passe dans le `try` qui referme la phase : `test_echec_du_mesureur_ne_laisse_pas_la_phase_ouverte`.
- medium, second avis 2, corrigé : les Réponses de la phase query étaient écrites avant leurs spans locaux retenus ; un arrêt dur laissait des Réponses sans span `answer` ni énergie, que la reprise ne réémet pas. Les Réponses sont retenues et écrites juste après `end_phase` (callback `apres`), jamais si l'écriture des spans échoue : `test_reponses_ecrites_apres_les_spans_de_leur_phase`. Coût : un arrêt dur fait reposer toute la phase query de la Configuration, depuis les caches.
- medium, second avis 3, corrigé : review-reconcile §1 exige la latence d'origine pour les hits du cache LLM (sinon p50/p95 valent 0 au rejeu et à la reprise). `llm_cache.sqlite` gagne une colonne `latency_s` (ajoutée par `ALTER TABLE` sur un cache existant, 0 pour les anciennes entrées), la passerelle la retrace au hit ; le temps propre et le prorata d'énergie utilisent `elapsed_total`, qui exclut les hits : `test_rejeu_retrace_la_latence_d_origine_des_appels_llm`, `test_hit_du_cache_hors_temps_ecoule_et_hors_energie`, `test_cache_garde_la_latence_d_origine`, `test_cache_d_avant_la_latence_migre`.
- low, second avis 4, corrigé : temps propre négatif ramené à 0 avec un avertissement (`measure.tracing.temps_propre`, partagé par `poser` et le span `index`).
- low, second avis 5, reporté (4.8) : la Question interrompue par `BudgetExceeded` n'a ni span `answer` ni Réponse ; cohérent (la reprise la repose), mais la 4.8 doit vérifier que sa reprise ne compte pas deux fois les spans `query` déjà émis pour cette Question (dédoublonnage par clé, review-adversarial).
- low, second avis 6, corrigé : un échec de `meter.stop()` ou de `end_phase` pendant une exception en vol est journalisé et ne remplace plus l'exception (un `BudgetExceeded` reste un plafond) : `test_fin_de_phase_en_echec_ne_masque_pas_le_plafond`, `test_fin_de_phase_en_echec_sans_exception_remonte`.
- low, second avis 7, corrigé : énergie relevée sur une phase sans durée répartie à parts égales au lieu d'être perdue (`spread_energy`).
- low, second avis 8, corrigé : tests renforcés avec chaque correctif ; chacun échoue sans le correctif côté `src` (vérifié).
- low, revue, reporté (story du Rapport) : un hit du cache porte désormais une latence d'origine dans `wl.latency_s` et des bornes `start_time`/`end_time` fictives ; le Coût de possession (durée des spans locaux × matériel) doit exclure les spans `wl.llm_cache_hit=true`, sinon un rejeu coûterait du temps machine.
- Rebase sur `main` : sans conflit.
