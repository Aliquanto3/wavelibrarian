---
story: "8.1"
title: "Licences SPDX par liste blanche exacte"
status: review
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
