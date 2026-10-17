---
story: "2.5"
title: Mini-corpus fictif
status: done
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

- Contenu : 14 Documents français et 2 anglais en Markdown ; 4 PDF français dont `convention-douane.pdf` sur 3 pages et `lettre-torvane.pdf` sans titre. `atlas-vaelmor.md` a trois niveaux de titres et deux tableaux ; `charte-conseil-v1.md` (an 1290) et `charte-conseil-v2.md` (an 1413, qui remplace la première) sont deux Documents coexistants au même titre, aux valeurs contradictoires (quatre ou six ans, sept ou neuf sièges, séance le premier ou le quinze du mois) : c'est le cas temporel du PRD et du cadrage, distinct du `modify` du Scénario. Les Documents liés partagent « Compagnie des Marées Grises », « Oswin Dacrel » et « Maëlis Torvane » (7 Documents ; l'heuristique d'entités de 2.4 n'en voit que 3, d'où un comptage textuel dans le test).
- Taille : 4 361 mots, 4 247 tokens `approx`, bien sous les 60 000 tokens de référence. `atlas-vaelmor.md` fait 1 157 mots (environ 1 100 tokens, quatre Passages de 300 tokens pour l'epic 6). Les Paliers de 2.7 (5, 10, 20) tiennent dans les 20 Documents.
- PDF reproductibles : date de création fixée, donc sortie identique à l'octet ; `rendre()` et `texte_attendu()` sont réutilisés par les tests. Sources : `#` titre, `##` sous-titre, `<<page>>` saut de page.
- Report de 2.2 : les Documents Markdown n'ont ni HTML brut (un `html_block` resterait brut dans un Block `text`) ni `<meta charset>` ; le Mini-corpus ne contient pas de HTML. Un test le vérifie. Le Parser n'est pas modifié.
- Chemins : `source_path` est relatif à `path` (ici `docs`) ; clés de `documents:` et `target` du scénario s'écrivent nus (`bulletin-maree.md`). Les exemples de `contracts.md` §4.1 et §4.7 sont alignés (revue).
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

## Revue

Revue Opus en une passe, après rebase sur `main` (75db72b).

- medium, orchestrateur n° 1 : exemples de `contracts.md` §4.1 et §4.7 préfixés par `docs/` ; corrigé (`charte.md`, `target: charte.md`, ligne sur les chemins relatifs à `path`), `declare.py` inchangé.
- medium, second avis n° 2 : deux versions contradictoires ; intention confirmée (PRD, reconcile-cadrage : « bon pour les questions temporelles ») : deux Documents coexistants. Corpus gardé ; test et formulation corrigés (le test vérifie les mentions de remplacement, non « même titre = même Document »).
- medium, second avis n° 3 : Misty Gold « schooner » contre caboteur de 30 tonneaux ; corrigé (« coaster »). « Deux navires lancés » écarté : le Petit Sarnoux appartient aux sauniers, hors du registre (Compagnie et Conseil).
- medium, second avis n° 4 : courrier du Conseil porté par « les navires de la Compagnie » contre « seule la Grande Sève » ; corrigé dans `compagnie-marees-grises.md`.
- medium, revue : flotte de « onze navires » alors que le registre, dit complet, en liste quatre ; corrigé (quatre).
- medium, revue : anachronismes de 1412 citant la charte de 1413 (`atlas-vaelmor.md`, `convention-douane` art. 6) ; corrigé, PDF régénéré par le script (seul `convention-douane.pdf` change).
- low, second avis n° 5 : séance le quinze dans le guide anglais de 1412, sous la charte de 1290 (le premier du mois) ; corrigé dans le guide. L'écart entre v1 et v2 reste voulu.
- low, revue : « pêcheurs de la Compagnie » (Compagnie de transport) et « barques de l'Écume Bleue » (une seule barque) ; corrigés.
- low, second avis n° 6 : Maëlis Torvane dans 7 Documents ; spec et test mis à jour (comptage textuel, l'heuristique de 2.4 la manque en début de phrase).
- low, second avis n° 7 : PDF sans titre testé sur les sources ; corrigé, le test mesure le corps de caractère des PDF ingérés (pypdfium2) : seul `lettre-torvane.pdf` reste sous 12 points.
- low, second avis n° 8 : bornes de taille larges ; écarté, l'AC ne fixe qu'un plafond (60 000 tokens, 40 000 mots).
- low, second avis n° 9 : long Document de 622 mots ; corrigé, `atlas-vaelmor.md` porté à 1 157 mots (sections Navigation et Société, troisième tableau), soit quatre Passages de 300 tokens. Les Paliers de 2.7 portent sur des effectifs (5, 10, 20), déjà tenus.
- low, second avis n° 10 : docstring « profil `test` » de la fixture inexacte (l'ingestion ne lit aucun profil) ; corrigée.
- low, second avis n° 11 : test de cache tautologique (`getfixturevalue` dans le même test) ; corrigé, deux tests paramétrés comparent l'objet reçu.
- low, second avis n° 12 : fpdf2 seulement en dépendance `dev` ; écarté, seul le script de régénération l'importe, et `uv sync` installe le groupe `dev` par défaut (le dépôt n'a pas encore de CI).
