---
story: "8.1"
title: "Licences SPDX par liste blanche exacte"
status: done
---

# Story 8.1 : Licences SPDX par liste blanche exacte

Exigences : FR-5, NFR-4 ; AD-19 ; `contracts.md` §4.1 (arbitrage P5). Correctif de `corpus/declare.py` : la comparaison par préfixe laissait passer `cc-by-nc-*`.

## Réalisé

- `LICENCES_OUVERTES` devient un ensemble d'identifiants SPDX exacts (CC0-1.0, CC-BY-4.0, CC-BY-SA-4.0, MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ODbL-1.0, PDDL-1.0, etalab-2.0, LO-2.0), comparés sans casse et sans espaces de bord. `-NC`, `-ND`, `-NC-SA`, `cc-by` seul, `MIT-0` et toute valeur inconnue (`maison`) sont restrictives.
- Le refus pour un `path` suivi par git nomme la licence : « sous licence 'CC-BY-NC-4.0', restrictive ou inconnue (hors liste blanche SPDX) ». Un corpus restrictif hors dépôt ou ignoré par git reste utilisable (inchangé).
- Le refus de deux Documents identiques nommait déjà les deux fichiers ; le test l'affirme désormais.
- Mini-corpus (`corpora/minicorpus/corpus.yaml`, `CC-BY-4.0`) : passe la liste, aucune déclaration à corriger. Aucun autre corpus livré dans `corpora/`.

## Tests

`tests/unit/corpus/test_declare.py` : licences restrictives (refus dans le dépôt avec nom de la licence, accepté si ignoré), licences ouvertes (11 identifiants, variantes de casse et espaces), message de doublon avec les deux fichiers.

## Reports

Aucun.

## Revue

- medium, second avis 1 : corrigé. AC 2 couvert seulement pour `declare` dans un dossier ignoré ; ajout de `test_licence_restrictive_ignoree_ou_hors_depot_declaree_puis_ingeree` (`CC-BY-NC-4.0` hors dépôt puis ignoré : `declare` puis `ingest` réels).
- low, second avis 2 : corrigé au passage dans le même test (licence restrictive ignorée mais déjà suivie par git : refus qui nomme la licence) ; le chemin de code est commun avec `publishable: false`.
- low, second avis 3 : rejeté. La comparaison passe par `.lower()` sur les deux côtés, `CC-BY-4.0`/`cc-by-4.0` et `Etalab-2.0`/`etalab-2.0` couvrent déjà la casse ; vérifié `CC0-1.0` → ouverte.
- low, second avis 4 : rejeté. « CC BY 4.0 » n'est pas un identifiant SPDX ; le refus est fail-closed, conforme à l'AC (espaces de bord seulement) et à `contracts.md` §4.1, et le message nomme la licence.
- info, revue : `contracts.md` §4.1 correspond au code (liste blanche identique, refus seulement pour un `path` suivi par git) ; seul le Mini-corpus est livré (`CC-BY-4.0`), les fixtures de tests utilisent `CC-BY-4.0` ou `MIT`.
