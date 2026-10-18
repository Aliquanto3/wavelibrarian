---
story: "7.6"
title: "GraphRAG, recherche locale et globale"
status: review
---

# Story 7.6 : GraphRAG, recherche locale et globale

## Code Map

- `src/wavelibrarian/architectures/graphrag.py` : `GraphRag`, enregistrée `("architecture", "graphrag")`. Assemble `EntityExtractor`, `NetworkxGraphStore`, `detect_communities` / `louvain_seed(ctx.seed)` et `CommunityReporter` (story 7.5), un store `numpy_exact` pour les entités, le Generator `llm`.
- Dossier d'index : `passages.jsonl` (feuilles et rapports de `level` 1), `vectors/` (entités), `graph/graph.json`, `communities.json` (id, membres, signature, `report_id`), `entities.json` (empreinte du texte embarqué de chaque entité), `extractions.json` (cache d'extraction, clé `sha16` du texte du Passage).
- `src/wavelibrarian/components/graph_stores/networkx_store.py` (revue) : journal des apports, rejoué par `remove_passages`, sauvegardé trié dans `graph.json`.
- `tests/unit/architectures/test_story_7_6.py` (23 tests). Aucun changement de `roles.py`, `fake.py`, du runner ni du Rapport.

## Design Notes

- Les Architectures ne voient pas le Type de la Question (AD-6) : le mode est `search: local|global`, dans `query_params` avec `k`, `k_entities`, `k_relations`, `k_reports`, `map_batch`, `max_map_batches`, `map_model`, `map_max_tokens`. Les deux recherches partagent l'index (`index_key` identique). C'est la Configuration qui associe `search: global` aux Questions `global`.
- Local : entités les plus proches (cosinus sur « nom : description », `embed_queries`) ; contexte dans l'ordre Passages sources (somme des proximités des entités qui les citent), un bloc « Relations » (relations incidentes, poids décroissant ; Passage synthétique de `level` 1 aux Ancrages des Passages d'où elles viennent), rapports des communautés. Graphe sans entité proche : abstention sans `generate`. `retrieved` trié par score décroissant.
- Global : rapports du plus gros groupe au plus petit, lots de `map_batch`, un `global_map` par lot (step `graphrag.map.<n>`, `max_map_batches` vérifié avant chaque appel), puis reduce par le Generator (`generate`). Chaque sortie de map est un Passage de `level` 1 aux Ancrages unis de son lot ; une Citation remonte donc aux Ancrages des rapports. Sortie de map vide : lot ignoré ; aucune sortie : abstention sans `generate`. `retrieved` = les rapports lus, score = taille de la communauté.
- Mise à jour : `remove_passages` retire les Passages des Documents supprimés ou remplacés et recalcule noms, types, descriptions et poids sans eux (journal rejoué) ; un Passage nouveau dont le texte est au cache d'extraction reprend son extraction sans appel, même sous un nouvel id (un Document modifié change de `doc_id`, donc d'ids de Passages) ; seuls les autres sont extraits. Seuls les embeddings d'entités dont l'empreinte change sont recalculés ; Louvain est relancé (gratuit, déterministe) et le rapport d'une communauté n'est régénéré que si son contexte change (signature `sha16` du contexte envoyé au rôle `community_report`) ; sinon son texte est repris, avec les Ancrages et `child_ids` recalculés depuis les Passages sources actuels, pour qu'un rapport repris ne cite jamais un Ancrage retiré. L'index mis à jour est identique, octet pour octet, à une indexation complète du corpus d'après (hors `vectors/`).
- Map : un lot que la fenêtre tronque ne cite que les rapports dont l'étiquette et du texte ont été lus ; aucun lu, pas d'appel. Le prompt demande le marqueur `AUCUN_POINT_UTILE` quand aucun rapport n'est utile ; ce marqueur ou une sortie vide écarte le lot.
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
- Le respect du marqueur `AUCUN_POINT_UTILE` par un vrai modèle (Ollama ou API) reste à vérifier dans un test `real_*` de la Configuration `graphrag` global (4.14) : compter les sorties de map qui paraphrasent un refus sans le marqueur.
- 7.7 et 7.8 : le GraphStore `networkx` sauvegarde désormais un `journal` dans `graph.json` et `remove_passages` rejoue ce journal (recalcul complet, coût linéaire en mentions) ; LazyGraphRAG et LightRAG en héritent. Un `graph.json` sans journal est relu avec un apport par élément (descriptions alors figées, comme avant la revue). Le cache `extractions.json` est propre à `graphrag` : à reprendre si 7.8 veut la même économie sur les Documents modifiés.
- `max_map_batches` tronque les lots avec un avertissement mais sans compteur au Rapport ; un rapport non lu n'est pas signalé autrement (à ajouter si H2 le demande).

## Revue

- high, revue : un Document modifié change de `doc_id` (`scenario.py`), donc d'ids de Passages ; `identiques` (comparaison par id) ne trouvait jamais rien et tout le Document était réextrait, le test le masquait en gardant le `doc_id`. Corrigé : cache d'extraction par texte, test `test_update_document_modifie_nouveau_doc_id_reprend_les_extractions`.
- medium, second avis 1 : Passage conservé à texte égal avec ses anciens Ancrages. Corrigé : les Passages des Documents nouveaux ou modifiés sont toujours ceux du nouveau découpage (seule l'extraction est reprise) ; `test_update_fusion_de_blocs_ancrages_a_jour_sans_extraction`.
- medium, second avis 2 : rapport repris avec d'anciens Ancrages. Corrigé autrement : signature = contexte envoyé au rôle (seule entrée du rapport), et le rapport repris reçoit les Ancrages et `child_ids` actuels ; pas d'appel `community_report` inutile (même test).
- medium, second avis 3 : `remove_passages` gardait descriptions, noms et types des Passages retirés. Corrigé dans le GraphStore (journal rejoué) ; tests 7.5 inchangés et verts, `test_store_remove_passages_recalcule_descriptions_et_noms`, `test_update_suppression_egale_l_index_complet`.
- medium, second avis 4 : sortie de map citant des rapports tronqués hors fenêtre, appel sur un texte vide. Corrigé : seuls les rapports lus sont cités, aucun lu donne aucun appel ; `test_global_map_ne_cite_que_les_rapports_lus`.
- medium, second avis 5 : refus en texte libre cité comme Passage. Corrigé : marqueur `AUCUN_POINT_UTILE` dans le prompt, filtré ; `test_global_map_refus_explicite_filtre`. Respect par un vrai modèle reporté (4.14).
- low, second avis 6 : ordre de `passages.jsonl` après `update`. Corrigé (tri stable par rang du Document dans le corpus d'après), couvert par les tests d'égalité à l'index complet.
- low, second avis 7 : `min_community_size=1` et troncature `max_map_batches` sans compteur. Consigné (Reports).
- low, second avis 8 : tests manquants pour 1 à 3. Corrigé : six tests ajoutés, qui échouent tous sur le code d'origine ; l'oracle est une indexation complète indépendante, pas un recalcul de la même formule.
