---
story: "3.6"
title: Gel et séparation développement / test
status: review
---

# Story 3.6 : Gel et séparation développement / test

## Code Map

- `src/wavelibrarian/evalset/freeze.py` : `geler(doc, dev_ratio, seed, at)` -> `QuestionsFile` ; `empreinte(doc)` ; `nb_dev(n, ratio)` ; `verify_frozen(doc)` ; `select_questions(questions, split)`.
- `src/wavelibrarian/evalset/io.py` : `load_agrege(chemin)` (toutes les erreurs du fichier, `ValidationFailed`) ; `load` inchangée.
- `src/wavelibrarian/cli.py` : `wl questions geler <questions.yaml> [--dev-ratio 0.4] [--graine 42]`.
- `tests/unit/evalset/test_freeze.py`.

## Design Notes

- Empreinte = SHA-256 de `canonical_json(model_dump)` sans `freeze` ni, par Question, `contaminated_by`. Elle inclut `split` et `status` : changer l'un ou l'autre après le Gel est détecté. Calculée après attribution des `split`.
- Répartition : par `type`, parmi les Questions `validated` / `corrected` ; ids triés puis mélangés par `random.Random` initialisé avec le SHA-256 de `graine + type` (indépendant de l'ordre du fichier et des autres Types, AD-20). Les `n_dev` premiers vont en dev.
- Arrondi : `n_dev = round_half_up(n * dev_ratio)` (10 x 0,4 = 4 ; 3 x 0,4 = 1 ; 1 x 0,4 = 0). Un Type d'une seule Question va donc en test. `dev_ratio` hors de [0, 1] est refusé.
- Les Questions `rejected` ne participent pas : `split` remis à `null`. Une Question `generated` bloque le Gel (`ConfigError` qui liste les ids, code 2, fichier inchangé).
- Re-geler un jeu déjà gelé est permis (mêmes graine et contenu : même résultat) ; le `split` précédent est ignoré.
- `verify_frozen` : `ConfigError` (`freeze`) si non gelé, (`freeze.sha256`) si empreinte différente. Le runner l'appellera (epic 4).
- `select_questions` accepte un `QuestionsFile` ou une séquence de Questions ; `split` est obligatoire (`dev` ou `test`), donc la partie test n'est jamais renvoyée par défaut.
- Report 3.1 traité : `geler` charge le fichier par `io.load_agrege`, qui agrège les erreurs de schéma et les ids en double, une ligne par erreur et un total. Les autres commandes gardent `io.load` (première erreur).

## Tâches et critères

- [x] 50 Questions validées sur cinq Types, `geler --dev-ratio 0.4 --graine 42` : 40 % de dev par Type, `freeze = {sha256, at, seed, dev_ratio}`, empreinte de `canonical_json` hors `freeze` et `contaminated_by` : `test_gel_stratifie_40_pour_cent_par_type`, `test_arrondi_documente`, `test_empreinte_est_le_sha_du_json_canonique_sans_freeze_ni_contaminated_by`, `test_cli_geler_ecrit_le_gel_et_est_reproductible`.
- [x] Second Gel, même graine et même contenu, même répartition : `test_meme_graine_meme_repartition_quel_que_soit_l_ordre`, `test_cli_geler_ecrit_le_gel_et_est_reproductible`.
- [x] Question modifiée après le Gel : `ConfigError` empreinte différente ; jeu non gelé refusé : `test_verify_frozen_refuse_un_texte_modifie`, `test_verify_frozen_refuse_un_split_ou_un_statut_modifie`, `test_verify_frozen_refuse_un_jeu_non_gele`, `test_verify_frozen_accepte_un_jeu_intact_et_relu_du_disque`.
- [x] Seul `contaminated_by` change : empreinte valide : `test_contaminated_by_ne_casse_pas_l_empreinte`.
- [x] `select_questions(split="dev")` : validated / corrected de la partie dev ; test seulement sur demande explicite : `test_select_questions_dev_et_test_explicite`.
- [x] Questions `generated` : signalées, Gel refusé : `test_gel_refuse_les_questions_generated_et_les_liste`, `test_cli_geler_refuse_les_generated_sans_ecrire`.
- [x] Report 3.1, erreurs agrégées : `test_load_agrege_rapporte_toutes_les_erreurs`, `test_load_agrege_fichier_valide`, `test_cli_geler_agrege_les_erreurs_du_fichier`.

## Auto Run Result

Livré, `status: review`. Tests ciblés : 18 verts. Aucun écart aux AC. Reports : appeler `verify_frozen` et `select_questions` depuis le runner (epic 4) ; contrôle de l'unicité des ids et de l'agrégation d'erreurs non étendu à `controler`, `generer` et `closed-book`.
