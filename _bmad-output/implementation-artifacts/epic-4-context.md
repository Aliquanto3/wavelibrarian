# Epic 4 Context: Comparer les Baselines de bout en bout et lire le Rapport

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Permettre à Anaël de lancer `wl run` sur une Expérience qui compare les trois Baselines (sans contexte, contexte long, BM25 seul), en Condition standard et contexte parfait, avec Scénario de mise à jour et Paliers de volume. L'Exécution s'arrête proprement au plafond de dépense et reprend sans repayer. Elle produit un Rapport complet : scores par Critère avec IC, comparaisons appariées, coûts et énergie par Poste, latence, point mort, Fraîcheur, fronts de Pareto exportables. L'epic pose aussi la suite de conformité commune qui valide toute Architecture future.

## Stories

- Story 4.1: Découpage, contexte étiqueté et Generator LLM
- Story 4.2: Baselines sans contexte, contexte long et BM25 seul
- Story 4.3: Cache d'index et dossier d'Exécution
- Story 4.4: Exécution d'une Expérience par `wl run`
- Story 4.5: Mesure de l'Exécution : postes, latence, énergie et rejeu
- Story 4.6: Condition contexte parfait et Paliers de volume
- Story 4.7: Phase après mise à jour
- Story 4.8: Arrêt au plafond et reprise d'une Exécution
- Story 4.9: Métriques de recherche, Critères automatiques et Panel de juges
- Story 4.10: Statistiques : bootstrap, McNemar et fronts de Pareto
- Story 4.11: Rapport : scores, recherche et comparaisons appariées
- Story 4.12: Rapport : coûts, énergie, latence et point mort
- Story 4.13: Rapport : Fraîcheur, Paliers, fronts de Pareto et export du front
- Story 4.14: Suite de conformité, Expériences livrées et test de bout en bout SM-3
- Story 4.15: Test réel SM-4 sur Claude Haiku 5.5

## Contraintes du run autonome

- Aucun réseau ni API dans les tests : Faux LLM (`fake-llm-a/b/c`), faux embedder, profil `test`.
- Seule la story 4.15 appelle la vraie API Anthropic (Haiku 5.5, 5 Questions, plafond 5 $), avec Juges et embedder factices.
- Ollama et GPU seulement après le go d'Anaël (`/api/tags` toléré au préflight) ; pas de `pytest -m real_local`, pas de `wl run` sur `mini-cpu.yaml`.
- Pas d'extra lourd (`local`, `docling`), pas de `wl installer`, pas de téléchargement de plus de 1 Go ; `OMP_NUM_THREADS=4`, RAM ≤ 6 Go, pas de pytest parallèle.

## Requirements & Constraints

- Une Expérience s'exécute par une seule commande ; la Configuration résolue et son empreinte sont écrites avant tout appel. Une Configuration inapplicable (contexte long au-delà de la fenêtre ou du palier tarifaire Haiku à 100 000 tokens) est marquée `inapplicable` avec sa raison, sans faire échouer les autres.
- Jeu non gelé ou modifié après Gel : refus avant tout appel (code 2). Seules les Questions `validated` et `corrected` de la partie demandée sont posées.
- Une erreur sur une Question est enregistrée (`status: error`) et n'arrête pas l'Exécution ; `max_questions` limite aux premières Questions par `id`.
- Reproductibilité : même graine et mêmes caches = mêmes Passages et Réponses, sans coût ; hors cache, seule l'identité des Passages est garantie.
- Plafond : refus de l'appel avant émission, Questions restantes `budget_exceeded`, manifeste `budget_exceeded`, code 3, Rapport partiel. Reprise par `--reprendre` ; empreinte différente = code 2 ; seconde exécution simultanée = code 1.
- Citation : étiquettes `[S1]…[Sn]` ; une Citation hors contexte est retirée et comptée (`invalid_citations`). Indicateur d'abstention distinct du texte. Contexte > 8 000 tokens : `context_texts` limité aux blocs cités (`context_truncated`).
- Critères : `citation_correctness`, `abstention_correctness`, `correctness` (exact_match en réponse courte) sans Juge ; `correctness`, `completeness`, `faithfulness` par Panel (un appel par Réponse et par Juge), majorité, égalité = non + `tie`. Pas de score global. Aucun Juge pour les Réponses `error`, `inapplicable`, `budget_exceeded`.
- Métriques de recherche : pertinence par recouvrement d'Ancrages ; `no_context` n'en a pas ; méthode (`ranked`, `provided`, `cited`, `none`) reportée.
- Statistiques : bootstrap 2 000 rééchantillons, 95 %, alpha 0,05, graine de l'Expérience ; McNemar exact ; comparaison sur les Questions communes (`n_common`) ; résultats vérifiés contre scipy.
- Rapport : calculé des seuls fichiers de l'Exécution, groupé par (config_id, condition, tier, phase) ; contaminées et contexte parfait à part ; énergies `measured` et `estimated` jamais additionnées ; `judging` et `evalset` hors coût d'une Configuration ; somme des `wl.cost` convertie = coût total affiché ; point mort seulement à Qualité égale ou supérieure et si requête_A < requête_B, sinon la raison ; fronts de Pareto en tête de `report.md`, sans pondération.
- SM-3 : `uv run pytest` sans réseau et Expérience sur le Mini-corpus avec les faux (toutes Baselines, Rapport complet). SM-4 : coût tracé = recalcul par le Catalogue au centime près ; aucune clé ni `x-api-key` dans `runs/<run_id>/`.

## Technical Decisions

- Couches : `runner` et `report` sont indépendants (`runner` n'importe jamais `report`) ; c'est `cli.py` qui enchaîne `wl run` puis le Rapport, y compris partiel avant le code 3. Seul le runner écrit les JSONL de l'Exécution (ajout seulement, UTF-8, LF).
- Architecture (`ports/architecture.py`) : `index(corpus, dir)`, `load(dir)`, `update(change, corpus_after, old_dir, new_dir)`, `answer(QuestionInput)`, `answer_with_context`, `check(profile)`, `index_key()`, `query_params`. Une Architecture ne reçoit que `QuestionInput` (jamais la Réponse de référence) ; le runner complète `ArchAnswer` en `Answer`. Elle ne trace jamais ; les spans LLM viennent de la passerelle.
- Cycle de vie piloté par le runner : parsing, `index` dans `.tmp-<clé>/`, `manifest.json`, `os.replace`, puis instance neuve + `load` (chemins cache présent et absent identiques) ; pour un Scénario, `update` vers la nouvelle clé sans toucher l'ancienne.
- `index_key = sha16(canonical_json({corpus_fingerprint, architecture, index_key()}))` ; défaut = Params moins `query_params`, plus parser résolu et nom du tokenizer. Dossier d'index : `passages.jsonl` + `manifest.json`.
- Postes de coût fixés par context manager du runner (`ctx.scope`) : `indexing`, `update`, `query`, `judging`, `evalset` ; un span `local` `index` par index chargé ou construit (`wl.index_cache_hit`), un span `local` `answer` par Question (`wl.invalid_citations`, `wl.question_id`). `latency_s` d'une Réponse = somme des `wl.latency_s` des spans `query`. Énergie locale relevée par phase puis répartie au prorata de la latence.
- `answer_id` : un par (config_id, condition, tier, phase, question_id), `tier = "all"` sans palier. Condition contexte parfait : un Passage `level 0` par Ancrage de référence (`anchor_text`), ordre des `reference_anchors`, vide pour `unanswerable`. Paliers : `required_paths` = Documents des Ancrages de référence, index par Palier avec sa clé.
- Fichiers d'Exécution (`runs/<run_id>/`) : `experiment.resolved.yaml`, `experiment.sha256`, `manifest.json`, `corpus_profile.json`, `answers.jsonl`, `verdicts.jsonl`, `panel.jsonl`, `traces.jsonl`, `applicability.json`, `run.log`, `report/` (`report.md`, `scores.csv`, `pairs.csv`, `pareto.csv`, `costs.csv`, `retrieval.csv`). `traces.jsonl` n'est jamais réécrit ; la reprise relit `answers.jsonl` et `verdicts.jsonl`.
- Modules : `components/chunkers/fixed_tokens`, `components/context/` (`labeled`, `build_arch_answer`), `components/generators/llm`, `components/lexical_indexes/bm25` (bm25s), retriever `lexical`, `runner/` (`index_cache`, `rundir`, `context`), `scoring/` (`retrieval`, `answer`, `panel`), `stats/` (`bootstrap`, `mcnemar`, `pareto`), `report/` (dont `export.py`). Baselines : `no_context`, `long_context` (`cache_system`, `retrieval_method: cited`), `bm25_only` (`k: 5`, `k` dans `query_params`).
- Panel (AD-14) : Juges hors Famille des `answer_producer` et hors exclus de la calibration (`calibration.json`) ; `JudgeInput` construit avec `context_texts`.
- Commandes : `wl run <exp> [--reprendre <run_id>]`, `wl rapport <run_id> [--exporter-front qualite-cout --vers <fichier>]` (liste `configurations:` acceptée par `config/load.py`). Codes de sortie 0, 1, 2, 3, 4 ; messages en français.
- Livrables de test : `tests/conformance/test_architectures.py` (paramétré sur tout le registre, utilise `CONFORMANCE_QUESTION_ID`), `tests/e2e/test_sm3.py`, `tests/real/test_sm4.py` (`real_api`, sauté sans `ANTHROPIC_API_KEY`) ; `experiments/mini-test.yaml` (une Configuration par Architecture enregistrée, vérifié par test), `mini-cpu.yaml`, `mini-real-haiku.yaml` (Juges `[fake-llm-b, fake-llm-c]`, embedder `fake`, `max_questions: 5`, 5,00 USD).

## Cross-Story Dependencies

- 4.1 (Generator, contexte) précède 4.2 (Baselines) ; 4.3 (cache d'index, dossier) et 4.2 précèdent 4.4 (`wl run`) ; 4.4 est requis par 4.5 à 4.9.
- 4.9 dépend du Juge LLM (3.4) et du Gel (3.6, `verify_frozen`, `select_questions`) ; 4.4 dépend de 3.6 et du `RunContext` concret (3.2).
- 4.6 dépend de `tirer` (2.7) ; 4.7 du Scénario (2.6) et de la Question de conformité (3.7).
- 4.10 est indépendante (fonctions pures) et précède 4.11 à 4.13 ; 4.11 précède 4.12 et 4.13.
- 4.14 suppose toutes les stories précédentes ; 4.15 dépend de 4.8, 4.12 et 4.14 (`mini-real-haiku.yaml`).
- Vers les autres epics : les epics 6 et 7 ajoutent une Configuration par Architecture à `mini-test.yaml` et passent la conformité ; l'epic 5 écrit `calibration.json` lu par le Panel.

## Reports hérités à traiter dans l'epic 4

- Runner, 4.3 / 4.4 : remplacer `parser: auto` par le parser concret (`markdown`, `text`, `html`, `pdf_text`) avant `write_resolved` et `RunContext.parser` ; vérifier qu'`experiment.resolved.yaml` ne contient plus `auto` (1.2, 1.5, 2.1, 2.2).
- Runner, `RunContext` concret : exposer `tokenizer_for(model_id, catalog, reference)`, appeler `runner/wiring.py::build_gateway`, câbler `make_tokenizer(profil.tokenizer)` et le `Tracer`, appliquer `token_factor` à l'estimation, poser `wl.energy_*` via `FakeEstimator` / `EcoLogitsEstimator` (1.9, 1.7).
- Runner : refuser à la validation un plafond `ollama` hors EUR ; répartir l'énergie locale par phase (1.9).
- Runner, Faux LLM : construire `FakeProvider` et le passer à `build_gateway(providers={"fake": ...})` ; isoler le Cache de réponses des runs scénarisés (`script`) pour qu'une sortie scénarisée ne persiste pas dans `WL_HOME` (1.10).
- Runner, journaux : créer le handler de `run.log` et appeler `limiter_journaux(handler)` après l'import du SDK (1.11).
- Runner, verrou et registre : prendre `run.lock` puis ouvrir le `Ledger` avec `recover_orphans=True` ; tester qu'un second `wl run` ne règle pas les réservations du premier (1.8).
- Runner, contexte : garder le `RunContext` vivant (`with`) pendant toute l'Exécution sinon le GC libère `run.lock` ; fixer `parser` depuis la Configuration ; écrire `manifest.json`, `run.log`, `experiment.resolved.yaml` ; prévoir une libération manuelle d'une réservation `hors_execution` orpheline (3.2).
- Runner, Scénario : passer à `corpus_apres` la langue par défaut du `corpus.yaml` (`lang`) et le Parser de la base (`parser`) (2.6).
- Runner, Paliers : déduire les `required_paths` des Ancrages des Questions et les passer à `tirer(parsed, tiers, required_paths)` (2.7).
- Panel : construire `JudgeInput` avec les textes des Ancrages et les `context_texts` du Generator ; ouvrir `ctx.scope(post="judging")` (3.4).
- Panel et préflight : contrôler tout le réservoir de Juges et `calibration_judge` (1.12).
- Panel, Juge closed-book : refuser une justification vide si le contrat l'exige (`CriterionVerdict`) ; choisir le Juge par défaut avec filtre de Famille (AD-14) au lieu de `judge_pool[0]` (3.4).
- Passerelle, 1.9 : `cache_write_1h` n'est pas facturé, `Usage` n'a pas de poste 1 h ; à garder en tête pour les coûts du Rapport (1.4).
- Story 4.15 (`real_api`) : vérifier que l'API accepte `temperature` via `extra_body` et l'outil de sortie imposé (1.11).
- Story 4.15 (`real_api`) : vérifier `wl questions generer` sur `claude-haiku-5-5` réel (répartition des Types, Ancrages hors échantillon rejetés) (3.3).
- Story 4.15 / providers : un délai dépassé après envoi doit régler à l'estimation au lieu de libérer, à vérifier sur un vrai appel interrompu ; vérifier `response.impacts` (EcoLogits, `llm_impacts` en ecologits 0.11.3) (1.11).
- Après le pilote, `energy` : vérifier `gpu_ids=[]` (pas de NVML), les noms `_hardware`/`_mode` de codecarbon 3.3.1, `estimated` sous Windows, règle CPU estimé / GPU mesuré (1.7).
- Préflight de `wl run` : code 4 avec Ollama arrêté puis démarré, une fois Ollama libre (1.12).
- Extraction d'entités : l'heuristique rate les noms en début de phrase ; à revoir si des Questions multi-hop en dépendent (2.5).
- Arbitrages en attente touchant les coûts : AC 3 de 1.4 (palier ×5 contre 0,60) et AC 2 de 1.8 (plafond de période) (1.4, 1.8).
