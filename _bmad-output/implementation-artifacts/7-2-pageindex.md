---
story: "7.2"
title: PageIndex
status: done
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
- Liste de sélection qui dépasse la fenêtre du modèle : découpée en lots consécutifs qui y tiennent, un appel et un span `pageindex.select.<n>` par lot, borne vérifiée avant chacun ; un `done` vrai arrête la navigation après lecture, sans présenter les lots suivants. Un nœud seul qui n'y tient pas : `ConfigError` avant l'appel.
- Fenêtre du générateur : les sections lues qui n'y tiennent pas (question, sortie réservée et marge de 256 tokens comprises) sont écartées depuis la dernière lue, avec un avertissement ; une section seule trop longue est tronquée, avec un avertissement ; une fenêtre sans place lève `ConfigError`. Fenêtre du résumé plus petite que la réserve : `ConfigError`.
- Sémantique de navigation : un nœud choisi est lu même si `done` est faux (ses enfants sont alors proposés) ; pas de retour arrière vers un niveau déjà parcouru.
- `update` : arbres des Documents inchangés conservés, seuls les Documents ajoutés ou modifiés sont résumés (Poste `update` fixé par le runner), ordre de `corpus_after`. Un Document inchangé absent de l'ancien index est reconstruit (avertissement).
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
- [x] Mise à jour incrémentale : `test_update_incremental_ne_resume_que_les_documents_changes`, `test_update_scenario_reel_document_modifie`, `test_update_reconstruit_un_document_absent_de_l_ancien_index`
- [x] Pagination de la sélection et borne du contexte de génération : `test_selection_paginee_pour_un_pdf_a_beaucoup_de_pages`, `test_contexte_borne_par_la_fenetre_du_generateur`
- [x] Enregistrement et capacités : `test_enregistrement_et_capacites`

## Auto Run Result

Voir le rapport de l'agent : tests ciblés, suite complète, pyright et contrôle rapide.

## Revue

Revue Opus en une passe, après rebase sur `main` (41e5e26, rien à rebaser). Livrée sous réserve de la conformité 4.14.

- medium, second avis 1 : corrigé. Les sections lues partaient vers `generate` sans contrôle de fenêtre (troncature silencieuse côté Ollama). Avant l'appel, les sections qui ne tiennent pas sont écartées depuis la dernière lue, une section seule trop longue est tronquée, chaque fois avec un avertissement ; `retrieved` ne montre que ce qui est envoyé. Fenêtre sans place : `ConfigError`. Test `test_contexte_borne_par_la_fenetre_du_generateur` (taille de la requête réellement envoyée mesurée dans le Faux).
- medium, second avis 2 : corrigé. Une liste de racines trop longue (PDF de beaucoup de pages, ou beaucoup de Documents) levait `ConfigError` à chaque Question. Elle est découpée en lots qui tiennent dans la fenêtre, un span par lot, borne vérifiée avant chacun ; l'arbre reste celui des pages (l'AC l'exige). Test `test_selection_paginee_pour_un_pdf_a_beaucoup_de_pages` (150 pages, toutes présentées une fois et dans l'ordre, chaque requête dans la fenêtre).
- low, second avis 3 : corrigé. Fenêtre du résumé inférieure à la réserve : `ConfigError` sur `summary_max_tokens`.
- medium, second avis 4 : corrigé. Chemin `modified` testé sur le vrai Scénario du Mini-corpus (`doc_id` changé) : seuls les Documents entrants sont résumés au Poste `update`, nœuds des inchangés repris à l'identique. Test `test_update_scenario_reel_document_modifie`.
- low, second avis 5 et 6 : corrigé. Le test de troncature vérifie la limite calculée (fenêtre moins system et sortie), le préfixe et l'avertissement, et l'absence d'avertissement sans troncature.
- low, second avis 7 : corrigé. Sémantique de navigation consignée (docstring et Design Notes).
- low, second avis 8 : corrigé. Un Document inchangé absent de l'ancien index est reconstruit avec un avertissement. Test `test_update_reconstruit_un_document_absent_de_l_ancien_index`.
- low, second avis 9 : reporté à 4.14. `incremental_update: true` n'est couvert qu'en appel direct ; le passage par le runner (`IndexCache.build(post="update")`) se vérifiera avec la Configuration `pageindex` de `mini-test.yaml` et le SM-3.
- Report, service réel : sur Ollama (`minicpm5`, fenêtre 32 768), vérifier qu'une Question sur un long PDF ne journalise aucune fenêtre pleine (`prompt_eval_count + eval_count >= num_ctx`) ; la marge de 256 tokens du system du générateur repose sur le tokenizer du Catalogue.
