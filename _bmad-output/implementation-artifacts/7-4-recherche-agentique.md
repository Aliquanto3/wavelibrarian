---
story: "7.4"
title: Recherche agentique
status: done
---

# Story 7.4 : Recherche agentique

## Code Map

- `src/wavelibrarian/architectures/agentic.py` : `Agentic(ArchitectureBase)` enregistrée `("architecture", "agentic")`, `retrieval_method: provided`, `incremental_update: false` (réindexation complète). Params : `max_steps = 8`, `max_cost_per_question = {amount: "0.05", currency: USD}`, `k = 5`, `agent_model`, `agent_max_tokens = 512` (tous `query_params`), `chunker` (`fixed_tokens`), `lexical_index` (`bm25`), `context_builder`, `generator` (requis par la Condition contexte parfait, non appelé par `answer`). Aucun embedder.
- Index : `passages.jsonl`, `lexical/` (BM25), `agentic.json` (texte de chaque Ancrage, Documents).
- `AgentStep(AgentStepOutput)` : valide les `args` selon l'action (sinon sortie non conforme).
- `tests/unit/architectures/test_story_7_4.py`. Aucun changement de `roles.py` ni de `fake.py` (le rôle `agent_step` et son comportement par défaut conviennent).

## Design Notes

- Outils (méthodes `_outil_search`, `_outil_read`, `_outil_list`, lecture seule, limités à l'index) : `search(query)` = BM25 via le retriever `lexical`, un résultat `{id: anchor_id, text}` par Ancrage ; `read(id)` = texte de l'Ancrage, message `Erreur : Ancrage inconnu` renvoyé à l'agent pour un id inconnu (aucune exception, rien n'est lu) ; `list()` = `{id: doc_id, text: chemin}`.
- Boucle : étape `n` = un appel `agent_step`, step `agent.step<n>`, `inputs = {question, step, last_results}` (résultats de l'outil de l'étape précédente). Le message de l'agent porte aussi l'historique des étapes (action, args, résumé). `answer` clôt la boucle.
- Bornes avant chaque appel : `max_steps` (au plus 8 appels, puis abstention) ; `engage >= max_cost_per_question` sur la somme des `cost_uncached` des appels rendus par la passerelle (lecture : borne atteinte = épuisée ; une borne nulle interdit tout appel) : abstention sans appel suivant. `cost_uncached` rend le comportement identique avec ou sans Cache de réponses (FR-4). Une devise différente de la borne lève `WlError`.
- Sortie non conforme (AD-4) : action hors `search|read|list|answer` ou `args` invalides (`AgentStep`) : la passerelle réessaie une fois sans cache, puis `NonConformantOutput` remonte ; le runner passe la Question en `error`. `args` stricts (`extra="forbid"`).
- Réponse : `retrieved` = extraits lus par `read`, dans l'ordre de lecture, dédoublonnés (`provided`) ; Citation = `anchor_id` lu ; ids cités mais non lus retirés et comptés dans `invalid_citations`. Abstention (borne ou `abstain`) : texte vide pour une borne, extraits lus conservés.
- Fenêtre (leçon 7.1 à 7.3) : avant chaque appel, si le message dépasse la fenêtre du modèle de l'agent (system et `agent_max_tokens` compris), les textes des résultats sont réduits de moitié jusqu'à tenir, puis l'historique le plus ancien est écarté, avec un avertissement ; `ConfigError` si la question seule n'y tient pas. L'extrait lu est alors enregistré tel que l'agent l'a vu.
- Aucune trace dans l'Architecture : les spans viennent de la passerelle (Poste `query` fixé par le runner).
- Coût de la tentative non conforme : `complete_structured` le rend dans `LLMResult.retry_cost_uncached` (défaut 0, rétrocompatible) ; l'agent l'ajoute à la somme de la borne (revue).
- Report : `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` n'existent pas dans ce commit de base (story 4.14 en attente) ; la Configuration `agentic` et le passage de conformité restent à ajouter avec 4.14.

## Tâches et critères

- [x] Outils `search`, `read`, `list` en lecture seule, limités au Corpus indexé : `test_outils_en_lecture_seule_et_limites_au_corpus` ; `read` inconnu = message : `test_read_d_un_ancrage_inconnu_renvoie_un_message_sans_exception`, `test_read_inconnu_cote_agent_message_renvoye_puis_reponse` ; `list` : `test_list_renvoie_les_documents`
- [x] Faux LLM par défaut : `search`, `read` du premier résultat, `answer`, Citation valide, spans `agent.step<n>`, extraits lus dans l'ordre, `provided` : `test_question_factuelle_search_read_answer_et_citation_valide`, `test_extraits_lus_dans_l_ordre_de_lecture`, `test_aucun_resultat_le_faux_llm_s_abstient_a_l_etape_2`
- [x] `max_steps: 8` : au plus 8 appels puis abstention : `test_max_steps_8_au_plus_8_appels_puis_abstention`, `test_max_steps_plus_petit`
- [x] `max_cost_per_question` vérifié avant chaque appel sur `cost_uncached`, identique avec Cache de réponses : `test_borne_de_cout_avant_chaque_appel_et_identique_avec_cache`, `test_borne_de_cout_nulle_aucun_appel`
- [x] Action inconnue ou `args` invalides : non conforme, un nouvel essai, puis erreur : `test_sortie_non_conforme_reessayee_une_fois_puis_erreur`
- [x] Citations non lues retirées et comptées : `test_citation_d_un_ancrage_non_lu_retiree_et_comptee`
- [x] Fenêtre du modèle sans troncature silencieuse : `test_fenetre_reduit_les_resultats_avec_avertissement`, `test_fenetre_ecarte_l_historique_ancien`, `test_fenetre_sans_place_pour_la_question_erreur_de_configuration`
- [x] Enregistrement, défauts, clé d'index : `test_enregistrement_et_capacites`, `test_defauts_des_bornes`, `test_index_key_ne_depend_pas_des_bornes`

## Auto Run Result

Voir le rapport de l'agent : tests ciblés, suite complète, pyright et contrôle rapide.

## Revue

Revue Opus du 2026-10-18 sur f0cb884, rebasé sur `main` (cbf8454, aucun conflit).

- medium, second avis 1 : corrigé. La tentative non conforme réessayée n'entrait pas dans `max_cost_per_question`. `NonConformantOutput` porte désormais son `cost_uncached`, `complete_structured` le rend dans `LLMResult.retry_cost_uncached` (défaut 0, rétrocompatible), et l'agent l'additionne. Test : `test_borne_de_cout_compte_la_tentative_non_conforme`, qui échoue sans le correctif.
- medium, second avis 2 : rejeté. Le contrat ne fait passer en abstention ni `abstain: false` sans Citation valide, ni `abstain: true` avec Citations. Le Generator `llm` transmet `abstain` et les Citations tels quels, et le Scoring juge ces cas (`citation_correctness`, `abstention_correctness`).
- low, second avis 3 : corrigé. Au dernier pas, le message demande l'action `answer` (`test_derniere_etape_demande_answer`). Une sortie qui n'y répond pas mène toujours à l'abstention prévue par le critère.
- low, second avis 4 : rejeté. Le choix est consigné dans les Design Notes : l'extrait est enregistré tel que l'agent l'a vu, pour que `retrieved` reflète le contexte réel de la Réponse. La troncature n'a lieu que si la fenêtre l'impose, et elle est signalée par un avertissement.
- low, second avis 5 : corrigé. Si les résultats dépassent encore la fenêtre une fois réduits et l'historique vidé, une `ConfigError` est levée (`test_fenetre_identifiants_trop_longs_erreur_de_configuration`).
- low, second avis 6 : corrigé. La réserve de fenêtre compte le schéma JSON de `AgentStep`, qu'un fournisseur `schema_in_prompt` ajoute au prompt.
- low, second avis 7 : corrigé. Un `agentic.json` malformé lève une `WlError` (`test_index_agentic_json_malforme_erreur`).
- Reporté (4.14) : la Configuration `agentic` dans `experiments/mini-test.yaml` et le passage de la conformité et du SM-3. Vérification à faire : `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` verts pour `agentic`, sans réseau, dont au moins une Citation valide avec le Faux.
