---
story: "6.1"
title: RAG naïf
status: done
---

# Story 6.1 : RAG naïf

## Code Map

- `src/wavelibrarian/components/vector_stores/numpy_exact.py` : `NumpyExactStore` (`("vector_store", "numpy_exact")`, `hybrid = false`, Param `dim`).
- `src/wavelibrarian/components/retrievers/dense.py` : `DenseRetriever` (`("retriever", "dense")`).
- `src/wavelibrarian/architectures/naive_rag.py` : `NaiveRag` (`k: 5`, `query_params = {k}`, `incremental_update`, `embedder_dim()`).
- Tests : `tests/unit/architectures/test_story_6_1.py` (Faux LLM, faux embedder dim 64, profil `test`).

## Design Notes

- Store : matrice float32 en mémoire, recherche exacte par produit scalaire, tri (score décroissant, id). Sauvegarde dans `vectors/` : `ids.json` (dim, ids) et `vectors.npy` (sans pickle). `add` remplace un id déjà présent (nécessaire à la mise à jour : un Document modifié garde ses `passage_id` d'ordinal égal). Dimension fixée par le Param `dim`, sinon par le premier `add` ou le `load` ; une autre dimension lève `WlError`.
- `NaiveRag` injecte `dim = embedder.dim` dans les Params du store à sa construction (`_nouveau_store`) ; l'Architecture reste sans état d'index, `load` crée un store neuf. Embedder par défaut `sentence_transformers` (les tests passent `fake`).
- Retriever `dense` : élargit la recherche tant que des ids inconnus des Passages réduisent la liste sous `k` (comme `lexical`). Ni l'un ni l'autre ne tracent ; l'Embedder trace ses lots.
- `index` : `passages.jsonl` + `vectors/`. `update` : charge le store de l'ancien dossier, retire les Passages des Documents supprimés ou remplacés, encode seuls les Passages des Documents ajoutés ou modifiés, écrit le nouveau dossier.
- `embedder_dim()` renvoie `embedder.dim` : l'`IndexCache` l'écrit au manifeste (64 avec le faux embedder).

## Tâches et critères

- [x] `numpy_exact` enregistré, `hybrid = false`; 10 ajouts, 2 suppressions, `k = 5` classés par produit scalaire : `test_numpy_exact_ajout_suppression_recherche_et_ordre`.
- [x] Ex æquo départagés par id : `test_numpy_exact_ex_aequo_departages_par_id`.
- [x] `save` puis `load` ailleurs identiques ; dimension différente refusée (`add`, `search`, `load`) : `test_numpy_exact_save_load_et_dimension_refusee`, `test_numpy_exact_add_remplace_un_id_existant`.
- [x] `dense` : `query_vector = None` appelle `embed_queries([query])`, rangs 1 à k : `test_dense_appelle_embed_queries_et_classe_de_1_a_k`, `test_dense_sans_store_refuse`.
- [x] `naive_rag` : 5 Passages classés `ranked`, prompt avec les 5 Passages, Citation hors contexte retirée et comptée, manifeste `embedder_dim: 64` : `test_naive_rag_cycle_complet_manifeste_et_citations`.
- [x] `k: 3` réutilise l'index, 3 Passages : `test_naive_rag_k_hors_de_la_cle_et_index_reutilise`.
- [x] Mise à jour incrémentale : seuls les Documents ajoutés ou modifiés réencodés (compteur du faux embedder), Passages supprimés ou remplacés retirés : `test_naive_rag_update_incremental`.
- [x] Reports hérités : `embedder_dim()` redéfini, `tokenizer=` passé à `build_arch_answer` (troncature déjà couverte par `test_bm25_only_tronque_au_dela_de_8000_tokens`, même code), `update` retire les Passages supprimés.

## Auto Run Result

- Statut : review. Vérifications finales dans le rapport de l'orchestrateur.
- Reports : la Configuration `naive_rag` dans `experiments/mini-test.yaml`, la suite `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` n'existent pas encore dans ce dépôt (story 4.14 non livrée) : à ajouter à l'intégration. `update` n'est testé qu'en appel direct ; l'enchaînement par `IndexCache.build(post="update")` relève du Runner (4.7).
- Un Document modifié garde ses `passage_id` d'ordinal égal (l'id ne dépend que du Document et de l'ordinal) : le vecteur est remplacé, pas dupliqué.

## Revue

- medium, second avis : test de mise à jour avec `doc_id` inchangé alors qu'un `modified` réel le change. Corrigé : `test_naive_rag_update_scenario_reel_depuis_le_cache` applique le vrai Scénario du Mini-corpus (`appliquer_fichier`) ; le code était déjà correct (sonde : 2 Passages sortants, 0 restant).
- medium, second avis : enchaînement index servi par l'`IndexCache`, `update` sur instance neuve, `load` sur une autre, puis recherche jamais exécuté. Corrigé par le même test (aucun ancien Passage retrouvé, 5 Passages rendus). L'appel `update` par le Runner reste à la story 4.7.
- low, second avis : score non cosinus si les vecteurs ne sont pas normés. Rejeté : le contrat impose des Embedders de norme L2 = 1 (faux et `sentence_transformers` normalisent) ; le store reste un produit scalaire exact, comme documenté.
- low, second avis : un `add` refusé fixait la dimension du store vide. Corrigé : dimension fixée après validation complète (`test_numpy_exact_ajout_rate_ne_fixe_pas_la_dimension`).
- low, second avis : `search` sur un store vide sans dimension levait une erreur. Corrigé : renvoie `[]`.
- low, second avis : modèle par défaut de l'Embedder absent de `index_key` sans résolution des Params. Rejeté pour la story : comportement commun d'`ArchitectureBase.index_key()` (4.3), la Configuration résolue le fixe en production.
- low, revue : `load` d'un `ids.json` sans `dim` ou `ids` levait `KeyError`. Corrigé : `WlError` « illisible ».
- Reports (inchangés) : Configuration `naive_rag` dans `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` à passer quand 4.14 sera livrée ; embedder `sentence_transformers` réel à vérifier par `pytest -m real_local` après le go GPU.
