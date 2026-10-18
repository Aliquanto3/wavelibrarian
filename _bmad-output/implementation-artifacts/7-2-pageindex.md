---
story: "7.2"
title: PageIndex
status: review
---

# Story 7.2 : PageIndex

## Code Map

- `src/wavelibrarian/architectures/pageindex.py` : `PageIndex(ArchitectureBase)` enregistrée `("architecture", "pageindex")`, `retrieval_method: provided`, `incremental_update: true`. Params : `max_nodes_read = 8`, `summary_model`, `summary_max_tokens`, `select_model`, `select_max_tokens`, `generator`, `context_builder`. `query_params` : `max_nodes_read`, `select_model`, `select_max_tokens`. Aucun embedder (`embedder_dim()` reste `None`).
- Index : `tree.json` dans le dossier d'index (nœuds : `node_id`, `doc_id`, `anchor_id`, `title`, `text`, `parent`, `children`, `summary`).
- `tests/unit/architectures/test_story_7_2.py` : tests de la story.
- Aucun changement de `roles.py`, `fake.py`, runner, `scoring/`, ni du suivi.

## Design Notes

- Un nœud par Ancrage du Document, dans l'ordre ; parent = nœud du plus long préfixe strict de `heading_path` déjà vu (titres frères identiques : le dernier vu sert de parent). Un PDF (Ancrages de page) donne des nœuds plats « Page n ». Texte avant le premier titre : nœud de premier niveau nommé d'après le fichier. `node_id = sha16("node","pageindex",anchor_id)`.
- Résumé : rôle `summarize`, step `pageindex.summarize`, un appel par nœud au texte non vide, sur le texte propre de la section. Texte tronqué (avertissement) s'il dépasse la fenêtre du modèle de résumé.
- Navigation : liste de départ = nœuds de premier niveau de tous les Documents. Chaque étape `pageindex.select.<n>` envoie `question`, `nodes [{id,title,summary}]`, `max` = lectures restantes. Les identifiants proposés et valides sont lus (texte de la section, ordre de choix) ; `done` faux : les enfants des nœuds choisis forment la liste suivante ; `done` vrai (le Faux LLM) : arrêt après lecture. Choisir un nœud le lit toujours, même s'il a des enfants.
- Bornes : `max_nodes_read` vérifié avant chaque appel de sélection (on n'appelle pas si la borne est atteinte) et avant chaque lecture (la sortie du LLM est tronquée à la borne). Nœud sans texte : non lu, ne consomme rien.
- Inconnu = absent de l'index ou non proposé à cette étape : ignoré, un seul avertissement du journal par étape avec le compte. Aucun nœud lu : abstention sans `generate` (`retrieved` vide).
- Liste de sélection qui dépasse la fenêtre du modèle : `ConfigError` avant l'appel, rien de tronqué en silence.
- `update` : arbres des Documents inchangés conservés, seuls les Documents ajoutés ou modifiés sont résumés (Poste `update` fixé par le runner), ordre de `corpus_after`.
- Report : `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` n'existent pas dans ce commit de base (story 4.14 en attente) ; la Configuration `pageindex` et le passage de conformité restent à ajouter avec 4.14.
- Report, hérité du cache d'index : isoler `WL_HOME` quand un Faux LLM scénarisé indexe (les tests le font).

## Tâches et critères

- [x] Un arbre par Document suivant les titres, nœud = titre, résumé, Ancrage : `test_arbre_par_document_hierarchie_resume_et_ancrage`
- [x] PDF sans titre : un nœud par page : `test_pdf_sans_titre_un_noeud_par_page`
- [x] Résumés par `summarize` au Poste `indexing` ; `load` d'une instance neuve sans aucun appel : `test_summarize_au_poste_indexing_et_load_sans_appel`
- [x] Sélection sans embedding, span `pageindex.select.<n>`, `retrieved` dans l'ordre de lecture, `provided` : `test_navigation_faux_llm_citation_valide_sans_embedding`, `test_navigation_scenarisee_descend_et_lit_dans_l_ordre`
- [x] `max_nodes_read` avant chaque lecture et chaque appel : `test_borne_max_nodes_read_avant_chaque_lecture_et_appel`, `test_borne_limite_aussi_le_max_transmis`
- [x] Faux LLM par défaut : Citation valide sur q-001 : `test_navigation_faux_llm_citation_valide_sans_embedding`
- [x] Identifiant inconnu ignoré et journalisé : `test_identifiant_inconnu_ignore_journalise_et_abstention` ; aucun nœud valide, abstention : `test_aucun_noeud_valide_abstention_sans_generate`
- [x] Fenêtre du modèle : `test_liste_trop_longue_pour_la_fenetre_refusee`, `test_section_tronquee_avant_resume`
- [x] Mise à jour incrémentale : `test_update_incremental_ne_resume_que_les_documents_changes`
- [x] Enregistrement et capacités : `test_enregistrement_et_capacites`

## Auto Run Result

Voir le rapport de l'agent : tests ciblés, suite complète, pyright et contrôle rapide.
