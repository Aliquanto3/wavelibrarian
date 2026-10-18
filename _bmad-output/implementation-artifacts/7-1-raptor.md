---
story: "7.1"
title: RAPTOR
status: done
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
- Résumés : rôle `summarize`, step `raptor.summarize.level<n>`, Poste courant (`indexing` sous le runner). Le Faux LLM renvoie les 30 premiers mots du texte reçu.
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

## Revue

Revue Opus en une passe, après rebase sur `main` (4.7). Livrée sous réserve de la conformité 4.14.

- medium, second avis 1 : corrigé. Aucune borne sur le texte envoyé au résumé. Avec `fixed_tokens`, la construction refuse un groupe plein (`group_max × max(size, summary_max_tokens)` + system + sortie) qui dépasse la fenêtre du Catalogue, avant tout appel ; chaque appel `summarize` est aussi vérifié avant l'envoi (`ConfigError`, rien de tronqué en silence). Test `test_fenetre_du_modele_de_resume`.
- medium, second avis 2 : corrigé. `group_max = 1` passait la validation ; désormais `group_max >= 2`, donc chaque niveau réduit, et la boucle s'arrête dès qu'il reste un seul nœud. Test `test_group_max_un_refuse_et_chaque_niveau_reduit`.
- low, second avis 3 : corrigé. Une feuille unique ne donne plus de résumé à un enfant. Test `test_feuille_unique_sans_resume`.
- low, second avis 4 : corrigé. Les Design Notes disent maintenant que le Faux LLM renvoie les 30 premiers mots.
- low, second avis 5 : rejeté. `resoudre_params` remplit `summary_model` avec le défaut du profil dans l'Expérience résolue, avant la construction : la clé d'index porte le modèle résolu, comme `hyde_model` (6.3). La valeur `None` n'apparaît qu'en construction directe dans les tests.
- low, second avis 6 : corrigé. Le test de borne basse vérifie tous les niveaux, le niveau 1 compris.
- low, second avis 7 : corrigé. Les Ancrages de chaque nœud, quel que soit son niveau, sont comparés à l'union récursive de ceux de ses feuilles, et appartiennent au Corpus.
- low, second avis 8 et 9 : consigné. La reconstruction complète à l'`update` est conforme à l'AC (`incremental_update: false`). Reporté à 4.14 : Configuration `raptor` dans `experiments/mini-test.yaml`, passage de `tests/conformance/test_architectures.py` et de `tests/e2e/test_sm3.py`.
- low, revue : corrigé. La chaîne de plus proches voisins faisait O(n²) appels Python scalaires ; elle est vectorisée (un produit matriciel par pas), avec le même départage par id (argmax sur les lignes triées par id).
- Report, service réel : vérifier sur Ollama (`minicpm5`, fenêtre 32 768) qu'une indexation par défaut ne journalise aucune fenêtre pleine (`prompt_eval_count + eval_count >= num_ctx`).
