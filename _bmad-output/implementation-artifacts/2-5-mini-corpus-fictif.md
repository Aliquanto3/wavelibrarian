---
story: "2.5"
title: Mini-corpus fictif
status: review
---

# Story 2.5 : Mini-corpus fictif

## Code Map

- `corpora/minicorpus/corpus.yaml` : `publishable: true`, CC-BY-4.0, `documents:` (langue `en`, `rights_profiles`), `tiers`.
- `corpora/minicorpus/docs/` : 20 Documents (16 Markdown, 4 PDF), univers inventé de l'Archipel de Vaelmor.
- `corpora/minicorpus/pdf-src/*.txt` : sources des 4 PDF ; `scripts/make_minicorpus_pdfs.py` (fpdf2) les régénère dans `docs/`.
- `scripts/fonts/` : DejaVu Sans et Sans Bold (TTF) avec leur licence.
- `corpora/minicorpus/scenario/` : `scenario.yaml` (`add`, `modify`, `delete`) et `updates/`.
- `corpora/minicorpus/extras/` : `sentinelle.md` (faits uniques), `document-piege.md` (injection indirecte).
- `tests/conftest.py` : fixture de session `minicorpus` (`ParsedCorpus`, Parsers `auto`, cache de parsing dans un dossier temporaire).
- `tests/unit/corpus/test_minicorpus.py` : tests de la story.

## Design Notes

- Contenu : 14 Documents français et 2 anglais en Markdown ; 4 PDF français dont `convention-douane.pdf` sur 3 pages et `lettre-torvane.pdf` sans titre. `atlas-vaelmor.md` a trois niveaux de titres et deux tableaux ; `charte-conseil-v1.md` et `charte-conseil-v2.md` portent le même titre avec des valeurs contradictoires (quatre ou six ans, sept ou neuf sièges). Les Documents liés partagent « Compagnie des Marées Grises » et « Oswin Dacrel ».
- Taille : environ 3 000 mots (tokenizer `approx`), soit bien moins que les 60 000 tokens de référence.
- PDF reproductibles : date de création fixée, donc sortie identique à l'octet ; `rendre()` et `texte_attendu()` sont réutilisés par les tests. Sources : `#` titre, `##` sous-titre, `<<page>>` saut de page.
- Report de 2.2 : les Documents Markdown n'ont ni HTML brut (un `html_block` resterait brut dans un Block `text`) ni `<meta charset>` ; le Mini-corpus ne contient pas de HTML. Un test le vérifie. Le Parser n'est pas modifié.
- Écart de lecture : le contrat §4.1 écrit `docs/charte.md` en clé de `documents:`, et §4.7 écrit `target: docs/...`. Or `source_path` est relatif à `path` (ici `docs`). On écrit donc des `source_path` nus (`bulletin-maree.md`), acceptés par `declare` ; la story 2.6 devra lire `target` comme `source_path`, comme l'AC de 2.6 le dit.
- Les extras sont hors de `docs/` et ne sont jamais ingérés ; la sentinelle est absente des Documents (test).

## Tâches et critères

- [x] 18 à 22 Documents Markdown et PDF, `publishable`, CC-BY-4.0 : `test_declaration_et_effectif`.
- [x] Au moins deux Documents `en`, le reste `fr` : `test_langues`.
- [x] Long Document à trois niveaux, deux tableaux : `test_long_document_a_trois_niveaux_et_deux_tableaux`.
- [x] Groupe d'au moins quatre Documents liés par des entités : `test_groupe_de_documents_lies_par_entites`.
- [x] Deux versions contradictoires d'un même Document : `test_deux_versions_contradictoires`.
- [x] Régénération à l'identique des PDF, fpdf2 : `test_pdf_regeneres_a_l_identique`, `test_script_ecrit_les_pdf`.
- [x] Police TTF libre commitée avec sa licence ; « œ », « Œ », « », tirets rendus et ré-extraits : `test_police_libre_commitee_avec_licence`, `test_caracteres_francais_rendus_et_reextraits`.
- [x] Un PDF multipage, un PDF sans titre : `test_un_pdf_multipage_et_un_pdf_sans_titre`.
- [x] Moins de 60 000 tokens `approx`, au plus 40 000 mots : `test_sous_la_borne_de_tokens_de_reference`.
- [x] `scenario.yaml` avec `add`, `modify`, `delete`, sources existantes : `test_scenario_operations_et_sources`.
- [x] `extras/` : sentinelle et document piégé : `test_extras_hors_docs`.
- [x] Au moins deux Documents avec `rights_profiles` : `test_droits_sur_au_moins_deux_documents`.
- [x] Fixture `minicorpus` de session : `test_fixture_minicorpus_en_cache_de_session`.
- [x] Report 2.2 (HTML brut, `<meta charset>`) : `test_markdown_sans_html_brut_ni_meta_charset`.

## Auto Run Result

Suite complète (420 tests), pyright (0 erreur) et contrôle rapide verts à la livraison. Aucun fichier de la story 3.2 n'est touché.
