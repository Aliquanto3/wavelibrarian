---
story: "7.5"
title: "Graphe de connaissances : GraphStore, extraction, communautés et rapports"
status: done
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

- Fusion par `slug_entite` (revue : `slug` + apostrophes typographiques unifiées et ligatures œ/æ développées ; `slug` reste inchangé pour les Ancrages gelés) : la clé d'un nœud est `slug_entite(entity_id)` (ou du `name`). Fusion indépendante de l'ordre (`components/graph/fusion.py`, appliquée aussi dans un Passage par l'extracteur) : `name` = forme la plus mentionnée (attribut `noms`), ex æquo la plus accentuée puis la plus petite ; `kind` extrait prioritaire sur le générique `entity`, sinon le plus petit ; `description` = la plus longue (ex æquo la plus petite), `weight` = le plus grand, `passage_ids` = union triée. Un `entity_id` sans caractère exploitable est refusé (`WlError`).
- Relations : graphe non orienté ; une boucle (même `slug` aux deux bouts) est ignorée ; une extrémité inconnue crée l'entité (type `entity`, description vide) ; les extrémités reçoivent les `passage_ids` de la relation. `remove_passages` retire d'abord les relations, puis les entités sans Passage.
- Extracteur : pas de `kind` au registre (liste fermée, `contracts.md` §2) ; « Composant réutilisable » = classe du paquet `components/graph/`, construite par `EntityExtractor(ctx, model_id, max_tokens)` (7.6 et 7.8). Un appel par Passage, entités dédoublonnées par `slug`, relations à boucle écartées. `NonConformantOutput` après le nouvel essai de la passerelle (AD-4). Poste (`indexing`/`update`) : celui de la portée du runner.
- Communautés : Louvain de networkx (`weight`, graine `louvain_seed(ctx.seed)` = `sha16("louvain", seed)` mod 2^32) sur une copie canonique triée, donc indépendante de l'ordre d'insertion. Ordre : taille décroissante, puis `community_id`. `community_id = sha16("community", *membres triés)` : une communauté inchangée garde son id (utile à la mise à jour incrémentale de 7.6).
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

## Revue

Revue Opus du 2026-10-18, rebasée sur `main` (8b30f60) sans conflit.

- medium, second avis n° 1 : corrigé. Une extrémité créée par une relation recevait `kind="entity"`, que `min()` gardait devant un type extrait (« entity » < « personne ») ; le nom canonique `min()` préférait « eric » à « Éric ». Règles communes dans `components/graph/fusion.py` : type extrait prioritaire, nom = forme la plus mentionnée puis la plus accentuée. Tests dans les deux ordres.
- medium, second avis n° 2 : corrigé. Dans un Passage, la première mention gagnait ; l'extracteur applique maintenant les mêmes règles que le store.
- medium, second avis n° 3 : corrigé par une fonction dédiée `core.ids.slug_entite` (’ → ', œ/æ → oe/ae). `slug` n'est pas modifié : il fixe les Ancrages des titres (`_sections.py`, `types.py`), gelés dans les Jeux.
- medium, second avis n° 4 : corrigé. L'extraction réserve le schéma JSON de sortie et un majorant de 400 tokens (`SURCOUT_SCHEMA`, `schema_prompt_overhead` d'Anthropic), les providers n'étant pas visibles des Composants.
- medium, second avis n° 5 : à arbitrer par Anaël. L'AC dit « enregistré comme Composant réutilisable », mais `contracts.md` §2 ferme la liste des `kind` et l'epic n'ajoute que `graph_store`. Décision de l'orchestrateur : classes non enregistrées (`EntityExtractor`, `CommunityReporter`) jusqu'à arbitrage.
- low, second avis n° 6 : corrigé. `couper` déplacé dans `core/fenetre.py`, réexporté par `architectures/_fenetre.py` (contrats import-linter tenus).
- low, second avis n° 7 : corrigé. `sources()` journalise les `passage_id` inconnus écartés.
- low, second avis n° 8 : corrigé. Communautés triées par taille décroissante puis `community_id`.
- low, second avis n° 9 : corrigé. Test en sous-processus avec trois `PYTHONHASHSEED` : mêmes communautés.
- low, second avis n° 10 : consigné. La troncature avant l'appel (extraction, rapport) est volontaire et journalisée ; elle ne se produit qu'au-delà de la fenêtre du modèle.
- low, revue : `remove_passages` ne recompte pas `noms` (nombre de mentions) ; le nom canonique peut garder une forme venue d'un Passage retiré. Accepté, consigné en docstring.

Reports pour 7.6 : brancher `louvain_seed(ctx.seed)` et le GraphStore dans l'Architecture `graphrag` ; si l'extracteur doit être enregistré (n° 5), ajouter le `kind` à `contracts.md` et `KINDS` ; vérifier la réserve de schéma contre un vrai appel Anthropic (`count_tokens`) quand l'API est disponible.
