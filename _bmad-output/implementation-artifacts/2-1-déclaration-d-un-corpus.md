---
story: "2.1"
title: Déclaration d'un Corpus
status: review
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
- Droits (AD-19) : seul `publishable: false` déclenche la vérification. `git rev-parse` détecte le dépôt, `git check-ignore -q <racine>` l'ignorance du dossier. Hors dépôt (ou git absent) : WARNING et vérification sautée.
- Deux fichiers au contenu identique donnent le même `doc_id` et des Ancrages ambigus : refusés par `ConfigError` (ajout non demandé, reporté à relecture).
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
