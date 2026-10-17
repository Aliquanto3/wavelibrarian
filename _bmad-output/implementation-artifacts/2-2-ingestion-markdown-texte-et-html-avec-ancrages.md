---
story: "2.2"
title: Ingestion Markdown, texte et HTML avec Ancrages
status: done
---

# Story 2.2 : Ingestion Markdown, texte et HTML avec Ancrages

## Code Map

- `src/wavelibrarian/components/parsers/_sections.py` : `SectionBuilder` commun (pile de titres, slugs, suffixe ordinal, Blocks et Ancrages dans l'ordre).
- `src/wavelibrarian/components/parsers/markdown.py`, `text.py`, `html.py` : Parsers `markdown` (markdown-it-py, commonmark + tableaux), `text`, `html` (beautifulsoup4, analyseur `html.parser`), enregistrés au `kind` `parser` avec leurs `formats`.
- `src/wavelibrarian/corpus/ingest.py` : `ingest(corpus, parser="auto", *, wl_home=None) -> ParsedCorpus`, `parsers_par_format(formats, parser)` (table format -> Parser concret, report de 2.1), `nom_parser_resolu(...)`.
- Tests : `tests/unit/corpus/test_ingest.py`. Aucune modification de `cli.py` ni de `pyproject.toml`.

## Design Notes

- Un Block est rattaché au titre le plus profond ouvert (`<doc_id>#h/<slug>/<slug>`) ; le titre est lui-même un Block `heading` de son Ancrage. Texte avant le premier titre et fichier `text` : `<doc_id>#h/`. Niveaux sautés (h1 puis h3) : le chemin ne contient que les titres réellement présents.
- Titres frères de même slug : le premier garde le slug, les suivants prennent `-2`, `-3`... ; si le suffixe collisionne avec un autre titre frère, on continue à incrémenter. `ParsedCorpus.resolve` cherche d'abord le chemin de titres bruts (espaces normalisés), puis le chemin de slugs : un vrai titre « Note 2 » est retrouvé, et pour des doublons exacts le premier ; les suivants s'adressent par `anchor_id`. Titre sans caractère alphanumérique : slug `section`.
- Markdown : un Block `text` par paragraphe, liste, citation ou bloc de code ; `table` (lignes `a | b`) ; `image` (texte alternatif, sinon `src`) émis après le texte de son paragraphe. HTML : même découpage ; tampon de texte en ligne vidé aux frontières de blocs ; `script`, `style`, `head`, `template` ignorés.
- `parser: auto` : table `AUTO` dans `ingest.py` (`markdown`, `text`, `html`, `pdf` -> `pdf_text`). Un format sans Parser enregistré (PDF avant la story 2.3) ou un Parser explicite qui ne couvre pas un format présent lève `ConfigError("parser", ...)` plutôt que d'ignorer les Documents. Le runner (epic 4) appelle `parsers_par_format(corpus.formats, "auto")` puis `nom_parser_resolu` pour écrire un nom concret.
- Cache `<WL_HOME>/parse_cache/<parser>/<doc_id>.json` (écriture atomique). Il est par contenu : à la relecture, `source_path`, `lang` et `meta` sont repris du Document déclaré (renommage sûr). Fichier corrompu : reparse. Un Document dont le Parser lève `OSError`/`ValueError` est signalé et ignoré.
- `ParsedCorpus` trié par `source_path`, `fingerprint = sha16` des couples `(source_path, doc_id)` triés. `ingest.py` n'importe pas `components` : `registry.discover()` puis `registry.get("parser", nom)`.

## Tâches et critères

- [x] Parsers enregistrés avec `formats` : `test_enregistrement_au_registre`.
- [x] Markdown : `anchor_id` `<doc_id>#h/histoire/fondation`, kinds `text/table/heading/image`, textes non vides, `anchors` dans l'ordre, `heading_path` brut, texte avant titre sous `#h/` : `test_markdown_blocks_et_ancrages`.
- [x] Fichier `text` sans titre sous `<doc_id>#h/` : `test_texte_sans_titre_sous_ancrage_vide`, `test_markdown_sans_titre_rattache_a_h_vide`.
- [x] HTML `h1` à `h3` et `table` : `test_html_hierarchie_et_tableau`.
- [x] Titres frères identiques distincts et déterministes : `test_freres_identiques_ordinal_deterministe` (et `test_niveaux_sautes_et_remontee`).
- [x] `auto` résolu en noms concrets par le registre, sans import de `components` : `test_parsers_par_format_auto`.
- [x] `ParsedCorpus` trié et `fingerprint` : `test_ingest_trie_fingerprint_et_resolve`.
- [x] Cache écrit puis relu sans appeler le Parser (compteur) : `test_cache_relu_sans_appeler_le_parser` ; robustesse : `test_cache_corrompu_reparse_et_renommage`, `test_corpus_vide`.
- [x] `resolve` et `anchor_text` d'une section : `test_ingest_trie_fingerprint_et_resolve`.

## Auto Run Result

Tests ciblés : 12 verts. Suite complète : 312 verts. Pyright et contrôle rapide : sans erreur.

Reports : ancrage des doublons non adressable par `resolve` (hors périmètre, suffixe documenté) ; Parser `pdf_text` à la story 2.3 (jusque-là `auto` refuse un Corpus contenant des PDF) ; `cli.py` (`wl corpus profiler`) à la story 2.4.

## Revue

Revue Opus 5.5, une passe, liste du second avis (Haiku) vérifiée par exécution.

- high, second avis 1, corrigé : `resolve(("Doc", "Note 2"))` renvoyait `note-2` (doublon de « Note ») au lieu de `note-2-2`, citation fausse sans signal. `resolve` cherche maintenant le `heading_path` brut, puis le chemin de slugs ; test dans `test_freres_identiques_ordinal_deterministe`.
- medium, second avis 2, corrigé : `errors="replace"` donnait `#h/t` pour un `<h1>Été</h1>` en cp1252. Décodage UTF-8 strict (BOM toléré) puis repli cp1252 signalé au journal (`_sections.decoder`) ; slug `Été` → `ete` vérifié ; `test_encodage_utf8_et_repli_cp1252`.
- medium, second avis 3, corrigé : un titre dans une citation ou une liste devenait du texte sans Ancrage (le HTML, lui, traite les titres imbriqués). Il ouvre maintenant sa section ; `test_titre_dans_citation_ou_liste_ouvre_une_section`.
- medium, second avis 4, corrigé : cache de parsing non versionné. Chaque Parser porte `version` ; le fichier `parse_cache/<parser>/<doc_id>.json` (chemin du contrat inchangé) enveloppe le Document avec `parser_version`, une autre version reparse ; test dans `test_cache_corrompu_reparse_et_renommage`.
- medium, second avis 5, corrigé : tests ajoutés (doublons et `resolve`, encodage, CRLF, `script`/`style` dans le `body`) ; assertion `any(... or ...)` remplacée par une égalité exacte.
- low, revue, corrigé : en HTML, une balise en ligne suivie d'une ponctuation donnait « Fin grasse . » (espace parasite) ; le tampon joint désormais le texte sans séparateur ajouté.
- second avis 6, rejeté (orchestrateur) : l'AC demande un Ancrage indépendant du Découpage, et AD-5 fonde l'`anchor_id` sur le `doc_id` de la version.
- low, second avis 7, corrigé : le message de `ConfigError` pour un PDF indique « Parser « pdf_text » non encore disponible ».
- low, revue, reporté : un `html_block` Markdown est gardé brut (balises comprises) dans un Block `text` ; un HTML non UTF-8 ignore son `<meta charset>` (repli cp1252 seulement). À reprendre si le Mini-corpus (2.5) en contient.
- Report 2.3 : `pdf_text` doit déclarer `version` (sinon `"0"`) et s'enregistrer pour lever le refus de `auto` sur un Corpus avec PDF.
