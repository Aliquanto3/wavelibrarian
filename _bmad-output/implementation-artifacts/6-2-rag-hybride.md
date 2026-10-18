---
story: "6.2"
title: RAG hybride
status: done
---

# Story 6.2 : RAG hybride

## Code Map

- `src/wavelibrarian/components/retrievers/hybrid.py` : `HybridRetriever` (`("retriever", "hybrid")`, Params `fusion: rrf | weighted`, `rrf_k: 60`, `weight_dense: 0.5`, `candidates: 50`) et fonctions pures `fusion_rrf`, `fusion_ponderee`.
- `src/wavelibrarian/components/rerankers/fake.py` : `FakeReranker` (`("reranker", "fake")`, recouvrement de mots, span `rerank`).
- `src/wavelibrarian/architectures/hybrid_rag.py` : `HybridRag` (`fusion`, `rrf_k`, `weight_dense`, `reranker: null`, `rerank_top_n: 20`, `k: 5` ; `incremental_update`, `embedder_dim()`).
- Tests : `tests/unit/architectures/test_story_6_2.py` ; `tests/unit/test_registry.py` ajusté (le kind `reranker` n'est plus vide).

## Design Notes

- Index : `passages.jsonl`, `vectors/` (`numpy_exact`) et `lexical/` (`bm25`), construits ensemble. `update` retire les Passages sortants des deux index et n'encode que les Documents ajoutés ou modifiés.
- `query_params` = `k`, `retriever`, `fusion`, `rrf_k`, `weight_dense`, `reranker`, `rerank_top_n` : tous hors de la clé d'index. « Dense seul » et « lexical seul » = `retriever: {name: dense}` ou `lexical` sur le même index ; fusion = `hybrid` ; reranker en plus = `reranker: {name: fake}`.
- Les Params de fusion vivent sur l'Architecture et sont injectés dans le Retriever `hybrid` à la construction (une valeur de `retriever.params` différente du défaut du Retriever et de celle de l'Architecture lève une `ConfigError`).
- Fusion : chaque liste a `max(k, candidates)` Passages. RRF : somme de 1 ÷ (`rrf_k` + rang). Pondérée : min-max par liste (liste à scores égaux : 1,0 pour chacun), absent d'une liste = 0. Ex æquo par `passage_id`.
- Reranker : l'Architecture récupère `max(k, rerank_top_n)` candidats, le Reranker reclasse les `rerank_top_n` premiers (notes = part des mots de la requête retrouvés, égalités par rang d'origine) et trace le span `rerank` (étape `rerank`, latence, `wl.candidates`). Les `k` premiers sont gardés, rangs renumérotés ; si `k > rerank_top_n`, les candidats non reclassés complètent dans l'ordre de la fusion, score plafonné au dernier score reclassé (scores décroissants avec le rang).
- `capabilities.requires_hybrid_store = false` : deux index distincts.

## Tâches et critères

- [x] RRF : score = somme de 1 ÷ (`rrf_k` + rang), ordre calculé à la main : `test_rrf_somme_des_inverses_et_ordre_calcule_a_la_main`.
- [x] Pondérée : min-max puis `weight_dense` × dense + (1 − `weight_dense`) × lexical : `test_ponderee_normalise_min_max_avant_de_combiner`.
- [x] Retriever `hybrid` sur de vrais index, deux index exigés, valeur de `fusion` validée : `test_hybrid_retriever_fusionne_les_deux_listes`, `test_hybrid_retriever_exige_les_deux_index`.
- [x] `hybrid_rag` : Passages issus de la fusion, k classés, manifeste `embedder_dim: 64` : `test_hybrid_rag_cycle_complet_et_manifeste`.
- [x] Dense seul, lexical seul, fusion, pondérée, reranker en plus : chaque combinaison valide : `test_hybrid_rag_chaque_combinaison_d_etages_est_valide`.
- [x] `fusion`, `weight_dense`, `reranker`, `k` dans `query_params`, index réutilisé : `test_hybrid_rag_etages_de_requete_reutilisent_l_index`.
- [x] Reranker `fake` : 20 candidats reclassés, k gardés, span `rerank` distinct avec latence : `test_hybrid_rag_reranker_reclasse_20_candidats_garde_k_et_trace_rerank`, `test_reranker_fake_recouvrement_et_span_rerank`, cas `k > rerank_top_n` : `test_hybrid_rag_k_superieur_a_rerank_top_n`.
- [x] Store `numpy_exact` refusé par une Architecture qui exige un store hybride, `hybrid_rag` non : `test_store_non_hybride_refuse_pour_une_architecture_qui_l_exige_mais_pas_hybrid_rag`.
- [x] Reports hérités : `embedder_dim()` redéfini, `tokenizer=` passé à `build_arch_answer`, `update` retire les Passages supprimés des deux index : `test_hybrid_rag_update_incremental_sur_les_deux_index`.

## Auto Run Result

- Statut : review. Vérifications finales dans le rapport de l'orchestrateur.
- Reports : Configuration `hybrid_rag` dans `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` absents du dépôt (story 4.14 non livrée) ; `update` testé en appel direct (l'enchaînement par `IndexCache.build(post="update")` relève du Runner, 4.7). Reranker cross-encoder réel (import paresseux) non écrit : seul `fake` est requis par la story.
- Test existant ajusté : `test_discover_recursif_et_idempotent` supposait le kind `reranker` vide.

## Revue

- medium, second avis 1 : corrigé. Avec `k > rerank_top_n`, les non reclassés gardaient leur score de fusion (~0,016) après des scores de recouvrement (0,0) : leur score est plafonné au dernier score reclassé, ordre inchangé. Tests `test_hybrid_rag_k_superieur_a_rerank_top_n` et `test_hybrid_rag_reranker_ne_reclasse_que_top_n_valeurs_a_la_main` (valeurs écrites à la main).
- medium, second avis 2 : corrigé en partie. Une valeur de `retriever.params` (`fusion`, `rrf_k`, `weight_dense`) qui diffère du défaut du Retriever et de l'Architecture lève une `ConfigError`. La comparaison se fait au défaut, parce que la résolution complète déjà `retriever.params`. Test `test_hybrid_rag_fusion_reglee_sur_l_architecture_seule`. Écarté : refuser ces paramètres quand le retriever n'est pas `hybrid`. Après résolution, ils sont toujours présents, et ils sont inoffensifs puisque ce sont des `query_params` sans effet sur l'index.
- low, second avis 3 : écarté. Une liste à scores égaux est normalisée à 1,0 ; le cas typique est une liste à un seul Passage, qui est bien le meilleur de sa liste. La constante est la même pour tous les Passages de la liste et ne change pas leur ordre relatif.
- low, second avis 4 : corrigé. Le test d'`update` interroge le BM25 avec le texte des Passages supprimés et vérifie qu'ils sont absents. Une mutation (suppression lexicale retirée) fait échouer le test.
- low, second avis 5 : corrigé. Un test à valeurs écrites à la main s'ajoute à l'oracle d'intégration. Le test unitaire du reranker utilisait déjà des valeurs à la main.
- low, second avis 6 : écarté. `count("decouvert") == 1` vérifie l'idempotence. `sorted(names) == [...]` casserait au prochain reranker enregistré.
- low, second avis 7 : reporté (déjà noté). La Configuration `mini-test`, la conformité et SM-3 attendent la story 4.14. À vérifier : `hybrid_rag` (rrf, puis `reranker: fake`) dans `experiments/mini-test.yaml`, puis passage de `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` sans réseau.
