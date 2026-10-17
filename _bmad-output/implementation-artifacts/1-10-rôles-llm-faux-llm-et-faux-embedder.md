---
story: "1.10"
title: Rôles LLM, Faux LLM et faux embedder
status: review
---

# Story 1.10 : Rôles LLM, Faux LLM et faux embedder

## Code Map

- `src/wavelibrarian/llm/roles.py` : `ROLES` (15 `RoleSpec` : clés obligatoires d'`inputs`, schéma pydantic de sortie ou `None` pour le texte libre), les schémas de sortie, `check_inputs(request)`.
- `src/wavelibrarian/llm/gateway.py` : `_run` appelle `check_inputs` en premier (avant marquage, cache, réservation, appel, span).
- `src/wavelibrarian/llm/providers/fake.py` : `FakeProvider` (protocole `Provider`), `script(role, step_glob, output)`, `default_output`.
- `src/wavelibrarian/components/embedders/fake.py` : `FakeEmbedder`, enregistré `("embedder", "fake")`.
- Tests : `tests/unit/llm/test_roles_fake.py`, `tests/unit/components/test_fake_embedder.py` ; `test_gateway.py` fournit désormais des `inputs` valides à `_req` ; les fixtures de `test_experiment.py` et `test_validate.py` vident le registre avant d'y poser leurs Composants de test (le vrai `fake` y est maintenant présent).

## Design Notes

- Un rôle déclare ses clés dans `ROLES` ; une assertion à l'import vérifie que `ROLES` couvre exactement `LLMRole`. Une clé manquante lève `WlError` (liste des clés) dans la passerelle, pour tout provider, avant tout effet de bord.
- Schémas gelés, sans `extra="forbid"` (un modèle réel peut ajouter une clé sans que la sortie soit rejetée). `scores` dans [0, 1] et `supported <= claims` sont validés. `answer_form` : `short` ou `free` (contracts.md §4.5).
- Faux LLM : ne lit que `inputs` ; les mots du prompt ne servent qu'au comptage des tokens et à la reconnaissance d'un préfixe vu. Découpage en phrases sur `. ! ?` suivis d'un blanc ; mots = `\w+` en minuscules.
- `generate` : abstention (réponse « Information introuvable dans les sources. », `citations` vide) si `blocks` est vide ou sans `S1`.
- `judge` : même verdict pour tous les critères ; oui si au moins 50 % des mots distincts de la référence figurent dans la réponse (référence vide : non).
- `extract_entities` : séquences de mots capitalisés (un mot de début de phrase compte), dédoublonnées ; une relation (poids 1.0) entre entités voisines. `select_nodes` : `done` vaut toujours `true`. `agent_step` : sans résultat à l'étape 2 ou plus, `answer` avec `abstain: true` ; `args` de `answer` = `answer`, `citations` (l'id du premier résultat), `abstain`. `question_gen` : une question `factual` par ancrage, `answer_form: free`, `types` ignoré.
- Tokens : `input_tokens` = mots du system et des messages moins les mots lus du cache ; `output_tokens` = mots de la sortie ; `cache_read_tokens` = mots du plus long préfixe en cache (system si `cache_system`, messages jusqu'à un `cache`) déjà vu par cette instance ; `cache_write_tokens` reste 0.
- `script` : le premier scénario dont le rôle est égal et dont le glob (`fnmatchcase`) couvre `step` répond ; la sortie peut être une chaîne ou une fonction de la requête (marquée). Un scénario n'est pas validé contre le schéma : c'est la passerelle qui lève `NonConformantOutput`.
- Cache : `step` n'entre pas dans la clé, donc deux appels de même prompt, mêmes `inputs` et même `pass_id` partagent leur réponse, scénarisée ou non (règle de 1.8).
- Faux embedder : sac de mots haché (`blake2b`, indice et signe) en dimension du Catalogue (64), norme L2 = 1 (float32), texte vide ramené à un vecteur fixe ; `embed_queries` = `embed_passages`. Un span `embed` (kind `embed`, coût 0 EUR, tokens du `ctx.tokenizer_for`) par appel, y compris pour une liste vide.

## Tâches et critères

- [x] Les 15 rôles déclarent clés et schéma (`test_quinze_roles_declares`, `test_sortie_par_defaut_valide_pour_chaque_role`).
- [x] Clé manquante refusée par la passerelle avant tout appel (`test_cle_manquante_refusee_avant_tout_appel`, aucun span écrit).
- [x] Sortie par défaut valide pour chaque rôle, sans lire le prompt (`test_sortie_par_defaut_valide_pour_chaque_role`, `test_ne_lit_jamais_le_texte_du_prompt`).
- [x] `generate` cite `S1`, abstention si `blocks` vide (`test_sortie_par_defaut_valide_pour_chaque_role[generate]`, `test_generate_abstention_si_blocks_vide`).
- [x] Tokens en mots, `cache_read_tokens` d'un préfixe vu, latence 0 (`test_tokens_en_mots_et_latence_nulle`, `test_cache_read_tokens_prefixe_deja_vu`, `test_latence_nulle_par_la_passerelle`).
- [x] `script("grade_relevance", "crag.*", ...)` prime sur le défaut (`test_script_prime_sur_le_defaut`, `test_script_callable_et_role_inconnu`, `test_script_non_conforme_leve_apres_un_nouvel_essai`).
- [x] `inputs` différents donc pas de service par le cache (`test_inputs_differents_pas_servis_par_le_cache`).
- [x] Faux embedder enregistré, dim 64, norme 1, identique d'un appel à l'autre (`test_enregistre_et_construit_par_le_contexte`, `test_vecteurs_dim_norme_et_determinisme`).
- [x] Les deux premiers textes plus proches entre eux que du troisième (`test_proximite_lexicale`).
- [x] Un span `embed` par appel d'`embed_*` (`test_chaque_appel_emet_un_span_embed`).

## Auto Run Result

Livré sans réseau, sans GPU, sans appel Ollama. Reports : `cache_write_tokens` du faux reste 0 (le contrat ne le demande pas) ; la suite de conformité des Architectures (stories 5.x) fixera le contenu attendu de `agent_step` et `select_nodes` en boucle ; le runner (epic 4) doit construire `FakeProvider` et le passer à `build_gateway(providers={"fake": ...})`.
