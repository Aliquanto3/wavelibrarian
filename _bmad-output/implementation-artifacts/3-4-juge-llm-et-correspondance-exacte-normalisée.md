---
story: "3.4"
title: Juge LLM et correspondance exacte normalisée
status: review
---

# Story 3.4 : Juge LLM et correspondance exacte normalisée

## Code Map

- `src/wavelibrarian/components/judges/llm.py` : `LLMJudge`, enregistré `("judge", "llm")`, `Params.model` en `ModelRef` (défaut `judge_pool[0]` du profil).
- `src/wavelibrarian/scoring/answer.py` : `exact_match(reference, answer)` (s'ajoute à `is_short_form`, story 3.1).
- Tests : `tests/unit/components/test_llm_judge.py`, `tests/unit/scoring/test_answer.py`.

## Design Notes

- Un appel `judge` par `judge(item, criteria, pass_id)`. Le schéma de sortie est construit pour les Critères demandés : un Critère absent de la réponse du modèle est non conforme, donc un nouvel essai (`complete_structured`), puis `NonConformantOutput`.
- `pass_id` va dans `LLMRequest.pass_id`, donc dans la clé du Cache de réponses (FR-34). Le Juge ne fixe pas le Poste de coût : l'appelant (Panel, closed-book) ouvre `ctx.scope(post="judging")`.
- `faithfulness` : `context_texts` du `JudgeInput` est repris tel quel dans le prompt et dans `inputs` (jamais reconstruit, AD-6). Sans ce Critère, ces textes ne sont pas envoyés (coût d'entrée).
- `exact_match` : la référence normalisée doit figurer comme suite de mots entiers dans la réponse normalisée. Normalisation : casse, accents (NFKD), ponctuation, regroupement des milliers (espaces, espaces insécables, apostrophe), virgule décimale en point, zéros de tête et zéros décimaux de fin retirés. Un nombre ne correspond jamais à un fragment d'un autre (« 1412 » n'est pas dans « 14120 »). Référence vide : faux.
- Limite assumée : « 1,412 » (notation anglaise des milliers) vaut 1.412, pas 1412.

## Tâches et critères

- [x] Un seul appel `judge` ; verdict booléen et justification par Critère : `test_un_seul_appel_pour_tous_les_criteres`, `test_verdict_non_quand_la_reponse_s_ecarte`.
- [x] Composant enregistré `("judge", "llm")`, `model` en `ModelRef` : `test_enregistre_et_modele_par_defaut_du_reservoir`.
- [x] Sortie non conforme après un nouvel essai : `NonConformantOutput` : `test_sortie_non_conforme_apres_un_nouvel_essai`, `test_critere_manquant_est_non_conforme`.
- [x] `pass_id` 0 puis 1 : le second n'est pas servi par le Cache : `test_pass_id_sort_du_cache_de_reponses`.
- [x] `exact_match` : « 1 412 » / « en 1412 », « Élodie Varn » / « elodie varn », « 3,5 » / « 3.5 », « 1413 » ≠ « 1412 » : `test_exact_match_vrai`, `test_exact_match_faux`.
- [x] `is_short_form` reconnaît nombre, date, au plus 5 mots (déjà livré, story 3.1) : tests existants de `test_answer.py`.
- [x] `faithfulness` : `context_texts` repris du Generator : `test_faithfulness_reprend_les_textes_du_generator`.
- [x] Report RUN-STATUS 3.4 (`exact_match` dans `scoring/answer.py`) traité.

## Auto Run Result

- Statut : review. Tests ciblés verts (Juge, `exact_match`) ; suite complète 490 verts ; pyright 0 erreur ; ruff propre ; contrôle rapide sans erreur.
- Reports : (1) construction du `JudgeInput` (texte des Ancrages, `context_texts` du Generator) à faire dans le Panel (epic 4) ; (2) le Juge ne fixe pas le Poste `judging` : le Panel et le closed-book (3.5) doivent ouvrir `ctx.scope(post="judging")` ; (3) choix du Juge d'une autre Famille pour le closed-book : story 3.5 (AD-14).
