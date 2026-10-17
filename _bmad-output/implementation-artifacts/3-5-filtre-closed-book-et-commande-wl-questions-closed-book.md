---
story: "3.5"
title: Filtre closed-book et commande `wl questions closed-book`
status: review
---

# Story 3.5 : Filtre closed-book et commande `wl questions closed-book`

## Code Map

- `src/wavelibrarian/evalset/closed_book.py` : `filtrer(ctx, fichier, modeles)` -> `Filtrage` (fichier mis à jour, verdicts, `unanswerable` exclues) ; `valider_modeles` (Catalogue, doublons).
- `src/wavelibrarian/cli.py` : `wl questions closed-book <questions.yaml> [--modeles a,b] [--profil] [--graine]`.
- Tests : `tests/unit/evalset/test_closed_book.py`.

## Design Notes

- Une Question `validated` ou `corrected` hors `unanswerable` est posée à chaque modèle, rôle `closed_book`, sans autre contexte que son texte (l'historique d'une Question de suivi n'est pas transmis). Chaque appel est dans `ctx.scope(post="judging", question_id=...)`.
- Réponse courte : `exact_match(reference_answer, sortie)`, sans Juge. Réponse libre : `LLMJudge` construit par `ctx.build` avec `model = closed_book_judge(modèle testé, judge_pool, catalogue)` (premier modèle du réservoir d'une autre Famille, AD-14) ; critère `correctness`, `pass_id` 0, `reference_texts` vide (closed-book).
- Les Juges sont résolus avant le premier appel : réservoir sans autre Famille = `ConfigError` (code 2), rien de payé.
- Relance : pour chaque Question testée, les entrées de `contaminated_by` des modèles retestés sont remplacées, celles des autres modèles conservées. Le fichier n'est réécrit que s'il change ; `freeze` et tous les autres champs sont intacts (empreinte AD-15 valide, `contaminated_by` exclu).
- Codes : 2 (modèle inconnu du Catalogue ou répété, `--modeles` vide, fichier invalide, pas de Juge), 3 (Plafond, fichier inchangé), 4 (fournisseur).
- Report RUN-STATUS « justification vide » : le contrat (`Verdict.justification: str = ""`) l'autorise, donc rien n'est refusé ; le Filtre n'utilise que le booléen.
- Report RUN-STATUS « `closed_book_models` au Catalogue » : traité (`valider_modeles`, aussi pour `--modeles`).
- Report RUN-STATUS « Juge par Famille » : traité. `LLMJudge` garde `judge_pool[0]` par défaut (le Panel de l'epic 4 passe `model`) ; le Filtre le surcharge toujours.
- Limite : le coût du Juge n'est pas affiché (le Juge ne renvoie pas les `LLMResult`) ; il reste compté au Poste `judging` dans le registre de dépense.

## Tâches et critères

- [x] `wl questions closed-book --modeles fake-llm-a,fake-llm-b` : Questions `validated`/`corrected` posées sans contexte au rôle `closed_book`, `unanswerable` (et `generated`/`rejected`) non posées : `test_questions_validees_posees_sans_contexte_unanswerable_exclues`.
- [x] Sans `--modeles`, liste de `closed_book_models` du profil : `test_sans_modeles_la_liste_vient_du_profil`.
- [x] Réponse courte contenant la référence : `contaminated_by`, correspondance exacte, aucun appel Juge : `test_reponse_courte_contenant_la_reference_contamine_sans_juge`.
- [x] Réponse libre : verdict du Juge d'une autre Famille ; contaminée si « oui » : `test_reponse_libre_jugee_par_une_autre_famille`, `test_verdict_non_du_juge_ne_contamine_pas`.
- [x] Faux LLM par défaut : aucune contamination : `test_faux_llm_par_defaut_aucune_contamination`.
- [x] Jeu Gelé : seul `contaminated_by` change, `freeze` conservé ; spans `wl.post=judging` : `test_jeu_gele_seul_contaminated_by_change_et_relance_remplace`, `test_relance_identique_ne_reecrit_pas_le_fichier`.
- [x] Reports : modèles au Catalogue (`test_modele_inconnu_ou_repete_code_2_sans_appel`), Juge par Famille sans autre Famille (`test_pool_sans_autre_famille_code_2_avant_appel`), Plafond (`test_plafond_code_3_fichier_inchange`).

## Auto Run Result

- Statut : review. 11 tests ciblés verts ; suite complète 538 verts ; pyright 0 erreur ; ruff propre ; contrôle rapide sans erreur.
- Reports : (1) `question_gen_model` au Catalogue est déjà contrôlé par `generer` (3.3) ; (2) le Gel (3.6) devra ignorer `contaminated_by` dans l'empreinte (déjà le contrat) ; (3) le Panel (epic 4) construit le `JudgeInput` complet.
