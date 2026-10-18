# Epic 7 Context: Architectures à structure dérivée, de RAPTOR à GraphRAG

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Ajouter au comparatif les Architectures qui construisent une structure à l'indexation : RAPTOR, PageIndex, LLM Wiki, recherche agentique, puis GraphRAG, LazyGraphRAG et LightRAG. À la fin, `experiments/mini-test.yaml` couvre les 15 Architectures du registre et le Rapport compare les Baselines et les 12 Architectures du niveau 1.

## Stories

- Story 7.1: RAPTOR
- Story 7.2: PageIndex
- Story 7.3: LLM Wiki
- Story 7.4: Recherche agentique
- Story 7.5: Graphe de connaissances (GraphStore, extraction, communautés, rapports)
- Story 7.6: GraphRAG, recherche locale et globale
- Story 7.7: LazyGraphRAG
- Story 7.8: LightRAG

## Contraintes du run autonome

- Aucun réseau ni API dans les tests : Faux LLM à rôles scénarisés (`fake-llm-a/b/c`), faux embedder (dim 64), profil `test`.
- networkx seulement, tel que déclaré dans `pyproject.toml` (3.7) ; aucun extra lourd, aucun téléchargement de plus de 1 Go.
- Ollama et GPU seulement après le go d'Anaël (pas de `pytest -m real_local`, pas de `wl run` sur `mini-cpu.yaml`) ; `OMP_NUM_THREADS=4`, RAM ≤ 6 Go, pas de pytest parallèle.

## Requirements & Constraints

- Règle commune de l'epic 6 : chaque story livre une Architecture enregistrée sous son nom (`raptor`, `pageindex`, `llm_wiki`, `agentic`, `graphrag`, `lazy_graphrag`, `lightrag`) avec ses défauts de Params, ses Composants manquants et une Configuration dans `experiments/mini-test.yaml`. Livrée seulement si `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` passent sans réseau. Une story qui déroge le dit. La 7.5 n'enregistre aucune Architecture. Si le run s'arrête, chaque Architecture livrée doit passer la conformité.
- RAPTOR : arbre de résumés par regroupement récursif (`group_min = 5`, `group_max = 10`, `max_depth = 3`), regroupement déterministe, dernier groupe d'un niveau toléré sous `group_min` (règle documentée). Nœud : `level` ≥ 1, `child_ids`, `doc_id: null` si plusieurs Documents, `anchor_ids` = union de ceux des feuilles, `passage_id = sha16("node","raptor",level,*sorted(child_ids))`. Recherche dense sur l'arbre aplati ; Citation d'un résumé convertie vers les Ancrages des feuilles. Pas de mise à jour incrémentale : reconstruction au poste `update`.
- PageIndex : un arbre par Document (titres, ou pages pour un PDF sans titre), résumé court et Ancrage par nœud, persistant dans le dossier d'index (`load` sans appel). Navigation par `select_nodes` sans embedding, `max_nodes_read = 8` vérifié avant chaque lecture et chaque appel, un span `pageindex.select.<n>` par sélection. Identifiant de nœud inconnu : ignoré et journalisé ; aucun nœud valide : abstention. `retrieval_method: provided`.
- LLM Wiki : rôle `wiki_compile` (poste `indexing`), chaque page = Passage de `level` 1 aux Ancrages déclarés filtrés sur ceux qui existent ; page sans Ancrage valide écartée et comptée. Recherche par index lexical sur le wiki. `fidelity_sample = 5` pages tirées de façon déterministe, rôle `wiki_fidelity`, `wiki_fidelity.json` (pages, `claims`, `supported`) écrit dans le dossier d'index. Mise à jour incrémentale (poste `update`, fidélité remesurée, aucune page du Document supprimé). Seule story de l'epic qui touche au runner et au Rapport : copie générique de `wiki_fidelity.json` dans `runs/<run_id>/` et taux `supported ÷ claims` par Configuration.
- Agentique : outils `search` (BM25), `read` (par `anchor_id`, erreur renvoyée à l'agent pour un Ancrage inconnu), `list`, en lecture seule. `max_steps = 8`, `max_cost_per_question = 0.05 USD`, vérifiés avant chaque appel sur la somme des `cost_uncached` (comportement identique avec ou sans Cache de réponses). Spans `agent.step<n>`. Action inconnue ou `args` invalides : non conforme, un nouvel essai, puis `status: error`. Dépassement de borne : abstention.
- Graphe (7.5) : GraphStore `networkx` (fusion des entités par `slug`, insensible casse et accents ; `remove_passages` retire les orphelins ; `save`/`load` identiques), extracteur LLM `extract_entities` réutilisable (entités et relations rattachées aux `passage_id`), communautés Louvain déterministes (graine de l'Expérience, ex æquo par id), rapports `community_report` = Passages de `level` 1 aux Ancrages unis.
- GraphRAG : indexation (extraction, communautés, rapports) au poste `indexing`. Local : entités proches par embedding de leurs descriptions (`numpy_exact`), contexte = relations, Passages sources, rapports. Global : map (`global_map`, un appel par lot de rapports) puis reduce (`generate`), spans distincts. `search` dans `query_params`. Mise à jour incrémentale : extraction des seuls Passages changés, rapports régénérés pour les seules communautés modifiées (poste `update`).
- LazyGraphRAG : zéro appel LLM à l'indexation (concepts par l'heuristique de `corpus/entities.py`, graphe de cooccurrence, communautés déterministes, aucun span `llm`). À la requête : classement des communautés, `grade_relevance` borné par `relevance_budget = 20` (vérifié avant chaque appel, dans `query_params`), puis `generate` ; scores tous nuls : abstention sans `generate`. Architecture distincte de `graphrag` dans `wl registre`.
- LightRAG : deux index denses séparés (entités, relations), pas de rapports de communauté ; recherche bas niveau (entités) et haut niveau (relations), Passages sources dédoublonnés ; mot-clé = embedding direct de la Question (simplification documentée en docstring). Mise à jour par union de sous-graphes, aucun appel sur un Passage inchangé (compteur du Faux LLM).

## Technical Decisions

- Registre : `@register(kind, name)`, `Params` pydantic `extra="forbid"` et `frozen=True`, construction `cls(params, ctx)`, sous-Composants par `ctx.build`. Nouveau `kind` : `graph_store` (`networkx`). Réutiliser `numpy_exact`, `dense`, `lexical`/`bm25`, `fixed_tokens`, `labeled`, `build_arch_answer(..., tokenizer=self.ctx.tokenizer_for(model_id))`, `LLMGenerator`, `IndexCache`, `_passages.py`.
- `Passage.level` > 0 pour résumés, pages de wiki et rapports de communauté ; un nœud porte dès sa création les `anchor_ids` de ses feuilles. Citations par étiquettes `[S1]…[Sn]` et table `labels` ; les invalides sont retirées et comptées. Pertinence en recherche par recouvrement d'Ancrages : aucun traitement dans `scoring/`.
- Rôles fermés : `summarize`, `select_nodes` (`question`, `nodes`, `max` -> `{node_ids, done}`), `agent_step` (`question`, `step`, `last_results` -> `{action, args}`), `extract_entities`, `wiki_compile`, `wiki_fidelity`, `community_report`, `global_map`, `grade_relevance`, `generate`. Un nouveau rôle ou un changement de sortie modifie `roles.py` et `fake.py` dans la même story. Sorties scénarisées par `FakeProvider.script(role, step_pattern, sortie)`. Agent et PageIndex fonctionnent par protocole JSON, sans tool calling natif.
- Les Faux : `agentic` et `pageindex` doivent produire au moins une Citation valide sur une question factuelle du Mini-corpus.
- Traces : une Architecture ou un Retriever ne tracent jamais ; spans LLM par la passerelle seule (le `step` nomme le span), Embedder et Reranker tracent leurs lots. Poste fixé par le runner : résumés, extraction, rapports, compilation au poste `indexing` ; mises à jour au poste `update`. Bornes vérifiées avant chaque appel.
- Cache d'index : `index_key` = Params moins `query_params`, plus parser et tokenizer ; paramètres de requête (`search`, `relevance_budget`, `max_steps`, `max_nodes_read`, `max_cost_per_question`, `k`) dans `query_params`. Instance neuve + `load` après `index` ou `update`. Chaque Architecture à embeddings redéfinit `embedder_dim()` (manifeste : 64 avec le faux embedder). `ArchCapabilities` : déclarer `incremental_update` et `retrieval_method` justes.
- Déterminisme : `ctx.rng(*clés)` ou `default_rng(sha16(...))`, `temperature: 0`, listes triées, égalités par id, graine de l'Expérience pour Louvain et pour l'échantillon de fidélité.
- Coût : le Rapport ventile déjà par Type de question et par Poste ; ne pas le modifier hors 7.3.

## Cross-Story Dependencies

- 7.1 et 7.6 utilisent `numpy_exact` et `dense` de l'epic 6 ; 7.4 réutilise l'index `bm25` ; 7.3 un index lexical.
- 7.5 précède 7.6, 7.7 et 7.8 (GraphStore, extracteur, communautés, rapports). 7.7 réutilise aussi `corpus/entities.py` (epic 2) ; 7.8 réutilise l'extracteur et le GraphStore.
- 7.3 est la seule à toucher au runner et au Rapport (copie de `wiki_fidelity.json`).
- Chaque story dépend de la suite de conformité et du SM-3 de 4.14 (encore en attente à la fin de l'epic 6) et ajoute sa Configuration à `mini-test.yaml` ; 7.8 clôt l'epic par la vérification des 15 Architectures.

## Reports hérités

- Cache d'index (4.4) : une Architecture qui appelle le LLM à l'indexation (RAPTOR, PageIndex, LLM Wiki, GraphRAG, LightRAG), lancée avec un Faux LLM scénarisé, ne doit pas laisser dans `WL_HOME/index/` un index construit sur une sortie scénarisée (isoler `WL_HOME`/cache de réponses dans les tests scénarisés).
- Chaque Architecture à embeddings redéfinit `ArchitectureBase.embedder_dim()` (4.3, 6.1).
- Extraction d'entités (2.4) : l'heuristique hors ligne rate les noms en début de phrase ; à garder en tête pour LazyGraphRAG et les questions multi-hop.
- `IndexCache.build(post="update")` pour la phase après mise à jour ; un `update` incrémental retire les Passages des Documents supprimés ; un Document modifié garde ses `passage_id` d'ordinal égal (remplacer, pas dupliquer).
- Passer `tokenizer=` à `build_arch_answer` et tester la troncature au-delà de 8 000 tokens depuis une Architecture (4.1).
- Condition contexte parfait : passe par `answer_with_context`, sans cache du system (4.2).
- `CONFORMANCE_QUESTION_ID = "q-001"` s'importe par `from conftest import` ; casse avec `--import-mode=importlib` (3.7).
- Questions ancrées sur un Document du Scénario : inapplicables en phase base (4.6) ; toute Expérience à Paliers sur le Mini-corpus pose `max_questions` ou un `tier` adapté (4.6).
- Rapport (4.12) : l'écriture du préchargement CAG revient à chaque Exécution au poste `indexing` (6.5) ; exclure les spans `wl.llm_cache_hit=true` de la durée locale (4.5).
- Passerelle : `cache_write_1h` non facturé (1.4) ; arbitrages en attente sur AC 3 de 1.4 et AC 2 de 1.8.
- Quand Ollama et le GPU seront libres : `uv sync --extra local`, `wl installer --profil cpu`, `pytest -m real_local` (1.12).

Leçons de l'epic 6 :

- Les Architectures ne se tracent pas elles-mêmes : seuls la passerelle, l'Embedder et le Reranker émettent des spans (revue 6.x, tests d'espion).
- Les retrievers ou options non supportés sont refusés à la construction, avant tout appel payant (ex. `hyde` avec un retriever `hybrid` échouait après l'appel payé).
