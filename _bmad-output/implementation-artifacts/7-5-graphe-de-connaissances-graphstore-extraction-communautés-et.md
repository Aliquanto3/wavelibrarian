---
story: "7.5"
title: "Graphe de connaissances : GraphStore, extraction, communautés et rapports"
status: review
---

# Story 7.5 : Graphe de connaissances : GraphStore, extraction, communautés et rapports

## Code Map

- `src/wavelibrarian/components/graph_stores/networkx_store.py` : `NetworkxGraphStore` enregistré `("graph_store", "networkx")` ; `graph.json` (nœuds et arêtes triés) pour `save`/`load`.
- `src/wavelibrarian/components/graph/extraction.py` : `EntityExtractor` (rôle `extract_entities`, step `graph.extract.<passage_id>`), `Extraction`, `ajouter(store, extraction)`.
- `src/wavelibrarian/components/graph/communities.py` : `detect_communities(graph, seed, min_size=1) -> list[Community]`, `louvain_seed(experiment_seed)`.
- `src/wavelibrarian/components/graph/reports.py` : `CommunityReporter` (rôle `community_report`, step `graph.report.<community_id>`), `community_context`.
- `src/wavelibrarian/components/graph/_texte.py` : contrôle de fenêtre (`borner`, `couper`).
- `tests/unit/components/test_story_7_5.py`. Aucun changement de `roles.py` ni de `fake.py` (les rôles et leurs sorties par défaut conviennent). Aucune Architecture enregistrée.

## Design Notes

- Fusion par `slug` : la clé d'un nœud est `slug(entity_id)` (ou `slug(name)`). Fusion indépendante de l'ordre : `name` et `kind` = plus petite valeur, `description` = la plus longue (ex æquo la plus petite), `weight` = le plus grand, `passage_ids` = union triée. Un `entity_id` sans caractère exploitable est refusé (`WlError`).
- Relations : graphe non orienté ; une boucle (même `slug` aux deux bouts) est ignorée ; une extrémité inconnue crée l'entité (type `entity`, description vide) ; les extrémités reçoivent les `passage_ids` de la relation. `remove_passages` retire d'abord les relations, puis les entités sans Passage.
- Extracteur : pas de `kind` au registre (liste fermée, `contracts.md` §2) ; « Composant réutilisable » = classe du paquet `components/graph/`, construite par `EntityExtractor(ctx, model_id, max_tokens)` (7.6 et 7.8). Un appel par Passage, entités dédoublonnées par `slug`, relations à boucle écartées. `NonConformantOutput` après le nouvel essai de la passerelle (AD-4). Poste (`indexing`/`update`) : celui de la portée du runner.
- Communautés : Louvain de networkx (`weight`, graine `louvain_seed(ctx.seed)` = `sha16("louvain", seed)` mod 2^32) sur une copie canonique triée, donc indépendante de l'ordre d'insertion. Ordre : taille décroissante, puis plus petit membre. `community_id = sha16("community", *membres triés)` : une communauté inchangée garde son id (utile à la mise à jour incrémentale de 7.6).
- Rapports : Passage de `level` 1, `passage_id = sha16("node","community_report",community_id)`, `child_ids` = Passages sources des entités (triés), `anchor_ids` = union triée de leurs Ancrages (AD-7), `doc_id` = Document commun ou `None`. Communauté sans Passage source connu ou rapport vide : écartée avec avertissement.
- Fenêtre (leçon 7.1 à 7.4) : avant chaque appel, le texte est tronqué avec avertissement s'il dépasse la fenêtre du modèle (system et sortie réservée comptés) ; `ConfigError` si le system et la sortie n'y tiennent pas. Couches (AD-1) : `components` ne peut pas importer `architectures._fenetre`, d'où `graph/_texte.py`.
- Offre à 7.6 à 7.8 : le GraphStore donne `graph()` (descriptions d'entités à embarquer, relations), 7.7 réutilise `detect_communities` sur un graphe de cooccurrence ; 7.8 réutilise `EntityExtractor` et le GraphStore.

## Tâches et critères

- [x] `remove_passages` retire entités et relations orphelines : `test_remove_passages_retire_les_orphelins`, `test_relation_retiree_sans_passage_mais_entites_gardees`
- [x] `save` puis `load` redonnent le même graphe : `test_save_puis_load_redonnent_le_meme_graphe`, `test_load_d_un_graphe_illisible_leve_une_erreur`
- [x] Fusion par `slug` (casse, accents) : `test_fusion_par_slug_casse_et_accents`, `test_fusion_independante_de_l_ordre`, `test_relation_fusionnee_et_boucle_ignoree`
- [x] Enregistrement `("graph_store", "networkx")` : `test_enregistrement`
- [x] Extraction rattachée aux `passage_id` (trois Passages du Mini-corpus, Faux LLM) : `test_extraction_rattache_aux_passage_id`, `test_extraction_scenarisee_fusionne_par_slug`
- [x] Sortie non conforme réessayée une fois puis `NonConformantOutput` : `test_sortie_non_conforme_reessayee_une_fois_puis_erreur`
- [x] Fenêtre : `test_extraction_tronque_avec_avertissement`, `test_extraction_fenetre_trop_petite_erreur`, `test_contexte_du_rapport_borne_a_la_fenetre`
- [x] Communautés déterministes (Louvain, graine de l'Expérience, ex æquo par id) : `test_communautes_deterministes`, `test_communautes_independantes_de_l_ordre_d_insertion`, `test_graine_derivee_de_l_experience`, `test_ids_de_communaute_selon_la_composition`, `test_graphe_vide_aucune_communaute`
- [x] Rapports = Passages de `level` 1 aux Ancrages unis : `test_rapports_passages_de_niveau_1_aux_ancrages_unis`, `test_rapports_identiques_sur_deux_executions`, `test_rapport_ecarte_sans_passage_source_ou_vide`
- [x] Aucune Architecture enregistrée : aucun fichier dans `architectures/`, aucun changement de `experiments/`.

## Auto Run Result

Voir le rapport de l'agent : tests ciblés, suite complète, pyright et contrôle rapide.

## Reports

- Extracteur non enregistré au registre faute de `kind` adapté (liste fermée) : si 7.6 ou 7.8 préfèrent un `kind`, il faudra modifier `contracts.md` et `KINDS`.
- La Configuration et la conformité de `graphrag`, `lazy_graphrag` et `lightrag` restent à faire dans leurs stories.
