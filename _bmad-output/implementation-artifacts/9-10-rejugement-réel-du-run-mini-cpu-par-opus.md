---
story: "9.10"
title: "Rejugement réel du run mini-cpu par Opus"
status: done
---

# Story 9.10 : rejugement réel du run mini-cpu par Opus

Exigences : FR-36, FR-39, FR-40, SM-5. Story réelle (API Anthropic), menée par l'orchestrateur après 9.5, 9.6 et 9.9.

## Réalisé

- `wl rejuger 20261018-115941-a2a512 experiments/mini-cpu.yaml` (Opus Juge unique) : Exécution `20261026-093758-1afc6b`, `completed`, 18 Questions dev, 72 Réponses, 0 Critère sans verdict, 0,43 USD (47 verdicts sur 72 servis par le Cache de la calibration 9.9), 1 min 13, sans Ollama.
- Scores par Configuration avec IC, `na`, comparaison aux Juges granite et qwen de la 8.8, coût et durée : `verifications-reelles-2026-10-26-v0.3.0.md` (b).

## Reports

- Aucune Configuration séparable sur 18 Questions (McNemar p = 1,00) : plus de Questions ou un Generator plus capable pour classer les Architectures.
- Énergie et latence de génération copiées de la source (étiquette `nvml` erronée d'avant fix-8-8).
