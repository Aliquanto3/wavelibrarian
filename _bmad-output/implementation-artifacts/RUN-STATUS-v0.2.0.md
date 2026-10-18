# RUN-STATUS v0.2.0 - run autonome de l'epic 8

Fichier tenu par l'orchestrateur. Après `/clear`, relire ce fichier puis `sprint-status.yaml` ; une story `in-progress` sans commit d'intégration reprend depuis son fichier de story et son worktree. Contexte de l'epic : `epic-8-context.md`.

## Consignes

- Par story : `agent-cost-kit:dev-story` (Sonnet ; Opus pour 8.3) → `second-avis` → `reviewer` (avec la liste du second avis) → intégration sur `main`. Appels bloquants, une passe de revue, une voie. Suite complète + `py .claude/cost-kit/controle_rapide.py` avant chaque intégration.
- Ollama : rien au-delà de `/api/version`, `/api/ps`, `/api/tags`, ni `ollama`, ni `pytest -m real_local`, ni `wl run` réel, tant qu'Anaël n'a pas écrit « Ollama disponible ». Ensuite : `/api/tags`, profil `cpu`, `num_gpu: 0`, `CUDA_VISIBLE_DEVICES=-1`.
- Non décidable seul : valeur par défaut (`relevance_threshold`, prix/palier du Catalogue, option PageIndex hors AC), dépense > 1 $, modification d'AC → « À arbitrer par Anaël » + notification, puis continuer.
- Sonnet en échec deux fois sur une story → reprise avec Opus.
- Ordre : 8.1, 8.2 (SM-4 real_api, plafond 5 $), 8.3, 8.4 (code ; vérif. réelle en attente), 8.5 (WebFetch prix), 8.6 (charge CPU ≤ 4 threads), 8.7 (Ollama → notifier ; pendant l'attente, code de 8.9) ; après « Ollama disponible » : vérif. 8.4, 8.7, 8.8, paquet 8.9 depuis le run_id de 8.8. 8.10 : ne pas toucher. Fin : notifier avec le chemin du paquet, pousser `main`.

## État

| Champ | Valeur |
| --- | --- |
| Mis à jour | 2026-10-18 |
| Story en cours | 8.1 |
| Stories livrées | 0 / 9 (8.10 hors run) |
| Dépense Anthropic | 0,00 $ / plafond 5 $ |
| Ollama | **non disponible** (attendre « Ollama disponible » d'Anaël) |
| Attentes envers Anaël | aucune |
| À arbitrer par Anaël | aucun |

## Stories livrées

| Story | Début | Fin | Commit d'intégration | Dépense | Notes |
| --- | --- | --- | --- | --- | --- |

## Reports entre stories

À transmettre au dev-story de la story cible.

## Journal

- 2026-10-18 : artefacts de planification commités (`ab2181f`) ; `epic-8-context.md` compilé ; démarrage du run.
