---
story: "3.4"
title: Juge LLM et correspondance exacte normalisée
status: done
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
- Jetons (revue) : une suite alphanumérique est un seul jeton (« A1412 », « 5e ») ; une plage ou date à tirets (« 1412-1413 », « 1412–1413 ») est un seul jeton ; le signe moins (y compris U+2212) tient au nombre qui le suit. Ligatures œ → oe, æ → ae.
- Milliers : espace, espace insécable ou fine, apostrophe dès un groupe ; point ou virgule seulement à partir de deux groupes au même séparateur (« 1.412.000 », « 1,412,000 »). Un seul groupe à virgule est décimal (contrat : « 3,5 » = « 3.5 »), donc « 1,412 » vaut 1.412 ; « 12 100 » vaut 12100.
- Limites assumées : critère d'inclusion, donc une négation (« pas en 1412 ») ou une disjonction (« 1412 ou 1413 ») matche ; les articles ne sont pas retirés (le contrat ne le demande pas).

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

## Revue

Revue Opus en une passe, après rebase sur `main` (83fad4f). Constats du second avis (Haiku) repris un par un.

- medium, second avis 1 (signe moins non tokenisé, `-3` = `3`) : confirmé par exécution ; corrigé, le signe tient au nombre.
- medium, second avis 2 (nombre collé à des lettres ou pris dans une plage : `A1412`, `1412-1413`, `5e`) : confirmé ; corrigé, jetons alphanumériques entiers et plage en un jeton. Disjonction « 1412 ou 1413 » et négation : non tranchées par le contrat, limite du critère d'inclusion consignée (Design Notes, docstring).
- medium, second avis 3 (cas négatifs manquants) : confirmé ; ajoutés à `test_exact_match_faux` (et positifs associés dans `test_exact_match_vrai`).
- low, second avis 4 (`100` contre `12 100`) : rejeté ; « 12 100 » est 12100 selon la règle des milliers à l'espace, l'ambiguïté est inhérente.
- low, second avis 5 (`1,412`, `1.412.000`) : corrigé pour les groupes multiples (point ou virgule, au moins deux groupes) ; `1,412` reste 1.412 car le contrat impose la virgule décimale.
- low, second avis 6 (œ/oe, articles) : œ → oe et æ → ae corrigés (normalisation typographique) ; articles rejetés, le contrat ne les cite pas.
- low, second avis 7 (justification vide acceptée par `CriterionVerdict`) : reporté à 3.5, schéma partagé `llm/roles.py` ; vérifier qu'un verdict sans justification est traité (nouvel essai ou refus).
- low, second avis 8 (`judge_pool[0]` par défaut sans filtre de Famille) : reporté à 3.5 (AD-14, Juge d'une autre Famille que le modèle testé).
- low, second avis 9 (`context_texts` repris du Generator) : reporté à l'epic 4 (Panel construit le `JudgeInput`) ; le Juge transmet tel quel ce qu'il reçoit, testé.
- Revue : aucun autre constat medium ou high ; le Juge n'a pas encore d'appelant (3.5, epic 4), enregistrement par `registry` vérifié.
