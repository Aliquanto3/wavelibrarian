---
story: "7.6"
title: "GraphRAG, recherche locale et globale"
status: review
---

# Story 7.6 : GraphRAG, recherche locale et globale

## Code Map

- `src/wavelibrarian/architectures/graphrag.py` : `GraphRag`, enregistrée `("architecture", "graphrag")`. Assemble `EntityExtractor`, `NetworkxGraphStore`, `detect_communities` / `louvain_seed(ctx.seed)` et `CommunityReporter` (story 7.5), un store `numpy_exact` pour les entités, le Generator `llm`.
- Dossier d'index : `passages.jsonl` (feuilles et rapports de `level` 1), `vectors/` (entités), `graph/graph.json`, `communities.json` (id, membres, signature, `report_id`), `entities.json` (empreinte du texte embarqué de chaque entité).
- `tests/unit/architectures/test_story_7_6.py` (17 tests). Aucun changement de `roles.py`, `fake.py`, du runner ni du Rapport.

## Design Notes

- Les Architectures ne voient pas le Type de la Question (AD-6) : le mode est `search: local|global`, dans `query_params` avec `k`, `k_entities`, `k_relations`, `k_reports`, `map_batch`, `max_map_batches`, `map_model`, `map_max_tokens`. Les deux recherches partagent l'index (`index_key` identique). C'est la Configuration qui associe `search: global` aux Questions `global`.
- Local : entités les plus proches (cosinus sur « nom : description », `embed_queries`) ; contexte dans l'ordre Passages sources (somme des proximités des entités qui les citent), un bloc « Relations » (relations incidentes, poids décroissant ; Passage synthétique de `level` 1 aux Ancrages des Passages d'où elles viennent), rapports des communautés. Graphe sans entité proche : abstention sans `generate`. `retrieved` trié par score décroissant.
- Global : rapports du plus gros groupe au plus petit, lots de `map_batch`, un `global_map` par lot (step `graphrag.map.<n>`, `max_map_batches` vérifié avant chaque appel), puis reduce par le Generator (`generate`). Chaque sortie de map est un Passage de `level` 1 aux Ancrages unis de son lot ; une Citation remonte donc aux Ancrages des rapports. Sortie de map vide : lot ignoré ; aucune sortie : abstention sans `generate`. `retrieved` = les rapports lus, score = taille de la communauté.
- Mise à jour : seuls les Passages ajoutés ou de texte changé sont extraits ; `remove_passages` retire ceux des Documents supprimés ou remplacés (un Passage au même id et même texte est conservé) ; seuls les embeddings d'entités dont l'empreinte change sont recalculés ; Louvain est relancé (gratuit, déterministe) et le rapport d'une communauté n'est régénéré que si sa signature change (`sha16` du contexte du rapport et de ses Passages sources), sinon il est repris tel quel. « Composition » est lu au sens large (membres, descriptions, relations et Passages sources), pour qu'un rapport repris ne cite jamais un Ancrage retiré.
- Poste : aucun `scope` dans l'Architecture, tous les appels portent le poste du runner (`indexing`, `update`, `query`). Fenêtre : `borner` (7.5) pour le texte de map et les rapports, `borner_passages` pour le reduce ; troncature ou écart avec avertissement. Pas de tracé propre (spans de la passerelle et de l'Embedder seuls).
- Simplifications documentées : un seul niveau de communautés (Louvain plat, pas la hiérarchie Leiden de l'article) ; pas de score d'utilité par réponse de map ; `min_community_size` vaut 1 (toutes les communautés ont un rapport).

## Tâches et critères

- [x] Extraction, communautés et rapports produits à l'indexation, tous les appels au poste `indexing` : `test_indexation_extraction_communautes_rapports_au_poste_indexing`, `test_indexation_deterministe`
- [x] Local : entités proches par embedding de leurs descriptions (`numpy_exact`), contexte relations + Passages sources + rapports, Ancrages existants cités : `test_recherche_locale_entites_proches_par_embedding`, `test_recherche_locale_contexte_et_citations`, `test_graphe_vide_abstention_sans_generate`
- [x] Global : map (`global_map`, un appel par lot) puis reduce (`generate`), spans distincts, Citations vers les Ancrages des rapports : `test_recherche_globale_map_puis_reduce`, `test_global_map_passage_aux_ancrages_des_rapports`, `test_global_lots_bornes_et_map_vide`
- [x] `search` dans `query_params`, index commun : `test_search_hors_de_l_index_key`, `test_global_et_local_partagent_le_meme_index`
- [x] Mise à jour : extraction des seuls Passages changés, `remove_passages`, rapports des seules communautés modifiées, poste `update` : `test_update_sans_changement_aucun_appel`, `test_update_suppression_retire_les_passages_et_regenere_les_rapports_changes`, `test_update_ajout_n_extrait_que_les_nouveaux_passages`, `test_update_document_modifie_ne_reextrait_pas_les_passages_identiques`, `test_update_reembarque_les_seules_entites_changees`
- [x] Fenêtre du Generator : `test_fenetre_du_generateur_ecarte_les_blocs_avec_avertissement`
- [x] Enregistrement, capacités (`incremental_update`, `ranked`), `embedder_dim()` = 64 : `test_enregistrement_et_capacites`
- [x] Rapport sans changement : la ventilation par Type de question et par Poste (`indexing`, `update`) existe déjà (4.12, 4.11 en cours) et lit les postes que cette Architecture laisse au runner : `test_indexation_extraction_communautes_rapports_au_poste_indexing`, `test_update_suppression_retire_les_passages_et_regenere_les_rapports_changes`

## Auto Run Result

Voir le rapport de l'agent : tests ciblés, suite complète, pyright et contrôle rapide.

## Reports

- Ni `tests/conformance/` ni `experiments/mini-test.yaml` n'existent encore (4.14 en attente) : la Configuration `graphrag` (local et global) et la conformité restent à ajouter dès leur arrivée.
- Le majorant de 400 tokens de la réserve de schéma reste à vérifier contre `count_tokens` Anthropic (4.15, repris de 7.5).
- Le Type de la Question n'étant pas visible de l'Architecture, la Configuration déclarera deux entrées (`search: local`, `search: global`) ; un routage par Type reste hors périmètre.
- `min_community_size: 1` coûte un appel `community_report` par entité isolée ; à relever à 2 si le coût d'indexation (H13) l'exige.
