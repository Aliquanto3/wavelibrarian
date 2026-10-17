---
story: "1.6"
title: Validation statique d'une Expérience et formation du Panel
status: review
---

# Story 1.6 : Validation statique d'une Expérience et formation du Panel

## Code Map

- `src/wavelibrarian/config/validate.py` : `validate_experiment(experience, source, wl_home)` et `validate_file(chemin, wl_home)` rassemblent tous les refus en un `ValidationFailed` ; renvoient un `ValidationResult` (Expérience résolue, Catalogue, Panel par Configuration).
- `src/wavelibrarian/config/panel.py` : `form_panel`, `closed_book_judge`, `excluded_judges` (lecture de `calibration.json`).
- `src/wavelibrarian/config/resolve.py` : `_Collecte` devient `Collecte` (public) et relève chemins de modèles, Composants, embedders et Juges explicites ; `resolve_experiment(..., erreurs=, releves=)` passe en mode agrégation.
- `src/wavelibrarian/config/load.py` : `load_experiment(chemin, verifier_params=True)`.
- `src/wavelibrarian/cli.py` : commande `wl run <experience.yaml>` (validation seule).
- `tests/unit/config/test_validate.py`.

## Design Notes

- Articulation avec la 1.5 : `load_experiment` reste strict par défaut (première `ConfigError`). `validate_file` le charge avec `verifier_params=False` puis rejoue la résolution en mode agrégation : une erreur de `params`, un Composant ou une Architecture inconnus, un modèle absent du Catalogue sont notés et le parcours continue (au sein d'une Configuration comme d'une Configuration à l'autre). Une Architecture inconnue saute le reste de sa Configuration. Une erreur de schéma, de profil, de Catalogue ou de coûts reste unique (enveloppée dans un `ValidationFailed`).
- Contrôles : modèle absent du Catalogue (chemin du champ `ModelRef`), `requires_hybrid_store` contre `StoreCapabilities.hybrid` de chaque `vector_store` de la Configuration, `requires_prompt_cache` contre `prompt_cache` de chaque `answer_producer` (le message cite le modèle), dimension de `WL_HOME/index/<clé>/manifest.json` contre `dim` du Catalogue pour chaque embedder, Juge explicite, Panel. Le prix des modèles d'API est déjà exigé au chargement du Catalogue (1.4). Les erreurs sont dédoublonnées sur (chemin, message).
- `reuse_index` : clé de forme `[A-Za-z0-9_-]+`, manifeste illisible ou absent = refus ; manifeste sans `embedder_dim` ou Configuration sans embedder = rien à comparer. `WL_HOME` : paramètre, sinon variable d'environnement, sinon `./.wl`.
- Juge « déclaré explicitement » : tout modèle référencé par un `ModelRef` sous un Composant de `kind` `judge` dans la Configuration (suivi par la pile des `kind` de `Collecte`). Un modèle du réservoir de la même Famille est seulement écarté du Panel, pas refusé. `judges.calibration_judge` n'est pas contrôlé (il ne note pas les Réponses d'une Configuration).
- Panel (AD-14) : `panel_size` premiers modèles du réservoir, ordre déclaré, hors Famille de chaque `answer_producer` et hors Juges exclus ; moins de 2 = `ConfigError` (`judges.pool`, message préfixé de l'id de la Configuration). Un `panel_size` de 1 est donc toujours refusé.
- Format de `calibration.json` retenu (le contrat ne le fixe pas) : `{"judges": {"<modèle>": {"excluded": bool, "criteria": {...}}}}`. À respecter par `wl calibrer` (epic 3).
- `closed_book_judge(modèle_testé, réservoir, catalogue)` prend le Catalogue en plus : les Familles ne se lisent que là. `form_panel` et `closed_book_judge` vivent dans `config/` (couche basse), `scoring/` les importera.
- CLI : erreurs sur stderr en français avec leur chemin, code de sortie 2 ; Expérience valide : « Validation réussie. » (le préflight de la 1.12 et le runner de l'epic 4 s'y insèrent).

## Tâches et critères

- [x] Trois défauts regroupés en un `ValidationFailed`, chacun avec son chemin, sans réseau : `test_trois_defauts_en_une_erreur`, `test_plusieurs_defauts_dans_une_meme_configuration`, `test_params_inconnus_agreges_avec_le_reste`, `test_erreur_de_schema_devient_validation_failed`.
- [x] `requires_prompt_cache` contre `prompt_cache: false`, message citant le modèle : `test_cache_de_prompt_non_satisfait`.
- [x] Index réutilisé de dimension incompatible refusé : `test_index_de_dimension_incompatible` (et `test_index_de_meme_dimension_accepte`, `test_index_sans_embedder_dim_accepte`, `test_index_introuvable_ou_cle_invalide`, `test_wl_home_pris_dans_l_environnement`).
- [x] Panel `[fake-llm-b, fake-llm-c]` dans l'ordre déclaré ; exclusion par `calibration.json` = refus ; Juge explicite de la Famille du Generator refusé : `test_form_panel_ordre_declare_et_famille`, `test_form_panel_exclusion_par_calibration_et_minimum`, `test_panel_refuse_par_la_validation`, `test_calibration_illisible`, `test_pool_avec_modele_inconnu`, `test_juge_explicite_de_la_famille_du_generator`.
- [x] `closed_book_judge` renvoie le premier modèle d'une autre Famille : `test_closed_book_judge`.
- [x] `wl run` : erreurs en français avec chemin et code 2 ; Expérience valide « Validation réussie » : `test_cli_experience_invalide`, `test_cli_experience_valide`, `test_cli_fichier_absent`.

## Auto Run Result

- Statut : prêt pour revue.
- Reports : le format de `calibration.json` est à confirmer par `wl calibrer` (epic 3) ; `wl run` ne fait que valider jusqu'à l'epic 4 ; `Architecture.check(profile)` (fenêtre, palier) reste à appeler par le runner après profilage ; `requires_hybrid_store` sans aucun `vector_store` dans la Configuration n'est pas refusé.
- Aucun appel réseau, ni Ollama, ni GPU (`CUDA_VISIBLE_DEVICES=-1`, threads à 4).
