---
story: "2.4"
title: Profil de corpus et commande `wl corpus profiler`
status: done
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

## Revue

Rebase sur `main` (story 3.1) : conflit dans `cli.py` seulement (imports et sous-apps `wl questions` / `wl corpus`), les deux apports gardés ; `core/types.py` fusionné sans conflit.

- medium, second avis 1 : apostrophe typographique non unifiée (« d’Orvane » ≠ « d'Orvane », lien manqué, vérifié) : corrigé, `’` ramenée à `'` avant extraction.
- medium, revue : une entité après élision (« l'ONU », « la ville d'Orvane », « qu'Anna ») était perdue par le lookbehind `(?<![\w'’-])` : corrigé, élisions françaises admises.
- medium, revue : « M. Durand » donnait l'entité « m », qui liait à tort tout Document citant « M. » : corrigé, entités d'une lettre écartées.
- medium, second avis 2 : fusion « Lyon Paris » : rejeté, l'AC demande des « séquences capitalisées » (« Jean Dupont » doit rester une entité) ; le Faux LLM (`_CAPITALISEE`, story 1.10) fusionne de même mais sert un autre rôle (début de phrase inclus, pas de liaisons), alignement non requis.
- medium, second avis 3 : `tokens_for` sans contrôle de `self.tokenizer` : rejeté, conforme à `contracts.md` §1 (« tokenizer du Catalogue si reference ») ; `approx` tient lieu de référence dans le profil `test`, méthode de la story 1.2 non modifiée.
- low, second avis 4 : `--sortie` par défaut dans le dossier courant : rejeté, §5 décrit les fichiers d'une Exécution (le runner, epic 4, écrira dans le dossier du run) ; la commande autonome n'a pas d'emplacement imposé.
- low, second avis 5 : encodage tiktoken absent en profil `cpu` -> code 1 : rejeté, §8 réserve 4 au préflight (Ollama, modèle, clé) ; le message renvoie à `wl installer`.
- low, second avis 6 et 7 : titre vide ignoré, profondeur = imbrication : rejeté, `heading_path` est la seule donnée de structure du modèle (pas de niveau de titre), conforme aux Design Notes et à l'AC.
- low, second avis 8 : décimales à point dans le résumé : corrigé, virgule décimale (`_fr`) ; le JSON garde des flottants.
- low, second avis 9 : `--profil` inconnu affiché « Corpus invalide » : corrigé, « Configuration invalide » (code 2 inchangé).
- low, revue : échec d'écriture de `corpus_profile.json` (OSError) remontait en trace : corrigé, message et code 1.
- low, second avis 10 et 11 : tests manquants, `model_copy` sans validation : tests ajoutés pour les correctifs ; `model_copy` n'est pas utilisé par le code de la story, rejeté.
