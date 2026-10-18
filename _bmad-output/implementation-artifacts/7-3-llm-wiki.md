---
story: "7.3"
title: LLM Wiki
status: done
---

# Story 7.3 : LLM Wiki

## Code Map

- `src/wavelibrarian/architectures/llm_wiki.py` : `LlmWiki(ArchitectureBase)` enregistrée `("architecture", "llm_wiki")`, `retrieval_method: provided`, `incremental_update: true`. Params : `fidelity_sample = 5`, `k = 5` (seul `query_params`), `compile_model`, `compile_max_tokens`, `fidelity_model`, `fidelity_max_tokens`, `lexical_index` (`bm25`), `retriever` (`lexical`), `generator`, `context_builder`. Aucun embedder.
- Index : `passages.jsonl` (pages, `level` 1), `lexical/` (BM25), `wiki.json` (pages avec `source_doc_id`, `compiled_docs`, `discarded_pages`), `wiki_fidelity.json`.
- `src/wavelibrarian/architectures/_fenetre.py` : `borner_passages` et `couper`, extraits de `pageindex.py` (même comportement, nom de l'Architecture en paramètre) et réutilisés par `llm_wiki`.
- `src/wavelibrarian/runner/wiki_fidelity.py` (copie générique) appelée en fin de `IndexCache.build` (`runner/index_cache.py`, 3 lignes) ; `src/wavelibrarian/report/wiki.py` : `taux_fidelite` et `section_fidelite`.
- `tests/unit/architectures/test_story_7_3.py`. Aucun changement de `roles.py` ni de `fake.py` (rôles `wiki_compile` et `wiki_fidelity` déjà présents).

## Design Notes

- Compilation : un appel `wiki_compile` (step `wiki.compile`) par Document ; un Document dont les Blocks ne tiennent pas dans la fenêtre du modèle est découpé en lots de Blocks consécutifs (un appel par lot) ; un Block seul trop long est tronqué avec un avertissement. `passage_id = sha16("page","llm_wiki",doc_id source,ordinal)`. `Passage.doc_id` = le Document des Ancrages s'il est unique, sinon `None`. Texte de la page : `titre\n\ncorps`.
- Ancrages déclarés filtrés sur ceux du Corpus ; page sans Ancrage valide écartée, avertissement du journal et `discarded_pages` dans `wiki.json`.
- Fidélité : tirage `ctx.rng("llm_wiki","fidelity")` sur les pages triées par id (graine de l'Expérience), `min(fidelity_sample, nombre de pages)`, un appel `wiki_fidelity` (step `wiki.fidelity`) par page, sur le texte de ses Ancrages. Les sources qui ne tiennent pas dans la fenêtre sont écartées depuis la dernière, une page ou une source seule trop longue est tronquée, avec un avertissement. `wiki_fidelity.json` : `fidelity_sample`, `pages` (`passage_id`, `title`, `anchor_ids`, `claims`, `supported`), `claims` et `supported` totaux. Écrit avant tout autre fichier de l'index (un échec n'en laisse pas).
- Juge de fidélité (revue, AD-14) : `fidelity_model` n'a pas de `ModelRefMeta` ; par défaut, `closed_book_judge(compile_model, profil.judge_pool)`, premier Juge du réservoir d'une autre Famille que l'auteur des pages ; un `fidelity_model` explicite de la même Famille est refusé à la construction (`ConfigError`).
- Clé d'index (revue) : `index_key()` ajoute le Juge de fidélité effectif et, si `fidelity_sample > 0`, la graine : un hit de cache ne sert pas l'échantillon d'une autre graine (une graine nouvelle recompile le wiki).
- Ancrages (revue) : une page ne garde que les Ancrages déclarés de son Document source (contrat `wiki_compile` : une page par Document).
- Requête : `k` pages par BM25, bornées par la fenêtre du générateur (`borner_passages`), `retrieval_method: provided` ; Citations remontées aux Ancrages des pages par la table `labels`. Aucune page trouvée : abstention sans `generate`.
- `update` : seuls les Documents ajoutés ou modifiés sont recompilés (Poste `update` fixé par le runner) ; pages des Documents supprimés ou modifiés retirées ; pages conservées avec Ancrages refiltrés sur le Corpus après mise à jour, écartées si plus aucun ne subsiste (aucune page ne référence un Document supprimé) ; un Document jamais compilé est compilé (avertissement) ; fidélité remesurée sur les pages résultantes.
- Runner et Rapport (seule story de l'epic à les toucher) : `runs/<run_id>/wiki_fidelity.json` est un objet `{clé: contenu du fichier d'index}`, clé = id de Configuration, suffixée `@<palier>` et `@after_update` ; il est complété à chaque `IndexCache.build` si le dossier d'index contient le fichier (chemins « cache présent » et « construit » identiques), sinon rien n'est écrit. Le choix d'un objet par Configuration plutôt qu'une copie brute vient de ce qu'une Exécution peut contenir plusieurs Configurations `llm_wiki`. `execute.py` n'est pas modifié (story 4.9 en parallèle).
- Rapport : `report/` n'a pas de générateur dans ce commit (story 4.12 en attente) ; `section_fidelite(run_dir)` rend la section Markdown `supported ÷ claims` par Configuration (chaîne vide si fichier absent, `n/a` si aucune affirmation), à brancher dans le Rapport avec 4.12.
- Report : `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` n'existent pas dans ce commit de base (story 4.14 en attente) ; la Configuration `llm_wiki` et le passage de conformité restent à ajouter avec 4.14.
- Report, hérité du cache d'index : les tests isolent `WL_HOME` quand un Faux LLM scénarisé indexe.

## Tâches et critères

- [x] `wiki_compile` au poste `indexing`, pages = Passages de `level` 1 aux Ancrages déclarés filtrés : `test_pages_de_level_1_aux_ancrages_filtres_au_poste_indexing`
- [x] Page sans Ancrage existant écartée et comptée au journal : `test_page_sans_ancrage_valide_ecartee_et_comptee`
- [x] Réponse par index lexical, pages fournies au Generator, Citations aux Ancrages des pages, `provided` : `test_reponse_par_index_lexical_et_citation_aux_ancrages_des_pages` ; abstention sans page : `test_question_sans_page_trouvee_abstention_sans_generate`
- [x] `fidelity_sample = 5`, tirage déterministe sur la graine, `wiki_fidelity.json` : `test_fidelite_echantillon_deterministe_et_fichier_ecrit`, `test_fidelite_depend_de_la_graine`, `test_fidelite_mesure_le_faux_llm_sur_le_texte_des_ancrages`
- [x] Mise à jour : pages des seuls Documents changés, poste `update`, fidélité remesurée, aucune page vers le Document supprimé : `test_update_ne_recompile_que_les_documents_changes_et_remesure`, `test_update_scenario_reel_document_modifie`, `test_update_retire_les_pages_qui_citent_un_document_supprime`
- [x] Copie générique par le runner (fichier présent ou absent) ; taux au Rapport livré côté données (`section_fidelite`), affichage reporté à 4.11/4.12 : `test_copie_generique_au_runner_et_taux_dans_le_rapport`, `test_architecture_sans_fidelite_ne_copie_rien_et_rapport_vide`, `test_taux_sans_affirmation_est_none`
- [x] Fenêtre du modèle sans troncature silencieuse : `test_compilation_decoupee_en_lots_dans_la_fenetre`, `test_fidelite_tient_dans_la_fenetre_avec_avertissement` ; non-régression de l'extraction depuis `pageindex` : `tests/unit/architectures/test_story_7_2.py`
- [x] Enregistrement et capacités : `test_enregistrement_et_capacites`

## Auto Run Result

Voir le rapport de l'agent : tests ciblés, suite complète, pyright et contrôle rapide.

## Revue

- high, second avis n° 1 (Juge de fidélité = auteur des pages, Famille non vérifiée) : corrigé, défaut `closed_book_judge` sur le réservoir du profil, refus d'une même Famille ; `test_juge_de_fidelite_par_defaut_d_une_autre_famille`, `test_juge_de_fidelite_de_la_meme_famille_refuse`.
- medium, orchestrateur n° 2 (Rapport absent) : reporté, `section_fidelite` livrée, son appel est à brancher par la story Rapport (4.11/4.12).
- medium, second avis n° 3 (graine hors de l'`index_key`) : corrigé, graine et Juge effectif dans la clé (tirage à l'indexation, fidèle à l'AC « quand l'indexation se termine ») ; `test_graine_dans_la_cle_un_hit_de_cache_ne_sert_pas_l_echantillon_d_une_autre_graine`.
- medium, second avis n° 4 (Ancrages filtrés sur tout le Corpus) : corrigé, filtre sur le Document source ; `test_page_ne_garde_que_les_ancrages_de_son_document_source`.
- low, second avis n° 5 (pas de `context_window`, silence) : corrigé, avertissement une fois par modèle.
- low, second avis n° 6 (pages en double entre lots) : rejeté, chaque lot couvre des Blocks distincts et les `passage_id` sont uniques ; fusionner par titre serait un choix de conception non demandé.
- low, second avis n° 7 (Block tronqué jusqu'à vide envoyé) : corrigé, `ConfigError` si la fenêtre ne laisse aucune place au texte d'un Block.
- low, second avis n° 8 (tests manquants) : corrigé par les tests ci-dessus.
- low, revue : un `fidelity_model` explicite n'est plus contrôlé au Catalogue par `validate` (plus de `ModelRefMeta`) ; il l'est à la construction (`catalog.get`). Accepté.
- report : conformité (`tests/conformance/test_architectures.py`, `tests/e2e/test_sm3.py`) et Configuration `llm_wiki` de `experiments/mini-test.yaml` avec la story 4.14 ; livraison sous cette réserve.
- report : le Juge par défaut suit `profil.judge_pool`, pas un `judges.pool` d'Expérience (le Context ne le porte pas) ; à reprendre si l'Expérience doit le surcharger.
