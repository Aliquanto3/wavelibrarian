---
story: "9.12"
title: "Double annotation partielle (humaine, hors run)"
status: ready-for-dev
---

# Story 9.12 : double annotation partielle (humaine)

Exigences : FR-38, SM-5. Story humaine, préparée par l'orchestrateur après la 9.4.

## Préparé

- `corpora/minicorpus/annotations-a-faire/` : `annotateur2.yaml` (25 lignes tirées de `anael.yaml`, stratifiées par Critère : 11 completeness, 3 correctness, 11 faithfulness ; 21 Réponses ; aucune q-044), `annotateur2.html` (page autonome), `calibration-inter-annotateurs.yaml` (2 passes, ~0,70 USD, plafond 1,00 USD), `LISEZMOI.md` (consigne et commandes d'import et de calibration).

## Reste à faire (humain)

- Un second annotateur remplit la page et exporte ses verdicts ; Anaël importe, copie le paquet dans `annotations/` et lance la calibration (commandes dans `LISEZMOI.md`).
