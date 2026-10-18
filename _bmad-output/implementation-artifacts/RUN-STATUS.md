# RUN-STATUS - run autonome WaveLibrarian

Fichier tenu par l'orchestrateur. Une session neuve (après `/clear`) reprend le run en ne relisant que ce fichier et `sprint-status.yaml`, dans le même dossier.

## État

| Champ | Valeur |
| --- | --- |
| Mis à jour | 2026-10-18 05:34 |
| Story en cours | 4.11 (voie B) ; 7.6 (voie A) |
| Stories livrées | 47 / 56 |
| Dépense Anthropic | 0,00 $ / plafond 5 $ |
| Pilote slm-quality-bench | **terminé** : `pilot-report.md` écrit à 04:59, fin confirmée à 05:03 et 05:08, GPU libre. **Ollama et GPU autorisés** depuis 05:08 (consigne d'Anaël) |
| Dernière mesure du banc | voir « Journal de surveillance » |
| Blocages | aucun |
| À arbitrer par Anaël | Story 1.4, AC 3 : l'exemple « 1 M + 1 M → 0,60 $ » contredit le palier ×5 au-delà de 100 000 tokens (3,00 $ sur le vrai Catalogue). Règle de palier gardée. Story 1.8, AC 2 : deux Exécutions de 1,50 $ réglées dépassent le plafond de période de 2,00 $ ; test écrit avec un plafond de période de 3,00 $. Story 7.5 : l'AC demande l'extracteur d'entités « enregistré comme Composant », mais `contracts.md` §2 ferme `KINDS` ; extracteur et rédacteur de rapports restent des classes de `components/graph/` (ajouter un `kind` si tu le souhaites). Story 1.7 (vérification réelle) : sous Windows, codecarbon lit le CPU par `windows_emi`, absent de `_MODES_MATERIELS` ; la méthode vaut `estimated` — ajouter `windows_emi` si la mesure CPU doit compter comme `measured`. Story 2.1 : « licence restrictive » non définie au contrat ; retenu = toute licence hors `LICENCES_OUVERTES` (CC0, CC-BY*, MIT, Apache, BSD, ODbL, PDDL, Etalab, LO) ; deux Documents de contenu identique sont refusés (Ancrages ambigus). Story 3.1 : l'AC dit « signalée » pour une `unanswerable` avec Ancrages ou une autre Question sans Ancrage ; retenu = bloquant (code 2) si `validated`/`corrected`, simple signalement sinon. |

## Consignes du run

Ordre : les stories de `sprint-status.yaml`, epics 1 à 7, dans l'ordre du fichier. Par story : `agent-cost-kit:dev-story` → `agent-cost-kit:second-avis` → `agent-cost-kit:reviewer` (avec la liste du second avis) → intégration sur `main`, puis mise à jour du sprint status et de ce fichier. Appels bloquants, une passe de revue, pas d'imbrication de sous-agents.

Parallélisme (autorisé par Anaël le 2026-10-17, risque faible) : au plus deux voies, A = fin de l'epic 1 (1.11, 1.12), B = epic 2 dans l'ordre. Intégration séquentielle : rebase sur `main`, suite complète, puis fusion. Retour à une voie si le débit du banc baisse de plus de 15 %.

Contexte : ne jamais relire `epics.md` en entier (150 Ko). Lire `epic-<N>-context.md` (compilé une fois par epic dans ce dossier), puis la seule section de la story : repérer `### Story N.M` par une recherche, et lire jusqu'à la story suivante. Transmettre aux sous-agents ce chemin et ces numéros de ligne, pas le fichier entier.

Contraintes du run autonome, reprises de `_bmad-output/planning-artifacts/epics.md`. Elles s'ajoutent aux stories sans changer leurs critères.

### Cohabitation avec slm-quality-bench (jusqu'au 18/10 vers 10 h, ou jusqu'à `pilot-report.md`)

- **Ollama local interdit.** Aucune requête hors `/api/version`, `/api/ps` et `/api/tags`, aucune commande `ollama`, aucun second serveur de modèles. Les tests `real_local` (stories 1.11 et 1.12) sont écrits mais pas exécutés : ne jamais lancer `pytest -m real_local`. Pas de `wl run` sur `mini-cpu.yaml`. Le préflight se limite à `/api/tags`.
- **GPU interdit.** `CUDA_VISIBLE_DEVICES=-1` avant tout code de ML. Après chaque exécution de code de ML, vérifier que son PID n'apparaît pas dans `nvidia-smi --query-compute-apps=pid,process_name --format=csv`.
- **Pas d'extra lourd, aucun téléchargement de plus de 1 Go.** Pas d'extras `local` (torch) ni `docling`, pas de `wl installer`.
- **Ressources.** `OMP_NUM_THREADS=4`, `MKL_NUM_THREADS=4`, `OPENBLAS_NUM_THREADS=4` ; au plus 6 Go de RAM ; priorité `BelowNormal` ; aucun pytest parallèle.
- **API autorisée.** Seule la story 4.15 (SM-4) appelle l'API Anthropic, avec des Juges et un embedder factices, sous le plafond de 5 $.

### Surveillance toutes les 10 minutes

Avant de commencer, puis toutes les 10 minutes environ, consigner une ligne dans le journal ci-dessous :

- débit du banc : réponses des 10 dernières minutes dans `C:\Users\Utilisateur\Documents\GitHub\wavelocalai\data\quality_bench\campaigns\pilot-20261017\log-generate.log`, comparées sur le même modèle et la même piste (champs 2 et 4 de la clé `pilot-20261017|modèle|mode|piste/…`) ;
- CPU total et RAM libre ;
- consommation propre du run : temps CPU, RSS de pointe, threads.

### Seuils d'arrêt

- **Pause** si le débit du banc baisse de plus de 15 %, si le CPU dépasse 80 % de façon soutenue, ou si la RAM libre passe sous 6 Go. Reprendre quand la mesure revient sous les seuils.
- **Arrêt sans rien toucher, et prévenir Anaël**, si une ligne `ERROR` ou « campagne arrêtée » apparaît dans le log du banc.
- Le travail lourd attend `pilot-report.md`.

### Après le pilote

Dès que `pilot-report.md` existe dans le dossier de la campagne, Ollama local redevient utilisable : tests `real_local` (stories 1.11 et 1.12) et `wl run` sur `mini-cpu.yaml`, sur le profil CPU (`num_gpu: 0`). Le GPU reste à `CUDA_VISIBLE_DEVICES=-1` sauf avis contraire d'Anaël. Le noter ici dans « État ».

**Avis d'Anaël (2026-10-17, 23 h 20)** : les tests GPU de l'autre session doivent finir vers 5 h ou 6 h (précision d'Anaël à 23 h 50). À partir de 5 h, vérifier toutes les 20 min qu'ils sont arrêtés (`pilot-report.md`, ou verrou `generation.lock` absent + log muet depuis 10 min + aucun processus dans `nvidia-smi`), et reconfirmer 5 min après le premier constat. Une fois confirmé, **Ollama et le GPU deviennent utilisables** (fin des contraintes de cohabitation ; garder un seul serveur de modèles).

### Reprise après `/clear`

1. Lire ce fichier, puis `sprint-status.yaml`.
2. Une story `in-progress` sans commit d'intégration est reprise depuis son fichier de story (et son worktree s'il existe).
3. Refaire une mesure du banc avant de relancer un dev-story.

## Reports entre stories

À transmettre au dev-story de la story cible.

- **2.2** : table format → parser enregistré à partir de `DeclaredCorpus.formats` (2.1), pour remplacer `parser: auto` (stories 1.5 et 2.1).
- **4.3 / 4.4** : le runner remplace `parser: auto` par le parser concret avant `write_resolved` et `RunContext.parser` (stories 1.2 et 1.5) ; vérifier que `experiment.resolved.yaml` ne contient plus `auto`.
- **Epic 5 (`wl calibrer`, FR-38)** : écrire `calibration.json` au format §4.6 retenu en 1.6 (par Juge, `excluded` booléen strict, `criteria`).
- **1.9 (Passerelle)** : câbler `RunContext.tokenizer_for(model_id, catalog, reference)`, `make_tokenizer(profil.tokenizer)` et le `Tracer` ; appliquer `token_factor` (1,5 pour Haiku) à l'estimation avant appel ; poser `wl.energy_*` via `FakeEstimator` / `EcoLogitsEstimator` (story 1.7).
- **1.11 (providers)** : brancher les providers sur le protocole `Provider` (`llm/providers/base.py`, `complete(request, *, timeout_s)` → `ProviderResponse`) ; délai dépassé après envoi → régler à l'estimation au lieu de libérer, à vérifier sur un vrai appel interrompu ; le poids du schéma de sortie dans l'estimation dépend du mode d'envoi (outil ou `format`) (story 1.9).
- **1.11 (providers, suite)** : lire `response.impacts` (AD-17 : `EcoLogits.init`) et vérifier `llm_impacts` en ecologits 0.11.3 (story 1.7).
- **Après le pilote, extra `energy`** : vérifier que `gpu_ids=[]` n'initialise pas NVML, les noms `_hardware`/`_mode` de codecarbon 3.3.1, `estimated` sous Windows, et la règle CPU estimé / GPU mesuré (story 1.7).
- **1.9 (Passerelle)** : calculer `cache_key` après avoir posé `role_marker(role)` (fonction de `llm/cache.py`, `cache_key` lève sinon) ; ne mettre en cache que les succès (story 1.8).
- **Runner / RunContext (epic 4)** : `RunContext` concret qui expose `tokenizer_for(model_id)` et appelle `runner/wiring.py::build_gateway` ; répartition de l'énergie locale par phase ; refuser à la validation un plafond `ollama` hors EUR (story 1.9).
- **Runner (epic 4), Faux LLM** : construire `FakeProvider` et le passer à `build_gateway(providers={"fake": ...})` ; isoler le Cache de réponses des runs scénarisés (`script`), sinon une sortie scénarisée persiste dans `WL_HOME` pour le run suivant (story 1.10).
- **Runner (epic 4), journaux** : créer le handler de `run.log` et y appeler `limiter_journaux(handler)` après l'import du SDK (story 1.11).
- **Quand Ollama sera libre** : `pytest -m real_local` ; vérifier dans `ollama ps` aucune couche GPU sur le profil CPU et `num_ctx` = 32768 ; surveiller la RAM de `granite4.2:3b` avec cette fenêtre (story 1.11).
- **Story 4.15 (`real_api`)** : vérifier que l'API accepte `temperature` via `extra_body` et l'outil de sortie imposé (story 1.11).
- **Runner (epic 4)** : prendre `run.lock` puis ouvrir le `Ledger` avec `recover_orphans=True` ; tester qu'un second `wl run` ne règle pas les réservations du premier (story 1.8).
- **Gateway (1.9)** : `cache_write_1h` n'est pas facturé, `Usage` n'a pas de poste 1 h (story 1.4).
- **Story outillage / CI** : lancer `test_socket_tcp_bloque` sous Linux (story 1.1).
- **2.3** : `pdf_text` déclare `version` et s'enregistre, pour que `auto` accepte un Corpus avec PDF (story 2.2).
- **2.5** : un `html_block` Markdown reste brut dans un Block `text` ; un HTML non UTF-8 ignore `<meta charset>` (repli cp1252 seulement) (story 2.2).
- **Quand Ollama et le GPU seront libres (story 1.12)** : `uv sync --extra local` puis `wl installer --profil cpu` (sortie 0, ou 4 avec la liste des `ollama pull`) ; vérifier `embedder_installe("intfloat/multilingual-e5-small")` sur le cache réel ; `pytest -m real_local` ; `wl run` avec Ollama arrêté (code 4) puis démarré.
- **Epic 3 / epic 4** : le préflight contrôle tout le réservoir de Juges et `calibration_judge` ; `closed_book_models` et `question_gen_model` sont à contrôler dans `wl questions` (story 1.12).
- **2.6** : fournir `wavelibrarian.corpus.scenario.corpus_apres(parsed, chemin)`, importé par `wl questions controler --scenario` (story 3.1), ou adapter `_corpus_apres` dans `cli.py`.
- **3.4** : `exact_match` va dans `scoring/answer.py`, qui contient déjà `is_short_form` (story 3.1).
- **3.3 / 3.5** : contrôler `question_gen_model` et `closed_book_models` au Catalogue dans `wl questions generer` et `closed-book` (stories 1.12 et 3.1).
- **Transverse CLI** : les erreurs d'usage click/typer (« Usage: », « Missing argument ») sont en anglais (story 3.1).
- **3.6 (`geler`)** : agréger toutes les erreurs du fichier de Questions (aujourd'hui une seule `ConfigError`) (story 3.1).
- **Runner (epic 4), RunContext** : garder le contexte vivant (`with`) pendant toute l'Exécution, sinon le GC libère `run.lock` ; fixer `parser` depuis la Configuration ; écrire `manifest.json`, `run.log`, `experiment.resolved.yaml` ; prévoir une libération manuelle d'une réservation `hors_execution` orpheline (story 3.2).
- **Toute commande hors Exécution** : ouvrir `ctx.scope(post=...)` avant tout appel LLM (la passerelle refuse sinon) ; traces dans `WL_HOME/hors-execution/<run_id>/` (story 3.2).
- **Extraction d'entités (2.4)** : l'heuristique rate les noms en début de phrase (Maëlis Torvane trouvée dans 3 Documents sur 7) ; à revoir si les questions multi-hop ou GraphRAG en dépendent (story 2.5).
- **Story 4.15 / real_api** : vérifier `wl questions generer` sur `claude-haiku-5-5` réel (répartition des Types, Ancrages hors échantillon rejetés) (story 3.3).
- **Runner (epic 4), Scénario** : passer à `corpus_apres` la langue par défaut du `corpus.yaml` (`lang`) et le Parser de la base (`parser`) (story 2.6).
- **3.5 (closed-book)** : refuser une justification vide si le contrat l'exige (`CriterionVerdict`) ; choisir le Juge par défaut avec filtre de Famille (AD-14) au lieu de `judge_pool[0]` (story 3.4).
- **Panel (epic 4)** : construire `JudgeInput` avec les textes des Ancrages et les `context_texts` du Generator ; ouvrir `ctx.scope(post="judging")` (story 3.4).
- **Runner (epic 4), Paliers** : déduire les `required_paths` des Ancrages des Questions et les passer à `tirer(parsed, tiers, required_paths)` (story 2.7).
- **Commandes `wl questions`** : afficher le coût du Juge (sommer le registre au Poste `judging`) ; pas de préflight dans `generer` ni `closed-book` (story 3.5).
- **4.2 (Baselines)** : passer `tokenizer=` à `build_arch_answer` depuis chaque Baseline et tester la troncature au-delà de 8 000 tokens depuis une Architecture (story 4.1).
- **Runner (epic 4), Jeu gelé** : appeler `verify_frozen` et `select_questions` ; le Rapport exclut des scores principaux les Questions contaminées pour le modèle concerné (FR-12, contracts §4.5) (story 3.6).
- **Runner des Conditions (epic 4)** : la Condition contexte parfait de `long_context` passe par `answer_with_context`, donc sans cache du system (story 4.2).
- **4.14 (conformité)** : `CONFORMANCE_QUESTION_ID = "q-001"` s'importe par `from conftest import` ; casse avec `--import-mode=importlib` (story 3.7).
- **Epic 6** : chaque Architecture à embeddings redéfinit `ArchitectureBase.embedder_dim()` (story 4.3).
- **4.8 (reprise)** : relire `experiment.resolved.yaml` comme `ResolvedExperiment` (ou accepter un parser composite `markdown+pdf_text` dans `resolve_experiment`) (story 4.3).
- **4.7** : `IndexCache.build(post="update")` pour la phase après mise à jour (story 4.3).
- **5.2 (`wl calibrer`)** : code 2 pour toute `ConfigError` du chargeur et quand `rapprocher` ne garde aucune annotation ; jointure inter-annotateurs sur les Réponses doublement annotées ; résoudre `answers.jsonl` de l'Exécution (story 5.1).
- **Epic 7, cache d'index** : une Architecture qui appelle le LLM à l'indexation, lancée avec un Faux LLM scénarisé, ne doit pas laisser dans `WL_HOME/index/` un index construit sur une sortie scénarisée (story 4.4).
- **Runner** : l'ingestion propre au parser d'une Configuration est hors de son `try` (échec → toute l'Exécution `failed`) (story 4.4).
- **4.14 (conformité)** : ajouter chaque Architecture de l'epic 6 (dès `naive_rag`) à `experiments/mini-test.yaml` et la faire passer dans `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` (story 6.1).
- **4.8 (reprise)** : à la reprise, ne pas compter deux fois les spans `query` déjà émis pour une Question interrompue par `BudgetExceeded` (story 4.5).
- **Rapport (4.12), Coût de possession** : exclure les spans `wl.llm_cache_hit=true` (latence d'origine, bornes fictives) de la durée des spans locaux (story 4.5).
- **4.14 (Expériences livrées)** : toute Expérience à Paliers sur le Mini-corpus pose `max_questions` ou un `tier` adapté (split dev = 12 Documents requis) ; vérifier `wl run` en code 0 sur chacune (story 4.6).
- **Rapport (4.12), CAG** : l'écriture du préchargement CAG revient à chaque Exécution au Poste `indexing` (hit d'index et reprise compris), elle ne s'amortit pas comme un index (story 6.5).
- **Story 4.15 / fournisseur réel, CAG** : sur `claude-haiku-5-5`, Corpus > 512 tokens → écriture positive et lecture dès la première Question ; Corpus plus court → tokens en cache nuls sans erreur (story 6.5).
- **4.13 (Fraîcheur)** : en contexte parfait, une Question dont l'Ancrage est supprimé (q-047) est `inapplicable` en `after_update` mais posée en Condition standard : exclure les `inapplicable` du dénominateur de la Fraîcheur par Condition et le dire dans le Rapport ; avec un Scénario, les Paliers `base` contiennent les cibles du Scénario (story 4.7).
- **Quand Ollama sera libre (story 7.1)** : vérifier qu'une indexation RAPTOR par défaut sur `minicpm5` ne journalise aucune fenêtre pleine.
- **4.11 (lecteurs du Rapport)** : tolérer une dernière ligne JSONL invalide non terminée (`answers.jsonl`, `traces.jsonl`) et terminer le fichier par `\n` avant tout ajout ; lire les Réponses par `read_answers` (dernière ligne d'une clé fait foi) ; ignorer les spans `wl.resumed: true` pour les appels et la latence ; ne jamais juger un `budget_exceeded` (story 4.8).
- **Quand Ollama sera libre (story 7.2)** : vérifier qu'un long PDF ne remplit jamais la fenêtre de `minicpm5` avec PageIndex.
- **Rapport (4.11 / 4.12), LLM Wiki** : appeler `report/wiki.py::section_fidelite` pour afficher le taux de fidélité ; le juge de fidélité par défaut suit `profil.judge_pool` (le Context ne porte pas `judges.pool`) ; `fidelity_model` explicite non contrôlé par `validate` (story 7.3).
- **4.11 (Rapport)** : calculer rappel@k / MRR / nDCG par Question depuis `answers.jsonl` et écrire `retrieval.csv` ; en Palier, juger une Citation « hors du Corpus » par rapport au sous-corpus du Palier ; afficher `unjudged` (story 4.9).
- **Story 4.15 / vraie Exécution** : vérifier que le plafond couvre les appels des Juges (2 par Réponse ok) (story 4.9).
- **4.11 (Rapport, statistiques)** : appeler `graine_derivee(seed_experience, config_id, condition, tier, phase, critère ou paire)` pour chaque IC et comparaison ; traiter `None` de `compare()` (pas de « Qualité égale » ni de point mort) ; signaler l'absence de correction de multiplicité à côté de `pairs.csv` ; écrire `pairs.csv` et `pareto.csv` (story 4.10).
- **7.6 (GraphRAG)** : brancher `louvain_seed(ctx.seed)` et le GraphStore `networkx` ; utiliser `components/graph/` (extraction, communautés, rapports) ; vérifier le majorant de 400 tokens contre `count_tokens` Anthropic en 4.15 (story 7.5).

## Journal de surveillance

| Heure | Débit banc (10 min, modèle / piste) | CPU | RAM libre | Run (CPU s, RSS max, threads) | Décision |
| --- | --- | --- | --- | --- | --- |
| 20:58 | 8 (lfm2.5-2.6b / reasoning, ~1 réponse/41 s) ; fenêtre précédente sur un autre modèle, référence posée | 9 % | 17,6 Go | 0 s, 86 Mo, 57 thr (aucun pytest) | Mesure de départ, aucune ERROR : on démarre 1.1 |
| 21:09 | 20 (lfm2.5-2.6b / reasoning) ; 11 sur les 10 min précédentes ; +82 % | 12 % | 16,7 Go | 1 s, 86 Mo, 101 thr (uv/pytest du run) | Sous les seuils : on continue (1.2) |
| 21:20 | 19 (lfm2.5-2.6b / reasoning) ; 10 min avant : 23 ; -17 % | 16 % | 17,2 Go | 1 s, 86 Mo, 70 thr (9 proc) | Faux signal : la piste reasoning s'est terminée vers 21:19 (passage à rag), fenêtre incomplète ; intervalle par réponse inchangé (~41 s). On continue (1.3). Mesure passée en secondes par réponse. |
| 21:22 | Indicateur révisé : durée des réponses tronquées (budget de tokens fixe), même modèle / mode / jeu. think_on reasoning/bbeh-mini 42 s vs 41 s (−3 %) | 7 % | 17,0 Go | 0 s, 86 Mo, 54 thr | Pas de ralentissement réel : on continue (1.3). Les comptages bruts par piste mélangent des questions de longueurs très différentes. |
| 21:30 | 2 tronq. (lfm2.5-2.6b) : think_on reasoning/bbeh-mini 1 tronq., 42 s/tronq. (pas de réf.) ; think_on tools/bfcl-multi 1 tronq., 25 s/tronq. (pas de réf.) ; pire +0 % | 12 % | 15.5 Go | 1 s, 86 Mo, 76 thr (9 proc) | Sous les seuils : on continue (1.4) |
| 21:40 | 2 tronq. (gemma4:e2b-it-qat) : think_off instructions/ifbench 2 tronq., 19 s/tronq. (pas de réf.) ; pire +0 % | 23 % | 16.9 Go | 1 s, 86 Mo, 72 thr (9 proc) | Sous les seuils : on continue (1.5) |
| 21:50 | 17 tronq. (gemma4:e2b-it-qat) : think_off reasoning/bbeh-mini 20 s/tronq. (nouveau modèle, référence posée) | 26 % | 15,1 Go | 1 s, 86 Mo, 59 thr | Sous les seuils |
| 21:52 | 19 tronq. (gemma4:e2b-it-qat) : think_off reasoning/bbeh-mini 19 tronq., 20 s/tronq. vs 20 (-0 %) ; pire -0 % | 36 % | 13.3 Go | 1 s, 86 Mo, 70 thr (9 proc) | Sous les seuils : on continue (1.6) |
| 22:05 | 6 tronq. (gemma4:e2b-it-qat) : think_off reasoning/bbeh-mini 4 tronq., 21 s/tronq. vs 20 (-4 %) ; think_off reasoning/var-math-fr 1 tronq., 20 s/tronq. (pas de réf.) ; think_off rag/oneruler-fr-cwe 1 tronq., 23 s/tronq. (pas de réf.) ; pire -4 % | 19 % | 14.6 Go | 1 s, 86 Mo, 73 thr (9 proc) | Sous les seuils : on continue (1.7) |
| 22:19 | 7 tronq. (gemma4:e2b-it-qat) : think_on instructions/ifbench 4 tronq., 20 s/tronq. (pas de réf.) ; think_on extraction/extraction-fr 3 tronq., 20 s/tronq. (pas de réf.) ; pire +0 % | 23 % | 13.9 Go | 1 s, 86 Mo, 69 thr (9 proc) | Sous les seuils : on continue (1.8) |
| 22:32 | 1 tronq. (gemma4:e2b-it-qat) : think_on reasoning/bbeh-mini 1 tronq., 41 s/tronq. (pas de réf.) ; pire +0 % | 24 % | 13.1 Go | 1 s, 87 Mo, 71 thr (9 proc) | Sous les seuils : on continue (1.9) |
| 22:46 | 9 tronq. (gemma4:e2b-it-qat) : think_on reasoning/bbeh-mini 9 tronq., 41 s/tronq. vs 41 (+1 %) ; pire +0 % | 11 % | 12.6 Go | 1 s, 87 Mo, 70 thr (9 proc) | Sous les seuils : on continue (1.10) |
| 23:01 | 5 tronq. (gemma4:e2b-it-qat) : think_on rag/oneruler-fr-cwe 4 tronq., 24 s/tronq. (pas de réf.) ; think_on reasoning/bbeh-mini 1 tronq., 42 s/tronq. (pas de réf.) ; pire +0 % | 34 % | 12.4 Go | 1 s, 87 Mo, 71 thr (9 proc) | Sous les seuils : on continue (1.11) |
| 23:26 | 2 tronq. (qwen3.5:4b) : think_off instructions/mifeval-fr 1 tronq., 35 s/tronq. (pas de réf.) ; think_off reasoning/bbeh-mini 1 tronq., 36 s/tronq. (pas de réf.) ; pire +0 % | 20 % | 10.4 Go | 1 s, 86 Mo, 81 thr (12 proc) | Sous les seuils : on continue (1.12) |
| 23:29 | 6 tronq. (qwen3.5:4b) : think_off reasoning/bbeh-mini 6 tronq., 36 s/tronq. (pas de réf.) ; pire +0 % | 32 % | 10.1 Go | 7 s, 547 Mo, 119 thr (19 proc) | Sous les seuils : on continue (2.2) |
| 23:45 | 12 tronq. (qwen3.5:4b) : think_off reasoning/bbeh-mini 12 tronq., 36 s/tronq. vs 36 (+1 %) ; pire +0 % | 20 % | 10.1 Go | 1 s, 88 Mo, 116 thr (19 proc) | Sous les seuils : on continue (2.3) |
| 23:49 | 10 tronq. (qwen3.5:4b) : think_off reasoning/bbeh-mini 10 tronq., 36 s/tronq. vs 36 (+0 %) ; pire +0 % | 19 % | 11.8 Go | 1 s, 86 Mo, 78 thr (13 proc) | Sous les seuils : on continue |
| 23:58 | 0 tronq. (?) :  ; pire +0 % | 62 % | 14.0 Go | 1 s, 86 Mo, 74 thr (13 proc) | Sous les seuils : on continue (2.4) |
| 00:07 | 5 tronq. (qwen3.5:4b) : think_off reasoning/bbeh-mini 5 tronq., 37 s/tronq. vs 36 (-4 %) ; pire -4 % | 21 % | 12.1 Go | 1 s, 86 Mo, 75 thr (13 proc) | Sous les seuils : on continue (3.2) |
| 00:16 | 1 tronq. (qwen3.5:4b) : think_on extraction/extraction-fr 1 tronq., 36 s/tronq. (pas de réf.) ; pire +0 % | 9 % | 14.9 Go | 1 s, 86 Mo, 74 thr (13 proc) | Sous les seuils : on continue (2.5) |
| 00:28 | 15 tronq. (qwen3.5:4b) : think_on extraction/jsonschemabench 8 tronq., 35 s/tronq. (pas de réf.) ; think_on extraction/extraction-fr 7 tronq., 36 s/tronq. vs 36 (+0 %) ; pire +0 % | 12 % | 11.6 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue (3.3) |
| 00:37 | 12 tronq. (qwen3.5:4b) : think_on extraction/jsonschemabench 7 tronq., 36 s/tronq. vs 35 (-2 %) ; think_on instructions/ifbench 5 tronq., 35 s/tronq. (pas de réf.) ; pire -2 % | 9 % | 11.4 Go | 1 s, 86 Mo, 78 thr (13 proc) | Sous les seuils : on continue (2.6) |
| 00:44 | 17 tronq. (qwen3.5:4b) : think_on instructions/ifbench 13 tronq., 35 s/tronq. (pas de réf.) ; think_on instructions/instructions-fr 4 tronq., 35 s/tronq. (pas de réf.) ; pire +0 % | 23 % | 11.7 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue (3.4) |
| 00:53 | 14 tronq. (qwen3.5:4b) : think_on instructions/instructions-fr 8 tronq., 35 s/tronq. (pas de réf.) ; think_on instructions/mifeval-fr 6 tronq., 35 s/tronq. (pas de réf.) ; pire +0 % | 22 % | 10.7 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue (2.7) |
| 00:58 | 16 tronq. (qwen3.5:4b) : think_on instructions/mifeval-fr 16 tronq., 35 s/tronq. (pas de réf.) ; pire +0 % | 9 % | 11.6 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue (3.5) |
| 01:04 | 17 tronq. (qwen3.5:4b) : think_on rag/piaf 9 tronq., 35 s/tronq. (pas de réf.) ; think_on instructions/mifeval-fr 8 tronq., 35 s/tronq. vs 35 (+0 %) ; pire +0 % | 10 % | 11.7 Go | 1 s, 86 Mo, 75 thr (13 proc) | Sous les seuils : on continue |
| 01:15 | 12 tronq. (qwen3.5:4b) : think_on rag/piaf 6 tronq., 35 s/tronq. vs 35 (+0 %) ; think_on writing/writing-fr 6 tronq., 35 s/tronq. (pas de réf.) ; pire +0 % | 4 % | 11.5 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue (3.6) |
| 01:20 | 16 tronq. (qwen3.5:4b) : think_on writing/writing-fr 16 tronq., 35 s/tronq. (pas de réf.) ; pire +0 % | 15 % | 11.8 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue (4.2) |
| 01:29 | 11 tronq. (qwen3.5:4b) : think_on writing/writing-fr 6 tronq., 35 s/tronq. vs 35 (+0 %) ; think_on abstention/oneruler-fr-none 2 tronq., 38 s/tronq. (pas de réf.) ; think_on extraction/jsonschemabench 2 tronq., 36 s/tronq. vs 35 (-3 %) ; pire -3 % | 11 % | 14.9 Go | 1 s, 86 Mo, 101 thr (20 proc) | Sous les seuils : on continue (3.7) |
| 01:37 | 7 tronq. (qwen3.5:4b) : think_on reasoning/bbeh-mini 7 tronq., 71 s/tronq. (pas de réf.) ; pire +0 % | 16 % | 13.0 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue (4.3) |
| 01:49 | 7 tronq. (qwen3.5:4b) : think_on reasoning/bbeh-mini 7 tronq., 71 s/tronq. vs 72 (+0 %) ; pire +0 % | 17 % | 11.6 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue |
| 01:56 | 9 tronq. (qwen3.5:4b) : think_on reasoning/bbeh-mini 9 tronq., 71 s/tronq. vs 72 (+0 %) ; pire +0 % | 8 % | 11.7 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue (4.4) |
| 02:02 | 6 tronq. (qwen3.5:4b) : think_on reasoning/bbeh-mini 6 tronq., 71 s/tronq. vs 72 (+0 %) ; pire +0 % | 15 % | 11.6 Go | 1 s, 86 Mo, 78 thr (13 proc) | Sous les seuils : on continue |
| 02:19 | 2 tronq. (qwen3.5:4b) : think_on reasoning/var-math-fr 2 tronq., 70 s/tronq. (pas de réf.) ; pire +0 % | 17 % | 10.8 Go | 7 s, 563 Mo, 122 thr (21 proc) | Sous les seuils : on continue (4.5) |
| 02:21 | 3 tronq. (qwen3.5:4b) : think_on reasoning/var-math-fr 2 tronq., 70 s/tronq. (pas de réf.) ; think_on abstention/oneruler-fr-none 1 tronq., 43 s/tronq. (pas de réf.) ; pire +0 % | 11 % | 18.1 Go | 1 s, 86 Mo, 76 thr (13 proc) | Sous les seuils : on continue (6.2) |
| 02:38 | 6 tronq. (qwen3.5:4b) : think_on abstention/oneruler-fr-none 3 tronq., 53 s/tronq. (pas de réf.) ; think_on rag/oneruler-fr-cwe 2 tronq., 48 s/tronq. vs 41 (-14 %) ; think_on reasoning/bbeh-mini 1 tronq., 74 s/tronq. (pas de réf.) ; pire -14 % | 17 % | 13.0 Go | 1 s, 86 Mo, 76 thr (13 proc) | -14 % sur 2 réponses seulement (rag/oneruler-fr-cwe), juste sous le seuil de 15 % : vigilance, mesure suivante surveillée ; on continue (6.3) |
| 02:45 | 6 tronq. (qwen3.5:4b) : think_on rag/oneruler-fr-niah 3 tronq., 51 s/tronq. (pas de réf.) ; think_on rag/oneruler-fr-cwe 2 tronq., 48 s/tronq. vs 41 (-14 %) ; think_on abstention/oneruler-fr-none 1 tronq., 51 s/tronq. (pas de réf.) ; pire -14 % | 19 % | 19.3 Go | 1 s, 86 Mo, 105 thr (21 proc) | Sous les seuils : on continue (4.6) |
| 02:51 | Génération du banc terminée à 02:42 (« génération complète », 3 376 lignes, 0 ERROR) ; plus de réponses à mesurer. `generation.lock` encore présent, un `llama-server` (pid 11716) occupe toujours le GPU, sans `pilot-report.md` | 33 % | 18,0 Go | 10 s, 154 Mo, 136 thr | Contraintes Ollama/GPU maintenues jusqu'au contrôle de 5 h (consigne d'Anaël) ; on continue sur deux voies |
| 02:54 | 16 tronq. (lfm2.5:8b-a1b-q4_K_M) : think_off reasoning/bbeh-mini 6 tronq., 14 s/tronq. (pas de réf.) ; think_off instructions/ifbench 4 tronq., 14 s/tronq. (pas de réf.) ; think_off extraction/jsonschemabench 3 tronq., 14 s/tronq. (pas de réf.) ; pire -1 % | 17 % | 19.1 Go | 11 s, 182 Mo, 106 thr (20 proc) | Sous les seuils ; seconde campagne du banc (replay) démarrée à 02:42, mesure et contrôle de fin adaptés ; on continue (6.4) |
| 03:09 | 12 tronq. (lfm2.5:8b-a1b-q4_K_M) : think_off reasoning/bbeh-mini 7 tronq., 16 s/tronq. (pas de réf.) ; think_off reasoning/bbeh-mini 1 tronq., 15 s/tronq. (pas de réf.) ; think_off tools/bfcl-multi 1 tronq., 44 s/tronq. (pas de réf.) ; pire +0 % | 32 % | 19.1 Go | 4 s, 136 Mo, 113 thr (20 proc) | Sous les seuils : on continue (6.5) |
| 03:16 | 21 tronq. (ling3-tiny:8b-q4_k_m) : think_off reasoning/bbeh-mini 8 tronq., 16 s/tronq. (pas de réf.) ; think_on extraction/extraction-fr 3 tronq., 16 s/tronq. (pas de réf.) ; think_on instructions/mifeval-fr 3 tronq., 16 s/tronq. (pas de réf.) ; pire +0 % | 37 % | 19.8 Go | 15 s, 179 Mo, 101 thr (20 proc) | Sous les seuils : on continue (4.7) |
| 03:28 | 10 tronq. (ling3-tiny:8b-q4_k_m) : think_on reasoning/bbeh-mini 4 tronq., 32 s/tronq. (pas de réf.) ; think_on extraction/extraction-fr 3 tronq., 20 s/tronq. (pas de réf.) ; think_on extraction/jsonschemabench 1 tronq., 16 s/tronq. (pas de réf.) ; pire +0 % | 8 % | 19.5 Go | 1 s, 86 Mo, 79 thr (14 proc) | Sous les seuils : on continue |
| 03:39 | 12 tronq. (lfm2.5-2.6b) : think_on reasoning/bbeh-mini 7 tronq., 41 s/tronq. (pas de réf.) ; think_on extraction/jsonschemabench 3 tronq., 22 s/tronq. (pas de réf.) ; think_on rag/oneruler-fr-cwe 2 tronq., 26 s/tronq. (pas de réf.) ; pire +0 % | 18 % | 17.9 Go | 1 s, 86 Mo, 79 thr (14 proc) | Sous les seuils : on continue (4.8) |
| 03:48 | 7 tronq. (gemma4:e2b-it-qat) : think_off reasoning/bbeh-mini 6 tronq., 20 s/tronq. (pas de réf.) ; think_off instructions/ifbench 1 tronq., 20 s/tronq. (pas de réf.) ; pire +0 % | 32 % | 17.2 Go | 8 s, 158 Mo, 114 thr (20 proc) | Sous les seuils : on continue (7.2) |
| 04:11 | 5 tronq. (gemma4:e2b-it-qat) : think_off reasoning/bbeh-mini 2 tronq., 36 s/tronq. (pas de réf.) ; think_on rag/oneruler-fr-cwe 1 tronq., 23 s/tronq. (pas de réf.) ; think_on rag/oneruler-fr-niah 1 tronq., 30 s/tronq. (pas de réf.) ; pire +0 % | 21 % | 17.8 Go | 27 s, 184 Mo, 98 thr (20 proc) | Sous les seuils : on continue (4.9) |
| 04:14 | 8 tronq. (qwen3.5:4b) : think_off reasoning/bbeh-mini 7 tronq., 36 s/tronq. (pas de réf.) ; think_off instructions/mifeval-fr 1 tronq., 35 s/tronq. (pas de réf.) ; pire +0 % | 17 % | 16.7 Go | 1 s, 86 Mo, 79 thr (14 proc) | Sous les seuils : on continue (7.3) |
| 04:38 | 16 tronq. (qwen3.5:4b) : think_on instructions/mifeval-fr 5 tronq., 35 s/tronq. (pas de réf.) ; think_on rag/piaf 4 tronq., 36 s/tronq. (pas de réf.) ; think_on writing/writing-fr 4 tronq., 35 s/tronq. (pas de réf.) ; pire +0 % | 16 % | 12.8 Go | 1 s, 86 Mo, 77 thr (14 proc) | Sous les seuils : on continue (7.4) |
| 04:57 | 6 tronq. (qwen3.5:4b) : think_on abstention/oneruler-fr-none 2 tronq., 52 s/tronq. (pas de réf.) ; think_on rag/oneruler-fr-cwe 2 tronq., 42 s/tronq. (pas de réf.) ; think_on extraction/jsonschemabench 1 tronq., 37 s/tronq. (pas de réf.) ; pire +0 % | 6 % | 18.7 Go | 1 s, 86 Mo, 78 thr (12 proc) | Sous les seuils : on continue |
| 05:00 | 7 tronq. (qwen3.5:4b) : think_on abstention/oneruler-fr-none 2 tronq., 52 s/tronq. (pas de réf.) ; think_on rag/oneruler-fr-cwe 2 tronq., 42 s/tronq. (pas de réf.) ; think_on extraction/jsonschemabench 1 tronq., 37 s/tronq. (pas de réf.) ; pire +0 % | 1 % | 21.1 Go | 1 s, 86 Mo, 73 thr (12 proc) | Sous les seuils : on continue |
| 05:08 | Banc terminé (pilot-report.md présent, nvidia-smi vide), double confirmation à 5 min d'écart | — | — | — | Fin de la surveillance du banc ; contraintes de cohabitation levées (Ollama, GPU, téléchargements) |
| 05:40 | Vérifications réelles post-pilote (`verifications-reelles-2026-10-18.md`) : Ollama 0.40.5 OK, `wl installer --profil cpu` code 0, embedder installé, `pytest -m real_local` 2 OK (100 % CPU, `num_ctx` 32768, granite4.2:3b 5,1 Go), codecarbon `gpu_ids=[]` sans NVML. 2 défauts corrigés (sockets bloqués pour `real_*`, méthode `measured` à tort). | — | — | — | Reports « Quand Ollama sera libre » 1.11, 1.12 et énergie 1.7 soldés ; 7.1/7.2 (fenêtre minicpm5) et `wl run` cpu restent pour 4.14 |

## Journal des stories

| Story | Début | Fin | Commit | Dépense | Remarques |
| --- | --- | --- | --- | --- | --- |
| 1.1 | 21:00 | 21:09 | 4f3294e21ae06ae43b9c78fefa2887e0c331053c | 0 $ | Revue : 2 high (contrats import-linter inopérants, test lint-imports vide) et 1 medium corrigés ; typer `>=0.26,<1` (conflit docling `<0.27`) ; test socket sous Linux reporté à une story outillage. 14 tests verts. |
| 1.2 | 21:10 | 21:30 | e349d1970419bd0b7d13367023ed0aeca48430a3 | 0 $ | Revue : 2 medium corrigés (index_key lit le parser résolu via RunContext.parser, contracts.md §2.4 mis à jour ; ArchCapabilities gelé + extra=forbid). 33 tests verts. |
| 1.3 | 21:23 | 21:30 | 3908cf1d4686321c7aa58ba162b2c59230b53789 | 0 $ | Revue : 2 medium corrigés (fuite sys.modules dans la fixture ; register exige Params forbid+frozen, AD-2) et 6 low. 42 tests verts. |
| 1.4 | 21:31 | 21:40 | 5b06b7ec0bca3bbb6c44479db7b51da9e8b6ccc6 | 0 $ | AC 3 contradictoire (0,60 vs palier ×5 → 3,00) : règle de palier gardée, à arbitrer. Revue : tarifs obligatoires par poste, pricing refusé sur modèle local, profil = nom de fichier. 62 tests verts. |
| 1.5 | 21:41 | 21:52 | 6414d58681c32a6f6b8f4ccbe6839343a33a80a6 | 0 $ | Revue : ModelRef nu refusé au register, juges explicites non écrasés (is None, ge/min_length), seed strict. parser:auto reporté au runner (voir Reports). 93 tests verts. |
| 1.6 | 21:53 | 22:05 | cd4de3b219280a0b9b619eaf51c8482c00adac1e | 0 $ | Revue : agrégation complète des erreurs de Params (imbriqués compris), calibration_judge contrôlé au Catalogue, calibration.json validé strictement. 118 tests verts. |
| 1.7 | 22:08 | 22:19 | 6b98d4adaac09cfb1651f61c859a7bb495b7d247 | 0 $ | Revue : tiktoken sans téléchargement (empreinte SHA-256 du cache), écriture de traces vérifiée (WlError), OTLP en SimpleSpanProcessor, test d'import réel. Vérifs codecarbon reportées après le pilote. 141 tests verts, aucun PID du run sur le GPU. |
| 1.8 | 22:20 | 22:32 | 0fb2ee81b54cf729cebc96d1962719846b6fd6cb | 0 $ | AC 2 contradictoire (plafond période 2,00 vs 2 × 1,50) : test à 3,00, à arbitrer. Revue : recover_orphans explicite (runner après run.lock), sommes par devise, cache_key exige le marqueur de rôle. 159 tests verts. |
| 1.9 | 22:33 | 22:46 | 69482b99395300b7d6ec471f97a4d891c803bd25 | 0 $ | Revue : sortie invalide en cache remplacée (replace=True), appel payé toujours tracé avec son coût (réel ou estimé), span écrit avant le cache. 180 tests verts. |
| 1.10 | 22:47 | 23:02 | 585760d4c83041b407f927b4a350a36a302437ca | 0 $ | Revue : step dans cache_key pour fake (sorties scénarisées), latence 0 du Faux LLM réelle (ProviderResponse.latency_s), tests sans contournement. 227 tests verts. |
| 1.11 | 23:02 | 23:26 | 42d79297090758716ac153b644a14e9a0dcb2c79 | 0 $ | Revue : httpx2 déclaré, output_schema dans cache_key, pas de relance d'un essai envoyé, num_ctx Ollama = fenêtre du Catalogue, build_providers branché, test ANTHROPIC_LOG en sous-processus. real_* écrits, non exécutés. 274 tests verts. |
| 2.1 | 23:16 | 23:29 | acde7b2d0a006ee4d8e950d077f0f24e06565fe8 | 0 $ | Revue : AD-19 fail-closed (dépôt repéré sans git, erreur git = refus), licence restrictive gardée, fichiers cachés et liens exclus, double barrière git ls-files. 253 tests verts (avant rebase). |
| 2.2 | 23:30 | 23:45 | 68ec21ecb4c2818112485e0f323a5080060a6861 | 0 $ | Revue : 1 high corrigé (resolve sur titres frères renvoyait une ancre fausse), décodage UTF-8 strict + repli cp1252, titres imbriqués, cache versionné par Parser. 316 tests verts (avant rebase). |
| 1.12 | 23:27 | 23:49 | 1ed4338c07d5bd1e60f7d5533378af05900e9599 | 0 $ | Revue : embedder installé = config + poids + tokenizer, extra cassé → WlError, calibration_judge au préflight, ollama list en échec → code 4, client httpx fermé. real_local écrits, non exécutés. Fin de l'epic 1. |
| 2.3 | 23:46 | 23:58 | 5cda356e04d9253f6e3338dd252d67be3298d60f | 0 $ | Revue : césure PDFium (U+0002) recollée, NFKC et caractères de contrôle supprimés, PdfiumError → ValueError, tests chiffré et fermeture. 327 tests verts (avant rebase). |
| 3.1 | 23:53 | 00:07 | aceba11c9b85330dd934cc47fe9e9ea570a3d329 | 0 $ | Revue : Ancrage page+titres ambigu signalé, repli par slug restreint, messages pydantic traduits en français (transverse), faux signalement scenario corrigé. 394 tests verts. |
| 2.4 | 00:00 | 00:16 | 548387418f8e561c7cb16e2e394b257c1b821acd | 0 $ | Revue : apostrophe typographique unifiée, entités après élision, entités d'une lettre écartées, décimales à virgule, échec d'écriture → code 1. Conflit cli.py résolu au rebase. 404 tests verts. |
| 3.2 | 00:08 | 00:28 | 3c04983236ddbeae3975d70e129d8224ef2f4caa | 0 $ | Revue : réservations hors Exécution protégées de recover_orphans (colonne + migration), Poste obligatoire (appel hors scope refusé), traces hors Exécution séparées, run_id validé, verrou libéré sur échec, test inter-processus. 425 tests verts. |
| 2.5 | 00:17 | 00:37 | 44826159e0192fdacf664bd2d990fb76a116696b | 0 $ | 20 Documents (16 md, 4 pdf), 4 361 mots, police DejaVu commitée (5,5 Mo téléchargés une fois, licence libre). Revue : contradictions d'univers non voulues corrigées, contracts.md §4.1/§4.7 alignés (chemins relatifs à path), long Document porté à 1 157 mots. |
| 3.3 | 00:29 | 00:44 | ef1bfab22aa7010ad548992bbace166c4049add3 | 0 $ | Revue : dédoublonnage (texte normalisé + Ancrages, dans la sortie et face au fichier), Ancrage hors échantillon rejeté, coût en virgule fixe, --cible < 1 refusé. 466 tests verts. |
| 2.6 | 00:39 | 00:53 | 11b462e35883ac340db4d3ef842ed8f9764e3ca3 | 0 $ | Revue : langue déclarée (et non majoritaire) pour un Document ajouté, état après identique à une ingestion directe (test oracle), chemins absolus/.. refusés, OSError → ConfigError, delete+add garde les métadonnées. Conflit cli.py résolu. 490 tests verts. |
| 3.4 | 00:46 | 00:59 | 7b56ebc2da6502263b7da8e06c6dc878db7384e4 | 0 $ | Revue : exact_match sans faux positifs (signe moins, mots alphanumériques, plages), milliers à deux groupes, œ→oe ; disjonction et négation consignées comme limite. 527 tests verts. |
| 2.7 | 00:54 | 01:04 | ee52043b91ef7f791af1d75a8c04656aeb759963 | 0 $ | Revue : wl corpus paliers ingère le Corpus (mêmes Paliers que tirer(parsed)), test de graine renforcé. Fin de l'epic 2. 537 tests verts. |
| 3.5 | 01:00 | 01:15 | 567fea02a32bbb09e196d365b7513231394c0623 | 0 $ | Revue : 1 high corrigé (la question recopiée par le modèle était jugée comme réponse contaminée ; sans_question la retire avant exact_match et Juge, contrat §3 mis à jour), ordre de contaminated_by stable. 552 tests verts. |
| 4.1 | 01:07 | 01:20 | 3c1a6174a90e9c49ff3bc53f6097442373e17074 | 0 $ | Revue : étiquettes [S1]/S1 strictes, tests d'abstention et de registre renforcés ; titre accolé au corps dans Passage.text consigné. 568 tests verts. |
| 3.6 | 01:16 | 01:29 | b9366cfd44f049b2a93fb33bfa092209b4d3c556 | 0 $ | Revue : re-Gel qui change une partie refusé sauf --forcer, règle d'arrondi et exclusion des contaminées au Rapport documentées (§4.5), ids en double et horloge naïve refusés. 589 tests verts. |
| 4.2 | 01:20 | 01:37 | f21a1ea9a06584740dc6424011d9b84e080b6e85 | 0 $ | Revue : 1 high corrigé (long_context forçait mal cache_system avec un Generator explicite ; validateur qui force true et refuse false), fenêtre = entrée + max_tokens, BM25 sans mot → [], œ/æ décomposés, k après filtre. 607 tests verts. |
| 3.7 | 01:30 | 01:49 | 16461c0819e5e1fd0294838dff69be8ca81d333a | 0 $ | 47 Questions écrites à la main et gelées (graine 42, ratio 0,4). Revue : q-008, q-018, q-039 fausses après Scénario corrigées, q-021 rendue vraiment multi-hop, tests réponse⊂Ancrage et Documents modifiés. Fin de l'epic 3. |
| 4.3 | 01:38 | 01:56 | 0db8c4feb4295fdfcb8b3e6caf19a8c6f038152d | 0 $ | Revue : 1 high corrigé (parser composite markdown+pdf_text décomposé par format, test de bout en bout), contrat AD-3 restauré (limiter_journaux réexporté par la passerelle), version du Parser dans la clé d'index, freeze_sha256 obligatoire, test de filtrage de run.log. 625 tests verts. |
| 5.1 | 01:53 | 02:02 | 661f70741198ef4ff1e2efbaa2f60394c74dd0a6 | 0 $ | Revue : fichiers non UTF-8 → ConfigError, dossier sans annotation refusé, verdict yes/no strict (SafeLoader sans booléens implicites), .yml accepté, clés dupliquées refusées. 670 tests verts. |
| 4.4 | 02:04 | 02:19 | 79a40b2ca7cbe32587993acc10ff7ef6dab576e6 | 0 $ | Dev Opus. Revue : décompte des Réponses au manifeste et code 1 sans Réponse valide, Gel vérifié avant le préflight, écritures atomiques, attach_run_log dans le try, 4 tests (plafond, erreurs, échec de Configuration, failed). 686 tests verts. |
| 6.1 | 02:07 | 02:21 | 093fbf0833057bc5ce0a7010f2df01ea981a639f | 0 $ | Store numpy exact, retriever dense, naive_rag. Revue : test de mise à jour sur le vrai Scénario via IndexCache et rechargement, dimension fixée après ajout valide, search vide → [], ids.json illisible → WlError. 697 tests verts. |
| 6.2 | 02:23 | 02:38 | 768c8501a1903f783372738b12dc545b065a8fdb | 0 $ | Retriever hybride (RRF et pondéré), reranker fake, hybrid_rag. Revue : scores non reclassés plafonnés (ordre décroissant), paramètres de fusion contradictoires refusés, test BM25 après update renforcé. 716 tests verts. |
| 4.5 | 02:20 | 02:45 | 4d60217d0e9e588edea5b8bfc8e586a0f4f0ced5 | 0 $ | Revue : phase refermée si le mesureur échoue, Réponses écrites après les spans de leur phase, latence d'origine des hits conservée en cache et retracée (rejeu à l'identique), exceptions en vol préservées, kWh réparti sur phase sans durée. 7 corrigés. |
| 6.3 | 02:39 | 02:54 | 71e8d7bbc1da6d11b83271ea1a0973110316034a | 0 $ | Livrée sous réserve de la conformité 4.14. Revue : retriever hybrid refusé (il échouait après l'appel hyde payé), espion embed_queries vs embed_passages, test hyde_model / hyde_max_tokens, repli journalisé. 747 tests verts. |
| 6.4 | 02:55 | 03:09 | 39ed8f788e1cf6eb33188002b8cb1fdf0d376dd4 | 0 $ | Livrée sous réserve de la conformité 4.14. Revue : schéma de notation borné à n scores passé à la passerelle (réponse fautive rejouée sans cache, jamais mise en cache), loop ajouté aux Protocols et au contrat §2. 759 tests verts. |
| 4.6 | 02:46 | 03:16 | 06dcc99c3f6f971696b60a02340c71d812cef61f | 0 $ | Revue : Question ancrée sur un Document du Scénario → inapplicable en phase base, tirage limité aux Paliers demandés (emboîtement conservé), answer_with_context par défaut via build_arch_answer (déplacé dans ports), retrieved renseigné en provided, échec de Palier en error par cellule. |
| 6.5 | 03:11 | 03:28 | 8ee838166850acad820f9709ed82699ade9f2ca7 | 0 $ | Livrée sous réserve de la conformité 4.14. Revue : préchargement hors Cache de réponses (use_cache=False, rejeu repaie le préchargement, documenté), tests de lecture du cache avec Questions distinctes et d'écriture au Poste indexing. Fin de l'epic 6 (conformité 4.14 en attente). |
| 4.7 | 03:17 | 03:39 | a66ad63e4371f63f8913293f1d6c1089986993b3 | 0 $ | Revue : toutes les Questions reposées en after_update (régression mesurée), Scénario + Paliers exécuté (cibles requises au tirage, Scénario appliqué au sous-corpus), test d'update incrémental naive_rag, Scénario validé avant le dossier. |
| 7.1 | 03:31 | 03:48 | 8a54f504b778c5cb7d00f9b876b3a14225e58297 | 0 $ | Livrée sous réserve de la conformité 4.14. Revue : groupe refusé s'il dépasse la fenêtre du modèle de résumé (et contrôle avant chaque appel), group_max >= 2, pas de résumé d'une feuille unique, regroupement vectorisé, tests de bornes et d'Ancrages à tous niveaux. 805 tests verts. |
| 4.8 | 03:42 | 04:11 | 653cc3d49cc7a5cef1ec4cfc548c335b26003c9c | 0 $ | Reprise --reprendre, Questions restantes en budget_exceeded, empreinte comparée à plafonds égaux. Revue : réponse conforme mise en cache même si settle est interrompu, empreintes du Corpus, du Scénario et du Catalogue au manifeste (reprise refusée si elles changent), run completed → code 0. |
| 7.2 | 03:50 | 04:14 | 4274fba212307ddbe4aef0834e2af13cceefe781 | 0 $ | Livrée sous réserve de la conformité 4.14. Revue : sections lues bornées par la fenêtre avant generate, sélection découpée en lots (PDF de 150 pages), update d'un Document modifié testé sur le vrai Scénario, Document absent de l'ancien index reconstruit. |
| 7.3 | 04:16 | 04:38 | 9ec982f85724c389eb25a8545cc3ef669c68418f | 0 $ | Livrée sous réserve de la conformité 4.14 ; affichage du taux reporté au Rapport. Revue : 1 high corrigé (juge de fidélité d'une autre Famille que le modèle de compilation, refus si même Famille), graine et juge dans l'index_key, Ancrages limités au Document source. |
| 4.9 | 04:12 | 04:58 | 84c3c5b5a1f450f5e544a460ab2dc4da52f93e4b | 0 $ | Revue : nDCG sans double gain par Ancrage, Citations inventées → citation_correctness non, unjudged au manifeste et reprise possible d'un run completed avec Critères manquants, Critère absent sans plantage, test d'égalité de bout en bout. 885 tests verts. |
| 7.4 | 04:39 | 05:00 | 57ac1280e6b483ca8d5d6d91682986e3f89fa0e2 | 0 $ | Livrée sous réserve de la conformité 4.14. Revue : coût des tentatives non conformes rendu par LLMResult.retry_cost_uncached et compté dans la borne, answer imposé au dernier pas, schéma compté dans la réserve, ConfigError si les résultats ne tiennent pas, agentic.json malformé → WlError. |
| 4.10 | 05:02 | 05:21 | aae51740d069cb4b8e20e27464140c4ea875e7ab | 0 $ | Revue : IC apparié testé contre scipy.stats.bootstrap et p-valeur contre une valeur théorique, graine_derivee conforme à AD-20, compare() sans Question commune → None, NaN refusés. 922 tests verts. |
| 7.5 | 05:05 | 05:34 | 95a07c2f76f13b300a7ffa4a23ddbfb69a262cca | 0 $ | GraphStore networkx, extraction, Louvain à graine dérivée, rapports de communauté. Revue : fusion des entités indépendante de l'ordre (type extrait > générique, nom le plus mentionné), slug_entite (’ et œ/æ), réserve du schéma, couper() dans core/fenetre.py, test PYTHONHASHSEED. 945 tests verts. |
