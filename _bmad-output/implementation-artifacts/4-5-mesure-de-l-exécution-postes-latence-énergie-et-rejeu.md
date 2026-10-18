---
story: "4.5"
title: "Mesure de l'Exécution : postes, latence, énergie et rejeu"
status: review
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
- Énergie sans durée (somme des latences nulle) ou sans valeur : `wl.energy_method=unknown`, pas de `wl.energy_kwh` (contrat §6).
- Rejeu : aucun code propre. Les caches d'index et de réponses de `WL_HOME` font le travail ; le test le vérifie sur les spans.

## Tâches et critères

- [x] AC 1 : `wl.post=indexing` sur `index` et `load`, `query` sur `answer`, fixés par `ctx.scope` du runner : `test_postes_fixes_par_le_runner_et_span_answer_par_question`, `test_load_est_impute_a_l_indexation`.
- [x] AC 1 : un span `local` `answer` par Question, émis par le runner, avec `wl.question_id` et `wl.invalid_citations` (FR-18) : `test_postes_fixes_par_le_runner_et_span_answer_par_question`, `test_citations_invalides_comptees_dans_le_span_answer`.
- [x] AC 2 : `latency_s` de chaque `Answer` = somme des `wl.latency_s` des spans `query` de la Question : `test_latency_s_egale_somme_des_spans_query_de_la_question`, `test_latence_positive_pour_une_reponse_ok`.
- [x] AC 3 : énergie `fake` relevée par phase et par Configuration, répartie au prorata de la latence, avec `wl.energy_method` : `test_energie_fake_relevee_par_phase_et_repartie_au_prorata`, `test_phase_sans_duree_energie_inconnue`, `test_phase_deja_ouverte_refusee`, `test_question_en_erreur_garde_son_span_answer_et_la_phase_se_ferme`.
- [x] AC 4 : même Expérience relancée avec les mêmes caches, `answers.jsonl` identiques (hors `answer_id` et `latency_s`), aucun coût non nul, `wl.index_cache_hit=true` et `wl.llm_cache_hit=true` : `test_rejeu_memes_reponses_aucun_cout_caches_servis`.

## Auto Run Result

- Statut : review. Vérifications : voir le rapport de l'orchestrateur.
- Reports traités : énergie locale par phase (`spread_energy`) ; span `answer` et `latency_s` laissés par la 4.4 ; `load` imputé à `indexing` (il était hors `ctx.scope`).
- Reports laissés : relevé réel codecarbon (`gpu_ids=[]`, noms `_hardware`/`_mode`, `estimated` sous Windows) après le run autonome ; `token_factor` à l'estimation (déjà fait par la passerelle en 1.9, rien à faire ici) ; phase `update` (story 4.7) et énergie du Poste `judging` (story 4.9) ; énergie du Rapport (story 4.12) ; plafond `ollama` hors EUR à la validation et réservation `hors_execution` orpheline (non traités).
- Écarts : les spans locaux d'une phase sont écrits à la fin de la phase, donc hors ordre chronologique dans `traces.jsonl`. Une Architecture qui lirait `traces.jsonl` en cours de phase ne verrait pas ses propres spans locaux. Le contrat §6 ne fixe pas d'ordre.
- Risque : l'énergie `measured` n'est jamais exercée ici (codecarbon absent) ; `CodecarbonMeter.method` est lu après `stop()` par `getattr`.
