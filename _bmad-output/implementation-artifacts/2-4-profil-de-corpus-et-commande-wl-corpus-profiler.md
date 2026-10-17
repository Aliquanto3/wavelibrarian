---
story: "2.4"
title: Profil de corpus et commande `wl corpus profiler`
status: review
---

# Story 2.4 : Profil de corpus et commande `wl corpus profiler`

## Code Map

- `src/wavelibrarian/corpus/profile.py` : `profile(corpus, parser=, tokenizer=, volatility=)` -> `CorpusProfile`.
- `src/wavelibrarian/corpus/entities.py` : `extraire_entites`, `link_density` (heuristique sans réseau ni LLM).
- `src/wavelibrarian/cli.py` : sous-app `wl corpus`, commande `profiler` (`--parser`, `--profil`, `--sortie`).
- `tests/unit/corpus/test_profile.py` : tests de la story. `CorpusProfile.tokens_for` existait (story 1.2) et n'est pas modifié.
- `src/wavelibrarian/core/types.py` : protocole `_EntreeCatalogue` en propriétés en lecture seule, pour que `ModelCatalog` le satisfasse sous pyright (aucun changement de comportement).

## Design Notes

- Tokens : tokenizer de référence du profil d'exécution, sur le texte de tous les Blocks (images comprises, leur texte étant en général vide ou un alt court). `table_share` = tokens des Blocks `table` / tokens totaux.
- Profondeur de titres d'un Document : plus longue `heading_path` de ses Ancrages (0 sans titre, le Document comptant dans la moyenne).
- `dominant_lang` : plus grand nombre de Documents ; égalité -> ordre alphabétique (déterminisme).
- Entités : séquences capitalisées (liaisons `de`, `du`, `des`, `de la`, `of`, `the`, `d'`), premier mot de chaque phrase ou ligne écarté, titres ignorés, comparaison insensible à la casse. `link_density` = part des Documents partageant au moins une entité avec un autre.
- Corpus sans Document ingéré : `ConfigError` (code 2).
- CLI : `--profil` (défaut `cpu`, tokenizer `reference` qui ne télécharge rien et exige `wl installer`) ; `--sortie` (défaut dossier courant) reçoit `corpus_profile.json` (`model_dump(mode="json")`). `ConfigError` -> code 2, autre `WlError` -> 1.
- Report : l'AC dit « profil `test` » sans option dans la commande de l'énoncé ; `--profil` est ajouté pour le choisir.

## Tâches et critères

- [x] Valeurs du profil sur le corpus connu (3 Documents, profondeurs 1/2/3, tableau 20/200, 2 images, fr/fr/en), `tokenizer`, `volatility` : `test_profil_aux_valeurs_connues`, `test_langue_dominante_a_egalite_est_alphabetique`.
- [x] `link_density` = 2/3, heuristique : `test_link_density_deux_tiers`, `test_entites_hors_debut_de_phrase`.
- [x] `tokens_for` : 50 000 / 75 000 / défaut 1,2 : `test_tokens_for_reference_facteur_et_defaut`.
- [x] CLI : `corpus_profile.json` écrit, résumé français, code 0 : `test_cli_ecrit_le_profil`.
- [x] `corpus.yaml` invalide -> code 2 : `test_cli_corpus_invalide_sort_en_code_2`.
- [x] Corpus vide refusé : `test_corpus_vide_est_refuse`.

## Auto Run Result

Livré, en revue. Aucune dépendance ajoutée. Report : le runner (epic 4) devra écrire `corpus_profile.json` dans le dossier du run en appelant `profile()`.
