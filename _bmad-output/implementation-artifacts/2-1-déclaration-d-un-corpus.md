---
story: "2.1"
title: Déclaration d'un Corpus
status: done
---

# Story 2.1 : Déclaration d'un Corpus

## Code Map

- `src/wavelibrarian/corpus/declare.py` : `declare(chemin) -> DeclaredCorpus`, schémas `CorpusSpec`, `DocOverride`, `TiersSpec`, type `Document` (source_path, doc_id, format, lang, `DocMeta`), table `EXTENSIONS`.
- `src/wavelibrarian/core/ids.py` : ajout de `sha16_bytes` (doc_id = sha256(octets)[:16]).
- Tests : `tests/unit/corpus/test_declare.py`.

## Design Notes

- `path` est relatif au dossier de `corpus.yaml` ; les Documents sont parcourus récursivement, triés par `source_path` POSIX relatif à la racine du Corpus. Format reconnu par extension (`.md`, `.markdown`, `.txt`, `.html`, `.htm`, `.pdf`) ; le reste est signalé par `logging` (WARNING) et ignoré.
- Contradiction du contrat §4.1 : `documents:` a pour clé le `source_path` (relatif à la racine, AD-5), mais l'exemple écrit `docs/charte.md` avec `path: docs`. Lecture retenue : la clé est le `source_path` ; la forme préfixée par `path` est tolérée. Une clé qui ne désigne aucun Document retenu lève `ConfigError` à `documents.<clé>`.
- Tous les champs de §4.1 hors `documents` et `tiers` sont obligatoires (pas de défaut caché, AD-12). `tiers` est validé (graine, tailles strictement croissantes) mais non exploité (story 2.7).
- Droits (AD-19) : la garde vaut pour `publishable: false` et pour une licence restrictive (toute licence hors `LICENCES_OUVERTES` : CC0, CC-BY*, MIT, Apache, BSD, ODbL, PDDL, Etalab, LO). Fail-closed : le dépôt est détecté sans git (premier ancêtre portant `.git`) ; aucun `.git` = hors dépôt, WARNING et vérification sautée ; sinon `git check-ignore -q -- <racine>` doit répondre 0 et `git ls-files -- <racine>` être vide, toute erreur de git (absent, dubious ownership) refuse.
- Deux fichiers au contenu identique donnent le même `doc_id`, donc des `anchor_id` ambigus (AD-5) : refusés par `ConfigError` qui nomme les deux fichiers (décision confirmée en revue).
- Parcours : chemins cachés (composant en `.`) et liens symboliques exclus.
- Suite de `parser: auto` : `DeclaredCorpus.formats` expose les formats présents (`markdown`, `text`, `html`, `pdf`). La table format -> parser enregistré est à poser en 2.2.
- Aucune modification de `cli.py` ni de `pyproject.toml`.

## Tâches et critères

- [x] Quatre Documents triés par `source_path`, `doc_id` sur les octets, `e.docx` signalé et ignoré : `test_quatre_documents_tries_et_docx_ignore`.
- [x] Renommage `a.md` -> `z.md` : `doc_id` inchangé : `test_renommage_conserve_doc_id`.
- [x] `documents:` -> `DocMeta` et langue surchargée : `test_metadonnees_par_document`.
- [x] Clé inconnue = `ConfigError` au chemin : `test_cle_inconnue_et_mal_typee` ; `corpus_id` hors `[a-z0-9-]+` : `test_corpus_id_refuse`.
- [x] Non publiable dans le dépôt, non ignoré : refus expliqué : `test_non_publiable_dans_depot_non_ignore_refuse`.
- [x] Non publiable en dossier ignoré accepté : `test_non_publiable_dossier_ignore_accepte` ; hors dépôt avec avertissement : `test_non_publiable_hors_depot_avertit` ; publiable dans le dépôt : `test_publiable_dans_depot_accepte`.

## Auto Run Result

- Statut : review. 14 tests ciblés verts.
- Reports : table format -> parser et résolution de `auto` (2.2) ; exploitation de `tiers` (2.7) ; pas de commande CLI (2.4).

## Revue

- high, second avis 1 : AD-19 en fail-open si git échoue ou est absent. Corrigé : dépôt détecté par `.git` sans git, erreur de git = `ConfigError` (`test_non_publiable_git_en_erreur_refuse`, `test_hors_depot_constate_sans_git`).
- medium, second avis 2 : licence restrictive non gardée (§4.1). Corrigé : liste de licences ouvertes par préfixe, toute autre licence suit la garde de `publishable: false` (`test_licence_restrictive_dans_depot_refusee`).
- medium, second avis 3 : fichiers suivis dans un dossier ignoré. Non reproduit (`git check-ignore` répond 1 dès qu'un fichier du dossier est suivi) ; `git ls-files` ajouté en seconde barrière, test `test_non_publiable_ignore_mais_suivi_refuse`.
- medium, second avis 4 : fichiers cachés retenus (`.claude/`, `.git/` avec `path: .`). Corrigé : composants en `.` exclus.
- medium, second avis 5 : liens symboliques suivis hors racine. Corrigé : liens exclus avec WARNING (rglob 3.12 ne descend pas dans les dossiers liés, pas de boucle).
- medium, second avis 6 : refus des doublons de contenu. Rejeté : AD-5 fait de `doc_id` l'identité de version et la base des `anchor_id` ; deux fichiers identiques rendraient les Ancrages ambigus. Le message nomme déjà les deux fichiers.
- low, second avis 7 : `formats` renvoie des formats et non des parsers. Reporté en 2.2 (table format -> parser).
- low, second avis 8 : résolution ambiguë des clés `documents:`. Rejeté : la forme exacte prime, la forme préfixée est tolérée, une collision lève `ConfigError`.
- low, second avis 9 : cas hors dépôt non gardé. Corrigé par `test_hors_depot_constate_sans_git`.
- low, second avis 10 : un WARNING par fichier non reconnu. Rejeté : demandé par l'AC (`e.docx` signalé), le volume baisse avec l'exclusion des fichiers cachés.
- Report 2.2 : choisir le parser par format à partir de `DeclaredCorpus.formats` (`parser: auto`).
