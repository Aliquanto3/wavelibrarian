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

- Opus 5.5 : risques thinking et `tool_choice` constatés et traités en revue (voir `## Revue`).
- Un plafond atteint en cours de calibration perd tous les verdicts payés (rien n'est écrit) ; seules les passes 0 restent au Cache.

## Revue

### Passe 1 (2026-10-26, SHA revu 7d951d3)

Rebase : branche déjà à jour sur `main` (56b7855).

Appels réels à l'API (`claude-opus-5-5`, requête du Juge, 3 Critères, ~1 050 tokens d'entrée), coût total ≈ 0,008 USD :
1. `tool_choice: {type: tool}`, `max_tokens` 700 : **HTTP 400** « tool_choice: type "tool" and "any" are not supported for this model » (non facturé).
2. `tool_choice: auto`, `temperature: 0` : **HTTP 400** « `temperature` is deprecated for this model » (non facturé ; confirme `accepts_temperature: false`).
3. Requête corrigée par le provider (`tool_choice: auto` + consigne, sans `temperature`, `max_tokens` 4 700) : **200**, `stop_reason: tool_use`, entrée 1 051, sortie 212 tokens, un seul bloc `tool_use` (aucun bloc `thinking` visible), sortie conforme au schéma.

- Important, high, second avis 1 : `calibration_verdicts.jsonl` écrit en dur dans l'Exécution quel que soit `--sortie` (collision avec la calibration Ollama en parallèle). Corrigé : verdicts dans `<nom de --sortie>_verdicts.jsonl` (`fichier_verdicts`), défaut inchangé ; seul `calibration.json` est lu par le Rapport.
- Important, high, second avis 2 : réponse sans bloc `tool_use` → `ProviderError` non attrapée, calibration perdue (code 4) et coût tracé à 0. Corrigé : le provider rend le texte et l'usage ; la passerelle trace le coût, juge non conforme, fait un nouvel essai puis la calibration consigne un verdict manquant.
- Important, high, second avis 3 : confirmé en réel (HTTP 400 sur `tool_choice` imposé). Corrigé : champ de Catalogue `forced_tool_choice` (false pour Opus 5.5), porté par `LLMRequest.forced_tool` (dans la clé de Cache seulement si false : clés Haiku inchangées), `tool_choice: auto` + consigne d'outil.
- Important, medium, second avis 4 : thinking compté dans `max_tokens`. Corrigé par précaution : `thinking_reserve_tokens: 4000` au Catalogue pour Opus, ajouté au budget du Juge (700 → 4 700). L'appel 3 n'a pas pensé (212 tokens), la réserve couvre les items plus durs ; une troncature éventuelle n'est plus fatale (point 2).
- Nit, medium, second avis 5 : passes ≥ 1 hors Cache, chaque relance repaie. Rejeté : voulu (chaque passe va au fournisseur).
- Important, medium, second avis 6 : `--sortie` vers un dossier absent → échec après les appels payés. Corrigé : dossier parent créé avant tout appel (`ConfigError` code 2 si impossible).
- Important, medium, second avis 7 : coût tracé à 0 quand le provider lève après une réponse payée. Corrigé pour le seul cas existant (réponse sans outil, point 2).
- Important, medium, second avis 8 : tests manquants. Corrigé : SDK factice qui reprend les deux refus HTTP 400 réels d'Opus, test de réponse sans outil (verdict manquant, coût compté, calibration écrite), test de deux `--sortie` sans écrasement avec dossier créé, tests provider (`tool_choice: auto`, texte rendu sans outil). Pas de test CLI (le provider n'est pas injectable par la CLI ; la CLI ne fait que passer `--sortie`).
- Nit, low, second avis 9-10 : sans action.
- Nit, low, revue : le double de Catalogue de `test_story_5_2.py` (`SimpleNamespace`) a dû recevoir `thinking_reserve_tokens` ; double interne au projet, gardé tel quel.
- Pre-existing, medium, revue : une `ProviderError` non réessayable (4xx inattendu) ou `BudgetExceeded` en cours de calibration perd tous les verdicts payés (rien n'est écrit). Reporté : à traiter par une écriture incrémentale des verdicts.
- Complexité : 0 constat (listes de verdicts parcourues une fois ; rapprochement Critère × annotations négligeable à 92 lignes).

Commande de la calibration réelle (depuis la racine du dépôt principal, où se trouve `.env`), `calibration.json` de l'Exécution laissé à la calibration Ollama :
`WL_HOME=C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0 uv run wl calibrer experiments/calibration-claude.yaml --annotations corpora/minicorpus/annotations --run 20261018-115941-a2a512 --sortie C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0/runs/20261018-115941-a2a512/calibration-claude.json`
→ verdicts dans `calibration-claude_verdicts.jsonl` du même dossier.
