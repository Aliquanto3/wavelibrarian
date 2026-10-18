---
story: "6.3"
title: HyDE
status: done
---

# Story 6.3 : HyDE

## Code Map

- `src/wavelibrarian/architectures/hyde.py` : `Hyde(NaiveRag)` enregistrée `("architecture", "hyde")` ; Params de `naive_rag` plus `mix_question: false`, `hyde_model` (défaut `generator_models[0]` du profil), `hyde_max_tokens: 256`.
- Tests : `tests/unit/architectures/test_story_6_3.py`.

## Design Notes

- Index, `update`, `load`, `embedder_dim()` et capacités hérités de `naive_rag` : même chunker, embedder et store, donc mêmes paramètres d'index (`index_key` identique à celui de `naive_rag`).
- `query_params` = `k`, `mix_question`, `hyde_model`, `hyde_max_tokens` : hors de la clé d'index, l'index est réutilisé.
- `answer` : un appel `complete` au rôle `hyde` (step `hyde`, entrée `text` = Question) puis `embed_queries` de la réponse hypothétique, vecteur passé au Retriever (`query_vector`). Le poste (`query`) vient du `scope` du Runner ; la passerelle trace le span `hyde`, distinct de `generate`. L'Architecture ne trace rien.
- `mix_question: true` : `embed_queries([hypothèse, question])`, moyenne puis renormalisation ; somme nulle : vecteur de l'hypothèse seul.
- Le texte hypothétique ne sort pas de `answer` : ni Contexte, ni prompt `generate`, ni Citation.
- Choix hors AC : une réponse hypothétique vide se rabat sur le vecteur de la Question ; tout retriever autre que `dense` est refusé (`ConfigError`) : `lexical` ignorerait le vecteur, `hybrid` exige un index lexical que l'index de `naive_rag` ne construit pas. Le repli est journalisé (`WARNING`), l'Architecture ne trace pas de span.

## Tâches et critères

- [x] Rôle `hyde`, step `hyde`, poste `query`, span distinct de `generate` : `test_hyde_appelle_le_role_hyde_au_poste_query_hors_du_span_generate`.
- [x] Vecteur du Retriever = `embed_queries` de la réponse hypothétique : `test_le_vecteur_du_retriever_est_celui_de_la_reponse_hypothetique`.
- [x] `mix_question` : moyenne renormalisée, dans `query_params`, défaut `false` : `test_mix_question_moyenne_renormalisee_et_dans_query_params`, `test_enregistrement_defauts_et_meme_index_que_naive_rag`.
- [x] Réponse hypothétique absente du Contexte et des Citations : `test_la_reponse_hypothetique_n_entre_ni_dans_le_contexte_ni_dans_les_citations`.
- [x] Hypothèse reprenant les mots d'un Passage : ce Passage est au rang 1 : `test_hypothese_reprenant_les_mots_d_un_passage_donne_le_rang_1`.
- [x] Même index que `naive_rag` : `test_enregistrement_defauts_et_meme_index_que_naive_rag`. Cas limites : `test_reponse_hypothetique_vide_se_rabat_sur_la_question`, `test_retriever_lexical_refuse`.

## Auto Run Result

- Statut : done (sous réserve du report 4.14 ci-dessous). Vérifications finales dans le rapport de l'orchestrateur.
- Reports : Configuration `hyde` dans `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` absents du dépôt (story 4.14 non livrée) ; à vérifier quand ils existent, sans réseau.
- Le Cache de réponses sert un second appel `hyde` identique (même Question) sans nouvel appel : comportement voulu de la passerelle, non modifiée.

## Revue

- medium, revue : `hybrid` annoncé accepté mais `WlError` à chaque Question (pas d'index lexical dans l'index de `naive_rag`), après l'appel `hyde` payé. Corrigé : `dense` seul accepté, test `test_retriever_autre_que_dense_refuse`.
- medium, second avis 1-2 : `FakeEmbedder` identique pour `embed_queries` et `embed_passages`, une régression passait. Corrigé : espion sur les deux méthodes, `test_la_requete_passe_par_embed_queries_et_non_embed_passages`.
- medium, second avis 3 : Configuration `mini-test.yaml`, conformité et `test_sm3.py` absents. Reporté vers 4.14 (décision de l'orchestrateur) : ajouter `hyde` et faire passer les deux suites sans réseau.
- low, second avis 4 : `hyde_model` et `hyde_max_tokens` non testés. Corrigé : `test_hyde_model_et_hyde_max_tokens` (requête et `index_key`).
- low, second avis 5 : repli silencieux sur la Question. Corrigé : `WARNING` journalisé avec l'id de Question ; pas d'attribut de span, une Architecture ne trace pas (epic 6).
