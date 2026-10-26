---
story: "9.9"
title: "Calibration réelle d'Opus avec le prompt du lot"
status: done
---

# Story 9.9 : calibration réelle d'Opus

Exigences : FR-38, SM-5 ; AD-14. Story réelle (API Anthropic), menée par l'orchestrateur après 9.1, 9.2 et 9.3.

## Réalisé

- `experiments/calibration-opus.yaml` : Juges `claude-opus-5-5` et `claude-haiku-5-5` (`wl calibrer` exige 2 Juges admissibles), 5 passes, plafond 5,00 USD (au lieu de 4,00 USD en A2 : coût mesuré en 8.11 ~0,65 USD par passe d'Opus).
- Calibration réelle sur `20261018-115941-a2a512` : Opus 1,00 / 0,72 / 0,76 (correctness / completeness / faithfulness), au-dessus du seuil ; 3,32 USD. Détail : `verifications-reelles-2026-10-26-v0.3.0.md` (a).
- `corpora/minicorpus/calibration/opus.json` versionné ; bascule de la story 9.5 appliquée : `mini-cpu.yaml` et `lazy-seuil-cpu.yaml` en Juge unique `claude-opus-5-5`, `excluded_from` vers ce fichier, plafonds 3,00 et 2,00 USD ; validation sans réseau verte.
- Tests réalignés : `tests/e2e/test_experiences_livrees.py` (mini-cpu jugée par Opus seul, sous plafond), `tests/unit/test_story_8_7.py` (la règle AD-14 sur `select_model` reste testée sur une copie de mini-cpu au réservoir local de la 8.7).

## Reports

- 5 désaccords `na` d'Opus en fidélité (Réponses non vides jugées sans objet, annotées oui ou non) : à revoir par Anaël en recette.
- Les commandes réelles demandent `uv run --extra energy` (sinon arrêt au démarrage, sans appel).
