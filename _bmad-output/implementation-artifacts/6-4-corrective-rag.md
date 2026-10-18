---
story: "6.4"
title: Corrective RAG
status: done
---

# Story 6.4 : Corrective RAG

## Code Map

- `src/wavelibrarian/components/deciders/llm.py` : `LLMDecider` (`("decider", "llm")`, rôle `grade_relevance`, step `crag.grade.loopN`).
- `src/wavelibrarian/components/query_rewriters/llm.py` : `LLMQueryRewriter` (`("query_rewriter", "llm")`, rôle `rewrite`, step `crag.rewrite.loopN`).
- `src/wavelibrarian/architectures/corrective_rag.py` : `CorrectiveRag(NaiveRag)` enregistrée `("architecture", "corrective_rag")`.
- Tests : `tests/unit/architectures/test_story_6_4.py` (Faux LLM, faux embedder dim 64, profil `test`).

## Design Notes

- Index, `update`, `load`, `embedder_dim()` et capacités hérités de `naive_rag`. `query_params` = `k`, `threshold`, `max_loops`, `decider`, `query_rewriter` : tous hors de la clé d'index, qui reste celle de `naive_rag` (index dense réutilisé).
- Étape de la Trace : `Decider.grade` et `QueryRewriter.rewrite` reçoivent un argument nommé `loop` (défaut 0 et 1) ajouté aux Protocols `Decider`/`QueryRewriter` et au contrat §2, pour nommer `crag.grade.loopN` / `crag.rewrite.loopN`. Seule la passerelle trace ; l'Architecture ne trace rien.
- Boucle : recherche par la Question, notation (`loop0`). Tant qu'aucun Passage n'atteint `threshold` et que `boucle < max_loops` (borne vérifiée avant chaque reformulation) : reformulation de la requête courante, nouvelle recherche dense, notation. Les Passages sont notés au regard de la Question d'origine. Un Passage noté `>= threshold` (0,5 compris) entre dans le Contexte, dans l'ordre du Retriever.
- Sans Passage retenu après `max_loops` : `abstained: true`, texte vide, aucun appel `generate`. `max_loops: 0` note une fois puis s'abstient.
- `retrieved` : la liste classée de la dernière recherche (rangs du Retriever, `ranked`), pour les métriques de recherche ; le Contexte n'en garde que les Passages retenus. `generate` reçoit la Question d'origine, pas la reformulation.
- Decider : le schéma passé à la passerelle est celui du rôle borné à n scores (`minItems`/`maxItems`) ; un autre nombre, comme un score hors [0, 1], est une sortie non conforme refusée par la passerelle (second essai sans cache, rien de fautif mis en cache). Aucun Passage : pas d'appel.
- Choix hors AC : retriever autre que `dense` refusé à la construction (`ConfigError`), comme `hyde`. Pas de repli web.

## Tâches et critères

- [x] Decider `llm` : trois scores dans l'ordre, étape `crag.grade.loop0` : `test_decider_trois_scores_dans_l_ordre_a_l_etape_de_la_boucle`. Score hors bornes ou nombre incorrect = non conforme : `test_score_hors_bornes_est_une_sortie_non_conforme`, `test_un_nombre_de_scores_different_du_nombre_de_passages_est_non_conforme`. Enregistrements : `test_enregistrement_defauts_et_meme_index_que_naive_rag`.
- [x] Seuls les Passages notés à 0,5 ou plus entrent dans le Contexte, au moins une Citation : `test_seuls_les_passages_au_seuil_entrent_dans_le_contexte_et_la_reponse_en_cite_un`, `test_scores_par_defaut_du_faux_llm_au_dessus_du_seuil`.
- [x] Tout sous le seuil, `max_loops: 2` : deux reformulations et recherches, les cinq étapes `crag.*` dans la Trace, abstention, aucun `generate` : `test_tout_sous_le_seuil_deux_reformulations_puis_abstention_sans_generate`, `test_max_loops_zero_ne_reformule_pas`.
- [x] Sous le seuil puis au-dessus : génération après une reformulation, avec les Passages de la deuxième recherche : `test_une_reformulation_suffit_et_le_contexte_vient_de_la_deuxieme_recherche`.
- [x] `threshold` et `max_loops` dans `query_params`, index dense de mêmes paramètres réutilisé : `test_enregistrement_defauts_et_meme_index_que_naive_rag`. Cas limite : `test_retriever_autre_que_dense_refuse`.

## Auto Run Result

- Statut : review. Vérifications finales dans le rapport.
- Reports : Configuration `corrective_rag` dans `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` : absents du dépôt (story 4.14) ; à passer quand ils existent, sans réseau.
- Le cache de réponses de la passerelle (fake) inclut `step` dans la clé : les étapes `crag.*` ne se servent pas mutuellement.

## Revue

- medium, second avis 1 et 5 : corrigé. Le contrôle du nombre de scores venait après la validation et la mise en cache par la passerelle, sans second essai, et une relance relisait la réponse fautive. Le schéma est désormais `GradeRelevanceOutput` borné à n (`_schema_pour`), que la passerelle valide (second essai sans cache, remplacement). Test : `test_un_mauvais_nombre_de_scores_est_rejoue_sans_cache_et_jamais_mis_en_cache`.
- low, second avis 2 : corrigé. `loop` est ajouté aux Protocols `Decider` et `QueryRewriter` (`ports/components.py`) et à `contracts.md` §2.
- low, second avis 3 : rejeté. La réécriture par défaut du Faux LLM rend la Question inchangée, et l'AC 3 exige pourtant deux reformulations et les cinq étapes `crag.*` : s'arrêter sur une réécriture identique violerait l'AC.
- low, second avis 4 : reporté (déjà consigné). La conformité, `mini-test.yaml` et la SM-3 attendent la 4.14.
