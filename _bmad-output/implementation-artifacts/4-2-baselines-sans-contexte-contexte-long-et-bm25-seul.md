---
story: "4.2"
title: Baselines sans contexte, contexte long et BM25 seul
status: review
---

# Story 4.2 : Baselines sans contexte, contexte long et BM25 seul

## Code Map

- `src/wavelibrarian/architectures/no_context.py` : `NoContext` (`("architecture", "no_context")`, `retrieval_method: none`).
- `src/wavelibrarian/architectures/long_context.py` : `LongContext` (`full_corpus_in_prompt`, `retrieval_method: cited`, `check(profile)`).
- `src/wavelibrarian/architectures/bm25_only.py` : `Bm25Only` (`k: 5`, `query_params = {k}`).
- `src/wavelibrarian/architectures/_passages.py` : écriture et lecture de `passages.jsonl` (UTF-8, LF).
- `src/wavelibrarian/components/lexical_indexes/bm25.py` : `Bm25Index` (`("lexical_index", "bm25")`, bm25s).
- `src/wavelibrarian/components/retrievers/lexical.py` : `LexicalRetriever` (`("retriever", "lexical")`).
- `src/wavelibrarian/components/generators/llm.py` : paramètre `cache_system` (Contexte dans le system, mis en cache).
- Tests : `tests/unit/architectures/test_story_4_2.py` (Faux LLM, profil `test`).

## Design Notes

- Les trois Baselines passent `tokenizer=self.ctx.tokenizer_for(generator.model_id)` à `build_arch_answer` : le seuil de 8 000 tokens est compté avec le tokenizer du modèle du Generator (report 4.1 traité).
- `no_context` : `index` écrit un `passages.jsonl` vide et rien d'autre ; `load` ne fait rien ; le Contexte vide vient de `context_builder.build([])`, l'abstention du Faux LLM.
- `long_context` : un Passage `level 0` par Ancrage non vide (texte = Blocks de l'Ancrage joints), dans l'ordre des Documents puis des Ancrages ; `load` construit le Contexte une fois. Le Generator par défaut porte `cache_system: true` : le Contexte entre dans le `system` (`LLMRequest.cache_system`), la Question seule dans le message. Citations : un `ScoredPassage` par Ancrage cité (rang = ordre de première citation, score 1,0). `requires_prompt_cache` reste faux : sur un modèle sans cache, `cache_system` est ignoré sans erreur.
- `long_context.check` : tokens estimés = `tokens_for` ; pour un modèle au tokenizer `reference`, `tokens_for` rend les tokens de référence sans majoration, donc le facteur du Catalogue (`token_factor`, 1,5 pour Haiku 5.5) est appliqué, comme l'estimation de la passerelle (contracts §4.2 : 60 000 tokens de référence = environ 90 000 pour Haiku). Inapplicable si l'estimation dépasse `context_window` (raison citant la fenêtre) ou le `above_prompt_tokens` d'un palier tarifaire (raison citant le palier). La sortie du modèle n'est pas ajoutée à la fenêtre.
- `bm25` : les mots (minuscules, accents retirés, `\w+`) sont sauvegardés dans `lexical.json` ; l'index bm25s est reconstruit à la première recherche, ce qui rend `delete` exact. Seuls les Passages de score > 0 sont renvoyés, tri par score décroissant puis id.
- `bm25_only` : `index` écrit `passages.jsonl` et `lexical/lexical.json` dans le dossier ; `load` relit les deux sur une instance neuve. `k` est dans `query_params` : il n'entre pas dans `index_key`.

## Tâches et critères

- [x] `no_context` : Contexte vide, `retrieval_method: none`, `retrieved` vide, seul `passages.jsonl` vide : `test_no_context_contexte_vide_et_aucun_fichier_hors_passages`.
- [x] `long_context` : un bloc par Ancrage dans l'ordre des Documents, `cache_system`, Réponse `cited` rang 1, 2…, score 1,0 : `test_long_context_prompt_complet_system_en_cache_et_citations`, `test_long_context_defaut_cache_le_system`.
- [x] `check` : 120 000 tokens contre fenêtre 100 000, sans exception, raison citant la fenêtre : `test_long_context_inapplicable_au_dela_de_la_fenetre`.
- [x] `check` : Haiku 5.5 au-delà de 100 000 tokens estimés, raison citant le palier : `test_long_context_inapplicable_au_dela_du_palier_haiku`.
- [x] Index `bm25` : au plus k ids par score décroissant, ex æquo par id, `save` puis `load` ailleurs, `delete` : `test_bm25_recherche_ordre_et_sauvegarde`, `test_bm25_ex_aequo_departages_par_id`.
- [x] `bm25_only` : index dans un dossier puis instance neuve + `load`, `passages.jsonl` un Passage par ligne, `ranked`, Citation valide : `test_bm25_only_cycle_complet`.
- [x] `k` déclaré dans `query_params`, hors `index_key` : `test_bm25_only_k_hors_de_la_cle_d_index`, `test_bm25_only_k_limite_les_passages`.
- [x] Report 4.1 : troncature au-delà de 8 000 tokens depuis une Architecture : `test_long_context_tronque_au_dela_de_8000_tokens`, `test_bm25_only_tronque_au_dela_de_8000_tokens`, `test_long_context_sous_le_seuil_garde_tous_les_blocs`.

## Auto Run Result

- Statut : review. 581 tests verts (suite complète), pyright 0 erreur, ruff propre, contrôle rapide sans erreur.
- Reports de l'epic 4 traités : « 4.2 (Baselines) : passer `tokenizer=` et tester la troncature ».
- Écart : le critère parle d'un prompt « estimé (`tokens_for`) » ; `tokens_for` ignore `token_factor` pour un modèle `reference`, on applique donc le facteur (voir Design Notes).
- Reports : le Generator `llm` gagne `cache_system` (hors périmètre 4.1, nécessaire au critère) ; `long_context` ne compte pas la sortie dans la fenêtre ; la Condition contexte parfait de `long_context` passe par `answer_with_context` (défaut du port), sans cache de system.
