# Run autonome du lot v0.3.0 (epic 9)

Fichier tenu par l'orchestrateur. Après `/clear` : relire ce fichier, `epic-9-context.md`, puis `sprint-status.yaml`. Une story `in-progress` sans commit d'intégration reprend depuis sa spec et son worktree. Proposition approuvée : `planning-artifacts/sprint-change-proposal-2026-10-26.md` (A1 à A10 en bloc).

## Périmètre

| Périmètre | Epics | Note |
| --- | --- | --- |
| Dans le run | Epics 9 à 9 | Stories 9.1 à 9.11 |
| Hors run | Epics 9 à 9 | 9.12 (humaine) : préparée seulement |

Au plus 2 stories en développement à la fois.

## Consignes

- Par story : `agent-cost-kit:dev-story` (Sonnet ; Opus pour 9.3 et 9.6) → `second-avis` → `reviewer` (avec la liste du second avis, rebasé avant de juger) → intégration sur `main` (rebase, suite complète, `ruff`, `pyright`, contrôle rapide). Appels bloquants.
- Ollama et GPU : rien sans accord écrit d'Anaël dans la session ; 9.11 attend ce feu vert (notification), le run avance en attendant.
- API : plafond total du lot 10 USD ; dépense tenue ci-dessous.
- Push de `main` en fin d'epic ; topic GitHub `status-dev` au démarrage ; pas de release v0.3.0 avant la recette d'Anaël.
- Fin : notifier Anaël avec un guide de recette court.

## Dépense API du lot

| Étape | Dépense |
| --- | --- |
| Total | 0 $ / 10 $ |

## Sprint 1 — Epic 9 (v0.3.0)

| Vague | Stories en parallèle | Après |
| --- | --- | --- |
| V0 | 9.1 · 9.7 | |
| V1 | 9.2 · 9.8 | |
| V2 | 9.3 ★ · 9.6 | 9.3 ← 9.1 ; 9.3 ← 9.2 |
| V3 | 9.4 · 9.5 ★ | 9.4 ← 9.3 ; 9.5 ← 9.3 |
| V4 | 9.9 (mixte) | 9.9 ← 9.1 ; 9.9 ← 9.2 ; 9.9 ← 9.3 |
| V5 | 9.10 (mixte) · 9.11 (mixte) | 9.10 ← 9.5 ; 9.10 ← 9.6 ; 9.10 ← 9.9 ; 9.11 ← 9.5 ; 9.11 ← 9.7 ; 9.11 ← 9.9 |
| V6 | 9.12 (humaine) | 9.12 ← 9.4 |

Fichiers par vague : V0 `scoring/calibration.py` + `cli.py` (calibrer) / `components/deciders`, `llm/cache.py`, schéma d'Expérience ; V1 `components/judges`, `llm/roles.py` / `measure/energy.py`, runner (phase judging), `report/couts.py`, profils ; V2 transverse 9.3 / nouveau module de rejugement 9.6 (rebase attendu sur `scoring/panel.py`) ; V3 `report/paquet.py`, `cli.py` (annotations) / `config/validate.py`, `experiments/`.

## Journal

- 2026-10-26 08:16 · lot · décision · Anaël : Opus Juge principal (série du 26/10)
- 2026-10-26 08:45 · lot · décision · proposition epic 9 approuvée (« OK en bloc », A1 à A10) ; PRD (FR-32, FR-36, FR-37, FR-38) et AD-14, AD-17 amendés ; sprint-status à jour
