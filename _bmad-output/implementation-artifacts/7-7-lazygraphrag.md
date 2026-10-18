---
story: "7.7"
title: "LazyGraphRAG"
status: review
---

# Story 7.7 : LazyGraphRAG

## Code Map

- `src/wavelibrarian/architectures/lazy_graphrag.py` : `LazyGraphRag`, enregistrée `("architecture", "lazy_graphrag")`, distincte de `graphrag`. Réutilise le GraphStore `networkx` et `detect_communities` / `louvain_seed` (7.5), `extraire_entites` (`corpus/entities.py`), le schéma borné du Decider `llm`.
- Dossier d'index : `passages.jsonl` (feuilles seules), `graph/graph.json` (GraphStore, avec son journal), `communities.json` (id et membres). Ni vecteurs ni rapports.
- `src/wavelibrarian/components/deciders/llm.py` : alias public `schema_scores` de `_schema_pour` (un seul changement, pas de nouveau comportement).
- `tests/unit/architectures/test_story_7_7.py` (17 tests). Aucun changement de `roles.py`, `fake.py`, du runner ni du Rapport.

## Design Notes

- Indexation sans LLM ni embedding : concepts de chaque feuille par `extraire_entites`, nœud `networkx` par concept (id `slug_entite`, type `concept`, rattaché aux Passages qui le citent), arête de cooccurrence entre deux concepts d'un même Passage. Louvain tourne sur une copie du graphe dont le poids d'arête est le nombre de Passages qui réunissent ses deux concepts (le GraphStore garde le plus grand poids, pas la somme). Aucun appel à la passerelle : pas de span `llm` à l'indexation.
- Requête : concepts de la Question par la même heuristique, la Question étant précédée d'un mot neutre (« — ») pour que son premier mot compte ; deux concepts se correspondent si les mots de l'un (séparés par espace, trait d'union, apostrophe) sont inclus dans ceux de l'autre. Communautés classées par nombre de concepts de la Question touchés, puis taille, puis id ; aucune communauté touchée : abstention sans aucun appel. Passages des meilleures communautés, un Passage une fois, les plus liés aux concepts touchés d'abord.
- Notation : rôle `grade_relevance`, step `lazygraphrag.grade.<n>`, lots de `grade_batch` (5) Passages, schéma borné au nombre de Passages du lot. `relevance_budget` (défaut 20, dans `query_params`, donc hors `index_key`) borne le nombre total de Passages notés ; il est vérifié avant chaque appel (lot réduit à ce qui reste). Un lot que la fenêtre du modèle ne laisse pas tenir est réduit ; un Passage seul trop long est tronqué avec avertissement (`borner`).
- Pertinence : note strictement supérieure à `relevance_threshold` (défaut 0.0, donc scores tous nuls : abstention sans `generate`). Les `k` (5) mieux notés vont au Generator ; `retrieved` est trié par note décroissante, rangs contigus après la borne de fenêtre (`borner_passages`).
- Mise à jour (Poste `update`) : `remove_passages` pour les Documents supprimés ou remplacés, concepts des Passages nouveaux ajoutés, Louvain relancé ; aucun appel. L'index obtenu est identique octet pour octet à une indexation complète du corpus d'après.
- Simplifications documentées : concepts par heuristique (rate les noms communs et en début de phrase, garde des bruits comme « Le » ou un titre collé au texte), un seul niveau de communautés, pas de rapport, les Passages au-delà du budget ne sont jamais lus.

## Tâches et critères

- [x] Indexation sans appel LLM (heuristique, graphe de cooccurrence `networkx`, Louvain déterministe), Trace sans span `llm` : `test_indexation_sans_aucun_appel_llm`, `test_cooccurrence_dans_un_meme_passage`, `test_indexation_deterministe`
- [x] Requête : classement des communautés par concepts de la Question, `grade_relevance` borné, puis `generate` avec les Passages pertinents : `test_requete_classe_les_communautes_note_puis_genere`, `test_la_communaute_qui_touche_la_question_passe_en_premier`, `test_premier_mot_de_la_question_compte`, `test_seuil_de_pertinence`
- [x] `relevance_budget` (20 par défaut) vérifié avant chaque appel, dans `query_params` : `test_relevance_budget_borne_les_passages_notes`, `test_budget_par_defaut_20_et_lots_de_5`, `test_relevance_budget_hors_de_l_index_key`
- [x] Scores tous nuls (ou aucun concept connu) : abstention sans `generate` : `test_scores_tous_nuls_abstention_sans_generate`, `test_question_sans_concept_abstention_sans_appel`
- [x] Fenêtre du modèle de notation : `test_fenetre_de_notation_reduit_le_lot`
- [x] Enregistrée, distincte de `graphrag` (visible dans `wl registre --kind architecture`) : `test_enregistrement_et_capacites`
- [x] Mise à jour sans appel, égale à l'index complet : `test_update_ajout_egale_l_index_complet_sans_appel`, `test_update_suppression_egale_l_index_complet`, `test_update_document_modifie_remplace_sans_dupliquer`

## Auto Run Result

Voir le rapport de l'agent : tests ciblés, suite complète, ruff, pyright et contrôle rapide.

## Reports

- Ni `tests/conformance/` ni `experiments/mini-test.yaml` n'existent encore (4.14 en attente) : la Configuration `lazy_graphrag` et la conformité restent à ajouter dès leur arrivée.
- Seuil de pertinence : `relevance_threshold = 0.0` laisse passer toute note positive ; avec un vrai modèle, qui note rarement 0, il faudra le relever (par ex. 0.3 à 0.5) et vérifier que l'abstention reste possible. À calibrer dans les Configurations réelles (4.14, H-tests `real_*`).
- Qualité de l'heuristique de concepts sur le Mini-corpus : le graphe contient du bruit (mots de liaison capitalisés, titres collés au texte). Le rappel sur des questions multi-hop et le coût de notation (jusqu'à 20 Passages par Question) sont à mesurer au banc (H13).
- Le poids de cooccurrence est calculé hors du GraphStore (nombre de Passages par arête) car `upsert_relation` garde le plus grand poids ; si 7.8 veut un poids cumulé, un paramètre du GraphStore serait plus propre.
- `_candidats` rescanne toutes les communautés à chaque Question (coût linéaire en nœuds) ; suffisant au Mini-corpus, à indexer par concept si un corpus plus grand l'exige.
- Pas de reprise du cache d'extraction pour 7.8 : ici l'extraction est gratuite et recalculée.
