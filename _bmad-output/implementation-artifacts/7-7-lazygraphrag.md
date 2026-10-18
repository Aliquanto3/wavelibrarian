---
story: "7.7"
title: "LazyGraphRAG"
status: review
---

# Story 7.7 : LazyGraphRAG

## Code Map

- `src/wavelibrarian/architectures/lazy_graphrag.py` : `LazyGraphRag`, enregistrée `("architecture", "lazy_graphrag")`, distincte de `graphrag`. Réutilise le GraphStore `networkx` et `detect_communities` / `louvain_seed` (7.5), `extraire_entites` (`corpus/entities.py`), le Decider `llm` (Params `decider`) pour la notation.
- Dossier d'index : `passages.jsonl` (feuilles seules), `graph/graph.json` (GraphStore, avec son journal), `communities.json` (id et membres). Ni vecteurs ni rapports.
- `src/wavelibrarian/components/deciders/llm.py` et port `Decider` : `grade(..., *, step=None)` nomme l'étape (défaut inchangé `crag.grade.loopN`, donc 6.3/6.4 et leur cache intacts) ; `SYSTEM` et `max_tokens` publics (revue).
- `tests/unit/architectures/test_story_7_7.py` (21 tests). Aucun changement de `roles.py`, `fake.py`, du runner ni du Rapport.

## Design Notes

- Indexation sans LLM ni embedding : concepts de chaque feuille par `extraire_entites`, nœud `networkx` par concept (id `slug_entite`, type `concept`, rattaché aux Passages qui le citent), arête de cooccurrence entre deux concepts d'un même Passage. Louvain tourne sur une copie du graphe dont le poids d'arête est le nombre de Passages qui réunissent ses deux concepts (le GraphStore garde le plus grand poids, pas la somme). Aucun appel à la passerelle : pas de span `llm` à l'indexation.
- Requête : concepts de la Question par la même heuristique, la Question étant précédée d'un mot neutre (« — ») pour que son premier mot compte ; deux concepts se correspondent si les mots de l'un (séparés par espace, trait d'union, apostrophe) sont inclus dans ceux de l'autre. Communautés classées par nombre de concepts de la Question touchés, puis taille, puis id ; aucune communauté touchée : abstention sans aucun appel. Passages des meilleures communautés, un Passage une fois, les plus liés aux concepts touchés d'abord.
- Notation : rôle `grade_relevance`, step `lazygraphrag.grade.<n>`, lots de `grade_batch` (5) Passages, schéma borné au nombre de Passages du lot. `relevance_budget` (défaut 20, dans `query_params`, donc hors `index_key`) borne le nombre total de Passages notés ; il est vérifié avant chaque appel (lot réduit à ce qui reste). Un lot que la fenêtre du modèle ne laisse pas tenir est réduit ; un Passage seul trop long est tronqué avec avertissement (`borner`).
- Pertinence : note strictement supérieure à `relevance_threshold` (défaut 0.1 depuis la revue : scores nuls ou quasi nuls, abstention sans `generate`). Les `k` (5) mieux notés vont au Generator ; `retrieved` est trié par note décroissante, rangs contigus après la borne de fenêtre (`borner_passages`).
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
- Seuil de pertinence : `relevance_threshold = 0.1` écarte les notes quasi nulles ; avec un vrai modèle, il faudra peut-être le relever (0.3 à 0.5, `corrective_rag` prend 0.5) et vérifier que l'abstention reste possible. À calibrer dans les Configurations réelles (4.14, H-tests `real_*`).
- Qualité de l'heuristique de concepts sur le Mini-corpus : le graphe contient du bruit (mots de liaison capitalisés, titres collés au texte). Le rappel sur des questions multi-hop et le coût de notation (jusqu'à 20 Passages par Question) sont à mesurer au banc (H13).
- Le poids de cooccurrence est calculé hors du GraphStore (nombre de Passages par arête) car `upsert_relation` garde le plus grand poids ; si 7.8 veut un poids cumulé, un paramètre du GraphStore serait plus propre.
- `_candidats` rescanne toutes les communautés à chaque Question (coût linéaire en nœuds) ; suffisant au Mini-corpus, à indexer par concept si un corpus plus grand l'exige.
- Pas de reprise du cache d'extraction pour 7.8 : ici l'extraction est gratuite et recalculée.

## Revue

Revue Opus du 2026-10-18, après rebase sur `main` (4.11), avec la liste du second avis (Haiku).

- medium, second avis 1 : corrigé. `relevance_threshold` passe de 0.0 à 0.1 (comparaison stricte gardée, donc des scores tous nuls s'abstiennent toujours, et un seuil 0 reste possible) ; une note réelle quasi nulle n'ouvrait plus jamais l'abstention. Test `test_seuil_par_defaut_ecarte_les_notes_quasi_nulles`. Calibrage réel reporté (4.14).
- medium, second avis 2 : corrigé. La notation passe par le Decider (`Params.decider`, `ctx.build("decider", ...)`, dans `query_params`), sans copie du prompt ; `grade` reçoit un `step` facultatif, l'étape reste `lazygraphrag.grade.<n>`. `grade_model` et `grade_max_tokens` quittent le Params (portés par le Decider). Le défaut `crag.grade.loopN` est inchangé : 6.3/6.4 et leur cache intacts. Test `test_notation_par_le_decider_avec_son_step`.
- low, second avis 3 : corrigé (alias `schema_scores` supprimé).
- low, second avis 4 : corrigé. Les tests d'indexation et d'`update` font lever le provider à tout appel ; un test de contrôle prouve que la doublure lève bien à la requête.
- low, second avis 5 : corrigé. Le test de remplacement affirme `not rep.abstained` et des Citations non vides.
- low, second avis 6 : corrigé. `_mots` écarte les mots outils et interrogatifs (« que », « le », « pourquoi port ysel » lu « port ysel ») ; test `test_mots_outils_ne_rattachent_rien`.
- low, second avis 7 et 8 : consignés sans correctif, comme demandé par l'orchestrateur (constats mineurs, voir aussi Reports).
- low, revue : reporté. `_OUTILS` est une liste courte FR/EN ; d'autres mots capitalisés de bruit (« Selon », « Mais ») restent des concepts. À mesurer sur le Mini-corpus au banc (H13) avec le rappel multi-hop.
- reporté (4.14) : Configuration `lazy_graphrag` dans `experiments/mini-test.yaml` et conformité dès que `tests/conformance/` existe ; vérification `real_*` du seuil et de la notation par lots avec un vrai modèle.
- reporté (7.8) : si LightRAG veut un poids d'arête cumulé, ajouter un paramètre au GraphStore plutôt que recompter hors de lui comme ici.
