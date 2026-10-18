# Epic 6 Context: Architectures à recherche, du RAG naïf au CAG

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Permettre à Anaël de comparer aux Baselines cinq Architectures du niveau 1 : RAG naïf, RAG hybride, HyDE, Corrective RAG et CAG. Chacune est sélectionnable par Expérience et validée par la suite de conformité. L'epic atteint le minimum de SM-3 (quatre Architectures du niveau 1 en plus des Baselines) et livre les Composants qui manquaient (store vectoriel, retrievers, reranker, decider, rewriter).

## Stories

- Story 6.1: RAG naïf
- Story 6.2: RAG hybride
- Story 6.3: HyDE
- Story 6.4: Corrective RAG
- Story 6.5: CAG

## Contraintes du run autonome

- Aucun réseau ni API dans les tests : Faux LLM (`fake-llm-a/b/c`), faux embedder (dim 64), profil `test`.
- `sentence-transformers` et `torch` ne sont pas installés (extra `local`) : les tests n'utilisent que le faux embedder.
- Ollama et GPU seulement après le go d'Anaël (pas de `pytest -m real_local`, pas de `wl run` sur `mini-cpu.yaml`).
- Pas d'extra lourd ni de téléchargement de plus de 1 Go ; `OMP_NUM_THREADS=4`, RAM ≤ 6 Go, pas de pytest parallèle.

## Requirements & Constraints

- Règle commune : chaque story livre une Architecture enregistrée sous son nom (`naive_rag`, `hybrid_rag`, `hyde`, `corrective_rag`, `cag`) avec les défauts de Params (`k = 5` ; `hybrid_rag` : `fusion = rrf`, `reranker = null` ; `hyde` : `mix_question = false` ; `corrective_rag` : `threshold = 0.5`, `max_loops = 2`), plus ses Composants manquants et une Configuration ajoutée à `experiments/mini-test.yaml`. Livrée seulement si `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` passent avec elle, sans réseau. Aucune story ne modifie le runner, la passerelle ni le Rapport.
- RAG naïf : exactement k Passages classés par score décroissant (`retrieval_method: ranked`), génération avec Citations ; une Citation hors du contexte est retirée et comptée (`invalid_citations`). Mise à jour incrémentale : seuls les Documents ajoutés ou modifiés sont réencodés, les supprimés quittent le store.
- Hybride : BM25 et dense fusionnés par RRF (somme de 1 ÷ (`rrf_k` + rang), `rrf_k = 60`) ou pondération (min-max puis `weight_dense` = 0,5) ; reranker optionnel sur les `rerank_top_n` meilleurs ; chaque étage s'active séparément ; la latence du reranker est un span `rerank` distinct.
- HyDE : la réponse hypothétique (rôle `hyde`, step `hyde`, poste `query`) est tracée à part, son vecteur sert à la recherche (option : moyenne renormalisée avec la question), elle n'apparaît jamais dans le Contexte ni dans les Citations.
- Corrective RAG : le Decider note chaque Passage dans [0, 1] (hors bornes = sortie non conforme) ; seuls les Passages ≥ seuil entrent dans le Contexte ; si aucun, reformulation et nouvelle recherche, au plus `max_loops` boucles, puis abstention sans appel `generate`. Chaque boucle est tracée (`crag.grade.loopN`, `crag.rewrite.loopN`).
- CAG : tout le Corpus étiqueté (un bloc par Ancrage) est préchargé dans le system avec `cache_system: true`, au poste `indexing`, par `load` (donc identique avec index construit ou servi par le cache) ; la seconde Question montre des tokens en cache non nuls, tracés à part ; `retrieval_method: cited`. Générateur sans `prompt_cache` au Catalogue : refus avant tout appel. `check(profile)` : inapplicable avec raison si le Corpus dépasse la fenêtre ou le palier de `claude-haiku-5-5` (100 000 tokens). Corpus sous `min_cacheable_tokens` : l'appel réussit, tokens en cache nuls.

## Technical Decisions

- Registre : `@register(kind, name)`, `Params` pydantic `extra="forbid"` et `frozen=True`, construction `cls(params, ctx)`, sous-Composants par `ctx.build`. Nouveaux `kind` à utiliser : `vector_store` (`numpy_exact`), `retriever` (`dense`, `hybrid`), `reranker` (`fake`), `decider` (`llm`), `query_rewriter` (`llm`).
- `VectorStore` : `capabilities: StoreCapabilities(hybrid, deletions)`, `dim`, `add`, `delete`, `search` (score décroissant, ex æquo par id), `save`, `load` ; dimension différente refusée. `numpy_exact` : `hybrid = false`.
- `Retriever.retrieve(query, k, index: SearchIndex, query_vector=None)` : si `query_vector` est `None`, appelle `index.embedder.embed_queries([query])`. `SearchIndex` (passages, embedder, vectors, lexical) est assemblé par l'Architecture. L'Embedder renvoie des vecteurs de norme L2 = 1 ; `embed_passages` / `embed_queries`.
- `ArchCapabilities` : `incremental_update`, `retrieval_method`, `full_corpus_in_prompt`, `requires_prompt_cache`, `requires_hybrid_store`. `hybrid_rag` n'exige pas de store hybride (deux index) ; une Architecture de test qui l'exige est refusée avec `numpy_exact` (story 1.6).
- `index_key` : défaut = Params moins `query_params`, plus parser et tokenizer. Paramètres de requête (`k`, `fusion`, `weight_dense`, `reranker`, `rerank_top_n`, `mix_question`, `threshold`, `max_loops`) dans `query_params` : changer d'étage réutilise l'index. Manifeste d'index : `embedder_dim` lu sur l'attribut `embedder.dim`. Instance neuve + `load` après `index` ou `update`.
- Traces : une Architecture ou un Retriever ne tracent jamais ; spans LLM par la passerelle seule, Embedder et Reranker tracent leurs lots. Rôles fermés (`hyde`, `rewrite`, `grade_relevance`, `generate`) ; un nouveau rôle modifie `roles.py` et `fake.py` dans la même story. Sorties scénarisées par `FakeProvider.script(role, step_pattern, sortie)`. Bornes (boucles) vérifiées avant chaque appel.
- Déterminisme : `temperature: 0`, égalités départagées par id, listes triées.
- Existant réutilisable (epic 4) : chunker `fixed_tokens` (`size: 300`, `overlap: 50`), `labeled`, `build_arch_answer(..., tokenizer=...)`, `LLMGenerator` (`cache_system`), index `bm25` + retriever `lexical`, `_passages.py` (`passages.jsonl`), `IndexCache`, `index_key`. Modèle des Baselines : `bm25_only` (index dans le dossier, `load` sur instance neuve) ; `long_context` (`check`, tokens estimés avec `token_factor` 1,5 pour Haiku).

## Cross-Story Dependencies

- 6.1 pose `numpy_exact`, le retriever `dense` et l'index dense ; 6.2 (index dense + `bm25`), 6.3 (même index que `naive_rag`) et 6.4 (réutilise un index dense de mêmes paramètres) en dépendent.
- 6.5 est indépendante de 6.1 à 6.4 mais s'appuie sur `cache_system` et `check()` de `long_context` (4.2).
- Chaque story dépend de la suite de conformité et du test SM-3 de 4.14 et ajoute sa Configuration à `mini-test.yaml`.
- L'epic 7 réutilise `dense`, `numpy_exact` et le Reranker.

## Reports hérités

- Chaque Architecture à embeddings redéfinit `ArchitectureBase.embedder_dim()` (4.3) ; le manifeste d'index porte `embedder_dim: 64` avec le faux embedder.
- Conformité : `CONFORMANCE_QUESTION_ID = "q-001"` s'importe par `from conftest import` ; casse avec `--import-mode=importlib` (3.7).
- Baselines/Architectures : passer `tokenizer=self.ctx.tokenizer_for(generator.model_id)` à `build_arch_answer` et tester la troncature au-delà de 8 000 tokens (4.1, traité en 4.2).
- Condition contexte parfait de `long_context` passe par `answer_with_context`, donc sans cache du system ; vaut aussi pour `cag` (4.2).
- Mise à jour : `IndexCache.build(post="update")` pour la phase après mise à jour (4.3) ; un `update` incrémental doit retirer les Passages des Documents supprimés.
- Parser composite `markdown+pdf_text` possible dans la clé d'index (version du Parser incluse, 4.3).
- Passerelle : `cache_write_1h` n'est pas facturé, `Usage` n'a pas de poste 1 h ; à garder en tête pour les coûts CAG (1.4).
- Arbitrages en attente touchant les coûts : AC 3 de 1.4 (palier ×5 contre 0,60), AC 2 de 1.8 (plafond de période).
- `check(profile)` pour CAG : tokens estimés avec le facteur du Catalogue, comme `long_context` (4.2).
- Quand Ollama et le GPU seront libres : `uv sync --extra local`, `wl installer --profil cpu`, `pytest -m real_local` (embedders réels ; 1.12).
