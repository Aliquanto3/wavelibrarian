---
story: "2.3"
title: Ingestion PDF avec Ancrages par page
status: done
---

# Story 2.3 : Ingestion PDF avec Ancrages par page

## Code Map

- `src/wavelibrarian/components/parsers/pdf_text.py` : Parser `pdf_text` (pypdfium2), `formats = {"pdf"}`, `version = "1"`, enregistré au `kind` `parser`.
- `src/wavelibrarian/corpus/ingest.py` : seul le commentaire d'`AUTO` change ; `pdf` -> `pdf_text` y figurait déjà, et `pdf_text` étant désormais enregistré, `auto` accepte un Corpus contenant des PDF.
- `tests/unit/components/test_pdf_text.py` : tests de la story (PDF générés par fpdf2 dans le test). `tests/unit/corpus/test_ingest.py` : l'attente « pdf_text non disponible » devient `{"pdf": "pdf_text"}`.

## Design Notes

- Un Ancrage `<doc_id>#p<n>` (n dès 1) par page, `page` renseigné, sans `heading_path`. Un seul Block `text` par page non vide, extrait par `get_text_bounded` (texte de la page entière, sans OCR).
- Page sans texte : l'Ancrage existe mais aucun Block n'est émis (pas de Block vide pour les Chunkers) ; `anchor_text` renvoie alors `""`.
- PDF illisible (ouverture ou page) : le Parser lève `ValueError`, que l'ingestion de 2.2 attrape déjà : Document signalé au journal et ignoré, les autres continuent. Rien n'est mis en cache.
- Le cache de parsing de 2.2 s'applique tel quel (`version` déclarée, invalidation par version testée). `resolve` existant couvre `page` (candidat `#p<n>` s'il est dans `anchors`).
- Hors périmètre : docling (extra), non utilisé ici ; images et tableaux des PDF non extraits.

## Tâches et critères

- [x] `pdf_text` enregistré, `formats = {"pdf"}`, `version` déclarée : `test_enregistre_avec_formats_et_version`, `test_auto_accepte_un_corpus_avec_pdf`.
- [x] PDF de trois pages : `anchor_id` `<doc_id>#p<page>` dès 1, texte de chaque page retrouvé, une entrée `anchors` par page avec `page` : `test_trois_pages_ancrees_dans_l_ordre`.
- [x] Page sans texte : Ancrage présent, texte vide, aucune exception : `test_page_sans_texte_garde_son_ancrage`.
- [x] PDF tronqué : signalé et ignoré, les autres Documents ingérés : `test_pdf_tronque_leve_value_error`, `test_ingestion_ignore_le_pdf_illisible_et_resout_les_pages`.
- [x] `resolve("registre.pdf", 2, ())` -> `<doc_id>#p2`, page 9 -> `None` : `test_ingestion_ignore_le_pdf_illisible_et_resout_les_pages`.
- [x] Report 2.2 : `version` + cache versionné pour le PDF : `test_cache_versionne_pour_le_pdf`.

## Auto Run Result

Livré et revu. Aucune dépendance ajoutée (pypdfium2 et fpdf2 étaient déjà déclarés). Report : aucun nouveau.

## Revue

Revue Opus en une passe, avec la liste du second avis (Haiku). Essai réel : sur un PDF fpdf2, PDFium rend un tiret de césure de fin de ligne par U+0002 (« porte\x02monnaie ») et ne restitue aucune ligne vide.

- medium, second avis 1 (césure) : corrigé. U+0002 était laissé dans le texte et coupait le mot ; `normaliser` recolle le mot (un mot composé coupé à son tiret perd ce tiret, choix consigné dans le module). Test `test_normalise_cesure_ligatures_et_controles`.
- low, second avis 1 (dé-enveloppement des lignes) : rejeté. PDFium ne rend pas de ligne vide, donc pas de frontière de paragraphe fiable ; le saut de ligne vaut une espace pour BM25 et les embeddings, et le Parser `text` garde aussi les sauts internes aux paragraphes. Chaque ligne est seulement débarrassée de ses espaces de bord.
- medium, second avis 2 (Unicode, contrôles) : corrigé. Aucun autre Parser ne normalise (leurs entrées sont du texte source) ; NFKC choisi pour le PDF seul (ligatures, espaces insécables), puis suppression des caractères de contrôle C0/C1 hors `\n` et `\t`, de U+00AD et de U+FFFE/FFFF. Consigné dans le docstring du module.
- low, second avis 3 (PDF entier en mémoire) : consigné dans le module ; les octets sont déjà lus par l'ingestion, rien à corriger.
- low, second avis 4 (`len(pdf)` hors du `try`) : corrigé. Une `PdfiumError` sur le nombre de pages devient `ValueError`, donc Document signalé et ignoré. Le `finally` fermait déjà le document.
- low, second avis 5 (chemin de l'AC) : corrigé. `source_path` est relatif à la racine du Corpus (`path`), d'où `registre.pdf` dans le test d'origine ; `test_resolve_avec_le_chemin_de_l_ac` pose la racine au-dessus de `docs/` et appelle `resolve("docs/registre.pdf", …)` tel que l'énonce l'AC.
- low, second avis 6 (PDF chiffré, fermeture) : corrigé. `test_pdf_chiffre_leve_value_error` (mot de passe utilisateur : `ValueError`) et `test_document_ferme_meme_en_cas_d_erreur` (fermeture sur succès et sur page illisible).
- low, second avis 7 (Ancrages partagés entre Documents identiques) : rejeté, antérieur à la story et déjà réglé en 2.1 par le refus des doublons.
- `version` du Parser laissée à `"1"` : la sortie change, mais aucune version n'a été livrée sur `main` avant cette revue.
