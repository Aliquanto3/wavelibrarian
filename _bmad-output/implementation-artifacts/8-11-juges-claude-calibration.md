---
story: "8.11"
title: "Calibration des Juges Claude (Haiku 5.5 et Opus 5.5)"
status: review
---

# Story 8.11 : Calibration des Juges Claude

Exigences : FR-38 ; AD-14, AD-3. Dépend de 5.2 (`wl calibrer`) et 8.9 (annotations d'Anaël).

## Réalisé

- `defaults/models.yaml` : entrée `claude-opus-5-5` (tarifs relevés le 2026-10-26, aucun palier de long contexte), `catalog_date` au 2026-10-26. Supposés et non vérifiés en réel : `accepts_temperature: false`, `token_factor: "1.5"` (repris de Haiku 5.5), `min_cacheable_tokens: 4096` (sans effet sur les Juges, qui ne mettent rien en cache).
- `experiments/calibration-claude.yaml` : Juges `[claude-haiku-5-5, claude-opus-5-5]`, `panel_size: 2`, `calibration_passes: 2`, plafond Anthropic de 10,00 USD ; Corpus et Configurations de `mini-cpu` (`wl calibrer` n'en lit que le Corpus, les Questions, les Configurations, le Panel et le budget).
- Le chemin des Juges gérait déjà un Juge `provider: anthropic` : aucune correction de code. `tests/unit/runner/test_story_8_11.py` le démontre (SDK factice) : outil imposé, pas de `temperature`, coût exact par appel dans `traces.jsonl`, `BudgetExceeded` (code 3) sans rien écrire.

## Reports

- Opus 5.5 : thinking adaptatif toujours actif, facturé en sortie et compté dans `max_tokens`. Le Juge fixe `max_tokens = 200 × n_critères + 100` (700 pour 3 Critères) et le gateway ne transmet aucun réglage de thinking ni d'effort. Risques non vérifiables hors réseau : sortie tronquée avant l'outil, ou HTTP 400 (`tool_choice` imposé avec thinking). À constater au premier appel réel ; à traiter alors par une story dédiée.
- Un plafond atteint en cours de calibration perd tous les verdicts payés (rien n'est écrit) ; seules les passes 0 restent au Cache.
