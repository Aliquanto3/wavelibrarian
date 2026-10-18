---
story: "4.6"
title: Condition contexte parfait et Paliers de volume
status: done
---

# Story 4.6 : Condition contexte parfait et Paliers de volume

## Code Map

- `src/wavelibrarian/runner/execute.py` : `_Runner.configuration` boucle sur les Conditions puis sur les Paliers (`_cellule` exécute un couple Condition/Palier) ; `passages_de_reference(parse, q)` (un Passage `level 0` par Ancrage de référence), `chemins_requis(questions, presents)` (`required_paths`), `verifier_paliers(experience, questions)` (refus code 2) et `_Runner.palier` (sous-corpus et Profil du Palier, par `corpus/tiers.py::tirer`). `_hors_perimetre` ne refuse plus que `scenario` (story 4.7). `poser` appelle `answer_with_context` quand on lui donne les Passages.
- `src/wavelibrarian/architectures/long_context.py` : `LongContext.answer_with_context` (Generator `llm` reconstruit avec `cache_system: false`).
- `src/wavelibrarian/cli.py` : `wl run` appelle `verifier_paliers` juste après le contrôle du Gel (avant le préflight).
- Tests : `tests/unit/runner/test_story_4_6.py`. Le test de refus de la story 4.4 (`test_conditions_et_paliers_refuses_explicitement`) est supprimé ; les fixtures de `test_installer.py` et `test_validate.py` neutralisent aussi `verifier_paliers`.

## Design Notes

- Contexte parfait : l'Architecture reçoit `QuestionInput` et les Passages, rien d'autre. Pas de `check()` ni d'index (le Corpus n'entre pas dans le prompt, et un index d'Architecture à embeddings coûterait pour rien) ; une seule phase d'énergie `query`. Les Réponses portent `retrieval_method: provided`, y compris en `error`. Les Ancrages en doublon sont dédoublonnés. `unanswerable` : Contexte vide.
- Ancrage vers un Document créé par le Scénario (par exemple `chronique-1415.md`, Question `q-044`, `scenario_target.state: after`) : absent du Corpus de base, donc la Réponse en contexte parfait de la phase `base` est `status: inapplicable` (non-applicabilité structurelle, pas une panne). Ces Questions relèvent de la phase après mise à jour (story 4.7). Un autre Ancrage introuvable reste en `error`.
- `required_paths` : Documents des Ancrages de référence des Questions posées, limités aux Documents présents au Corpus. Le tirage est le même pour tous les Palier (`tirer` emboîte) et fait par parser résolu.
- Paliers : chaque Palier est indexé sur son sous-corpus avec sa propre `index_key` (la `fingerprint` du sous-corpus change). `check()` juge le Profil du Palier, non du Corpus entier : `long_context` peut être inapplicable à un Palier et applicable à un autre. `applicability.json` garde la clé `config_id` sans Palier et prend `<config_id>@<taille>` (avec `tier`) sinon.
- Le contexte parfait s'exécute aussi par Palier quand `tier` est posé (une ligne par config, Condition, Palier), pour que les lignes d'`answers.jsonl` et le Rapport aient la même grille.
- Refus avant tout appel (code 2) : Corpus sans clé `tiers`, taille absente de `tiers.sizes`, et tirage à blanc impossible (Documents requis plus nombreux que le plus petit Palier). `verifier_paliers` est appelé par `cli.py` et à l'entrée de `run_experiment`.
- Un Palier ne dépend pas des autres tailles (préfixe d'un même mélange) : `tier: <taille>` seul ne tire que ce Palier, et les Documents requis doivent tenir dans celui-ci, non dans le plus petit déclaré (`tirer_chemins(..., tailles)`). L'emboîtement est inchangé.
- Mini-corpus : le split `dev` entier a 12 Documents requis, plus que le Palier de 5. `tier: all` sur le split complet est donc refusé (code 2), avec un message qui nomme le Palier (`tiers.sizes[0]`) et le remède (`max_questions` ou un Palier plus grand) ; `tier: 20` passe. Les tests de `tier: all` limitent par `max_questions`.
- Les prompts du contexte parfait sont identiques d'un Palier à l'autre : à partir du deuxième Palier, le cache LLM sert les Réponses (coût nul hors premier Palier).
- `ArchitectureBase.answer_with_context` par défaut passe par `build_arch_answer` (déplacé dans `ports/arch_answer.py`, réexporté par `components.context`) : troncature à 8 000 tokens et `context_truncated` comme `answer`. `retrieved` reprend les Passages fournis, dans l'ordre (méthode `provided`, contracts.md §1).

## Tâches et critères

- [x] AC 1 : Passages de référence dans l'ordre des `reference_anchors`, texte de `anchor_text`, via `answer_with_context` ; `condition: perfect_context` sur les `Answer` : `test_contexte_parfait_passages_de_reference_et_aucune_reference_a_l_architecture`.
- [x] AC 1 : l'Architecture et le Generator ne reçoivent que `QuestionInput` et des Passages (espions) : même test.
- [x] AC 1 : `unanswerable` reçoit un Contexte vide : `test_question_unanswerable_recoit_un_contexte_vide`.
- [x] AC 2 : `required_paths` = Documents des Ancrages de référence : `test_required_paths_sont_les_documents_des_ancrages_de_reference`, `test_paliers_all_sous_corpus_index_et_lignes_distincts` (requis dans chaque Palier, Paliers emboîtés).
- [x] AC 2 : sous-corpus et `index_key` par Palier, `tier` sur les `Answer` et les spans, une ligne distincte par Palier : `test_paliers_all_sous_corpus_index_et_lignes_distincts`, `test_palier_inapplicable_long_context_est_juge_sur_son_sous_corpus`, `test_paliers_et_contexte_parfait_combines`.
- [x] AC 3 : `tier: 10` n'exécute que ce Palier : `test_palier_unique_seul_ce_palier_s_execute`.
- [x] AC 3 : taille non déclarée refusée en code 2 avant tout appel : `test_taille_non_declaree_refusee_en_2_avant_tout_appel` ; Corpus sans `tiers` : `test_corpus_sans_tiers_refuse_en_2` ; requis trop nombreux : `test_paliers_trop_petits_pour_les_documents_requis_refuses_en_2`.
- [x] Report « Runner (epic 4), Paliers » (`required_paths` déduits des Ancrages, passés à `tirer`) : tests d'AC 2.
- [x] Report « Runner des Conditions » (contexte parfait de `long_context` sans cache du system) : `test_long_context_en_contexte_parfait_sans_cache_du_system`.
- [x] Sans Palier ni Condition, comportement inchangé : `test_sans_palier_ni_condition_le_comportement_est_inchange`.

## Auto Run Result

- Statut : review. Vérifications : voir le rapport de l'orchestrateur.
- Reports traités : `required_paths` des Paliers ; contexte parfait de `long_context` sans cache du system.
- Reports laissés : Scénario (story 4.7) ; reprise et Questions restantes `budget_exceeded` (story 4.8) ; Panel (story 4.9).
- Risques : le contexte parfait est rejoué à chaque Palier (même résultat, coût multiplié par le nombre de Paliers hors cache) ; à revoir si le Rapport de la 4.13 préfère une seule ligne. Les Questions de Scénario sont en `error` en contexte parfait tant que la 4.7 n'existe pas.

## Revue

Revue Opus du 2026-10-18 (rebasée sur `main` 89b3758), constats du second avis (Haiku) repris un par un.

- medium, second avis 1 : `q-044` en `error` en contexte parfait de la phase `base`. Corrigé : `inapplicable` si `scenario_target.state: after` et Ancrage absent du Corpus de la phase, `error` sinon ; la Question reste posée en Condition standard (le choix des Questions par phase relève de la 4.7).
- medium, second avis 2 : `tier: 20` seul refusé à cause du Palier de 5. Corrigé : `tirer_chemins`/`tirer` prennent `tailles`, le runner et `verifier_paliers` ne tirent que les Paliers demandés ; message avec le Palier fautif et le remède. Emboîtement vérifié par test.
- medium, second avis 3 : `answer_with_context` par défaut sans troncature ni `context_truncated`. Corrigé : passe par `build_arch_answer` (déplacé dans `ports` pour respecter les couches AD-1), test unitaire de troncature.
- medium, revue : `retrieved` vide pour `retrieval_method: provided`, contraire à contracts.md §1 (« Passages fournis au Generator, dans l'ordre »). Corrigé dans le défaut et dans `long_context`.
- medium, second avis 4 : `tier: all` inexécutable sur le split `dev` du Mini-corpus. Corrigé pour le message (Palier et remède) ; reporté : la 4.14 (Expériences livrées) doit poser `max_questions` ou un `tier` adapté pour toute Expérience à Paliers sur le Mini-corpus (vérifier `wl run` en code 0 sur chaque Expérience livrée).
- low, second avis 5 : pas d'espion sur `check()` en contexte parfait. Corrigé (test qui échoue si `check()` est appelé).
- low, second avis 6 : vérifier que la Réponse de référence n'est pas dans le prompt. Corrigé en partie : le test apparie chaque appel à sa génération, vérifie bloc par bloc que le Contexte ne reprend que les Passages fournis, et que la Réponse de référence n'y figure pas quand aucun Ancrage ne la contient (elle y figure légitimement sinon, c'est le principe du contexte parfait).
- low, second avis 7 : prompts identiques entre Paliers. Consigné dans les Design Notes (le cache LLM absorbe le coût).
- low, second avis 8 : `palier()` lève hors du `try`. Corrigé : un tirage en échec met la cellule en `error` sans arrêter l'Exécution.
- low, second avis 9 : commentaire « 13 Documents ». Corrigé (12).
