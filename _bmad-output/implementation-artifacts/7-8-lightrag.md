---
story: "7.8"
title: "LightRAG"
status: review
---

# Story 7.8 : LightRAG

## Code Map

- `src/wavelibrarian/architectures/lightrag.py` : `LightRag`, enregistrée `("architecture", "lightrag")`. Réutilise l'extracteur `EntityExtractor` et le GraphStore `networkx` (7.5), `numpy_exact`, `labeled`, `build_arch_answer`, `borner_passages`.
- `src/wavelibrarian/components/graph/cache.py` (nouveau) : cache d'extraction par texte (`cle_extraction`, `brut`, `depuis_brut`, `extraire_avec_cache`), factorisé depuis `graphrag.py` (7.6, comportement inchangé) et partagé avec `lightrag`.
- Dossier d'index : `passages.jsonl` (feuilles seules), `graph/graph.json`, `vectors_entities/`, `vectors_relations/`, `entities.json` et `relations.json` (empreinte du texte embarqué), `extractions.json`.
- `tests/unit/architectures/test_story_7_8.py` (16 tests). Aucun changement de `roles.py`, `fake.py`, du runner ni du Rapport.

## Design Notes

- Indexation (poste `indexing`) : un appel `extract_entities` par Passage (step `graph.extract.<id>`), fusion dans le GraphStore, deux index denses séparés : entités (« nom : description ») et relations (« nom - nom : description », id `sha16("relation", a, b)` avec a < b). Ni communautés ni rapport ; seuls des spans `extract_entities`.
- Requête : niveau bas = `k_entities` entités les plus proches de l'embedding de la Question, niveau haut = `k_relations` relations les plus proches. Passages sources des deux résultats dédoublonnés, `k` meilleurs (score = somme des proximités, ex æquo par id), rangs contigus après `borner_passages`. Aucun résultat : abstention sans `generate`. `k`, `k_entities`, `k_relations` dans `query_params`.
- Simplification FR-27 : le mot-clé de la Question est son embedding direct (pas de mots-clés bas/haut produits par un LLM), documenté dans la docstring.
- Mise à jour (poste `update`) : `remove_passages` pour les Documents supprimés ou remplacés (le journal du GraphStore est rejoué), sous-graphe des Passages ajoutés ou modifiés uni au graphe, cache d'extraction par texte (un Document modifié change de `doc_id` mais ses Passages inchangés ne sont pas ré-extraits). Seuls les embeddings des entités et relations dont l'empreinte change sont recalculés. L'index obtenu est identique octet pour octet à une indexation complète (hors dossiers de vecteurs, comparés par contenu).
- GraphStore inchangé : le poids d'arête cumulé reporté de 7.7 n'est pas nécessaire (le classement des relations est sémantique, pas par poids).

## Tâches et critères

- [x] Entités et relations extraites par Passage, deux index denses séparés, aucun rapport : `test_indexation_deux_index_separes_sans_rapport`
- [x] Recherche bas niveau (entités) et haut niveau (relations), Passages dédoublonnés, Citations sur des Ancrages existants : `test_requete_deux_niveaux_passages_dedoublonnes`, `test_niveau_haut_apporte_des_passages_absents_du_niveau_bas`, `test_k_borne_les_passages`
- [x] Mise à jour incrémentale par union, aucun appel sur un Passage inchangé : `test_update_ajout_unit_le_sous_graphe_sans_toucher_aux_passages_inchanges`, `test_update_sans_changement_aucun_appel`, `test_update_suppression_retire_les_passages_sans_appel`, `test_update_document_modifie_nouveau_doc_id_reprend_les_extractions`, `test_update_ne_reembarque_que_les_textes_changes`
- [x] Fenêtre, graphe vide, déterminisme, `index_key` : `test_fenetre_du_generateur_ecarte_les_blocs_avec_avertissement`, `test_graphe_vide_abstention_sans_generate`, `test_indexation_deterministe`, `test_k_hors_de_l_index_key`
- [ ] Dernier critère (SM-3 : 15 Architectures dans `mini-test.yaml`) : reporté, voir Reports.

## Auto Run Result

Voir le rapport de l'agent : tests ciblés, suite complète, ruff, pyright, lint-imports et contrôle rapide.

## Reports

- `experiments/mini-test.yaml`, `tests/conformance/` et `tests/e2e/test_sm3.py` relèvent de la 4.14 : la Configuration `lightrag` (et celles de l'epic 7) et la clôture « 15 Architectures » restent à ajouter dès leur arrivée.
- Mots-clés LLM de bas et haut niveau non repris (simplification FR-27) ; à comparer avec l'embedding direct au banc si la qualité des questions multi-hop déçoit.
- Les relations sont indexées une fois par paire d'entités (description fusionnée par le GraphStore : la plus longue) ; une paire à plusieurs relations ne garde qu'un texte.
- Pas de bloc « Relations » dans le contexte (contrairement à `graphrag` local) : seuls les Passages sources sont passés au Generator.
