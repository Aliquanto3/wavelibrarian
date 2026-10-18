---
story: "7.1"
title: RAPTOR
status: review
---

# Story 7.1 : RAPTOR

## Code Map

- `src/wavelibrarian/architectures/raptor.py` : `Raptor(NaiveRag)` enregistrée `("architecture", "raptor")`, `incremental_update: false`, `retrieval_method: ranked`. Params ajoutés : `group_min = 5`, `group_max = 10`, `max_depth = 3`, `summary_model`, `summary_max_tokens`. `query_params` hérité (`k`). `load` et `answer` sont ceux de `naive_rag` : l'arbre aplati est dans `passages.jsonl` et dans le store `numpy_exact`.
- `tests/unit/architectures/test_story_7_1.py` : tests de la story.
- Aucun changement de `roles.py`, `fake.py`, `scoring/`, runner, ni du suivi.

## Design Notes

- Regroupement déterministe sans scikit-learn ni umap : nœuds ordonnés par chaîne de plus proches voisins (cosinus, départ au plus petit id, égalités par id), puis coupés en `ceil(n / group_max)` groupes de tailles égales à un près. Simplification documentée en docstring (ce n'est pas un GMM/UMAP du papier).
- Règle du dernier groupe : tous les groupes comptent entre `group_min` et `group_max`, sauf un niveau de moins de `group_min` nœuds, qui forme un unique groupe plus petit. `Params` refuse `group_max < 2 * group_min - 1` (garantit la borne basse).
- Niveaux construits tant que `niveau <= max_depth` et qu'il reste plus d'un nœud (à partir du niveau 2).
- Nœud : `passage_id = sha16("node","raptor",level,*sorted(child_ids))`, `anchor_ids` = union triée des Ancrages des enfants (donc des feuilles), `doc_id` nul si plusieurs Documents.
- Résumés : rôle `summarize`, step `raptor.summarize.level<n>`, Poste courant (`indexing` sous le runner). Le Faux LLM renvoie le texte reçu.
- Citation d'un nœud : le `labels` du `labeled` porte déjà ses `anchor_ids` ; `LLMGenerator` les convertit, rien de propre à RAPTOR.
- `update` : reconstruction complète sur `corpus_after` (Poste `update` fixé par le runner).
- Retriever autre que `dense` refusé à la construction (leçon epic 6).
- Report : `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` n'existent pas dans ce commit de base (story 4.14 en attente) ; la Configuration `raptor` et le passage de conformité restent à ajouter avec 4.14.

## Tâches et critères

- [x] Indexation : feuilles et niveaux de résumés, `level` >= 1, `child_ids`, `doc_id` nul multi-Documents, `anchor_ids` unis, `passage_id` : `test_arbre_noeuds_groupes_profondeur_et_identifiants`
- [x] Tailles de groupe, dernier groupe toléré, profondeur : `test_arbre_noeuds_groupes_profondeur_et_identifiants`, `test_groupes_toleres_sous_group_min_et_profondeur_bornee`
- [x] Déterminisme de deux indexations : `test_indexation_deterministe`
- [x] Appels `summarize` : step `raptor.summarize.level<n>`, Poste `indexing` : `test_appels_summarize_step_et_poste`
- [x] Recherche dense sur l'arbre aplati, `level` exposé, Citations vers Ancrages existants des feuilles : `test_recherche_a_plat_niveaux_et_citation_vers_les_feuilles`
- [x] Pertinence par recouvrement d'Ancrages, sans traitement dans `scoring/` : même test (union des `anchor_ids`)
- [x] Mise à jour : arbre reconstruit au Poste `update`, aucun Ancrage du Document supprimé : `test_update_reconstruit_et_retire_le_document_supprime`
- [x] Retriever non supporté refusé avant tout appel : `test_retriever_non_dense_refuse_avant_tout_appel`

## Auto Run Result

Voir le rapport de l'agent : tests ciblés, suite complète, pyright et contrôle rapide verts.
