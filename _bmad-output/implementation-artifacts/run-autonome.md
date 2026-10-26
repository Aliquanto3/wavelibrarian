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
- 2026-10-26 08:47 · 9.1 · dev · lancé (Sonnet, story/9-1) · 
- 2026-10-26 08:47 · 9.7 · dev · lancé (Sonnet, story/9-7) · 
- 2026-10-26 08:57 · 9.7 · dev · fini · 2c7529d
- 2026-10-26 08:57 · 9.2 · dev · lancé (Sonnet, story/9-2) · 
- 2026-10-26 08:57 · 9.1 · dev · fini · 15d2d1c
- 2026-10-26 08:57 · 9.8 · dev · lancé (Sonnet, story/9-8) · 
- 2026-10-26 08:57 · 9.7 · second-avis · 1 medium (empreinte changée par llm_cache à false), 9 low · 
- 2026-10-26 08:57 · 9.7 · décision · isolation du Cache limitée aux appels de la Configuration (pas Juges, calibration, closed-book) · 
- 2026-10-26 08:58 · 9.7 · review · lancé (Opus) · 
- 2026-10-26 08:58 · 9.2 · dev · fini · 31b08db
- 2026-10-26 08:58 · 9.6 · dev · lancé (Opus, story/9-6, en avance sur V2 : aucune dépendance de code) · 
- 2026-10-26 08:59 · 9.1 · second-avis · 2 medium (empreinte sans prompt des Juges ; per_run neuf à la reprise), 8 low · 
- 2026-10-26 08:59 · 9.1 · review · lancé (Opus) · 
- 2026-10-26 09:01 · 9.2 · second-avis · 2 medium (test ne reproduit pas la coupure réelle ; délibération hors outil chez Opus), 6 low · 
- 2026-10-26 09:01 · 9.2 · review · lancé (Opus) · 
- 2026-10-26 09:08 · 9.2 · review · 1 medium corrigé (test honnête + borne de budget), troncature mesurable (wl.justification_truncated) · 3436cb7
- 2026-10-26 09:11 · 9.7 · review · 1 medium corrigé (llm_cache par défaut hors empreinte), isolation limitée au poste query · 51cf87a
- 2026-10-26 09:15 · 9.6 · dev · fini · 51a38f7
- 2026-10-26 09:15 · 9.6 · second-avis · lancé (vérifie le cas réel de la 9.10 : Catalogue et date différents de la source) · 
- 2026-10-26 09:16 · 9.8 · dev · fini · d3a5ed1
- 2026-10-26 09:16 · 9.8 · second-avis · lancé · 
- 2026-10-26 09:17 · 9.1 · review · 2 medium corrigés (empreinte = requêtes des Juges ; calibration_id réutilisé à la reprise), 8 low · c151fbc
- 2026-10-26 09:19 · 9.6 · second-avis · 1 high confirmé (cas 9.10 refusé : catalog_date, models_frozen_at), 2 medium, 6 low · 
- 2026-10-26 09:19 · 9.6 · review · lancé (Opus) · 
- 2026-10-26 09:21 · 9.8 · second-avis · 4 medium (règle measured/mixed incohérente avec GPU, GPU 0 en dur, judging couvre les attentes d'API, énergie répartie sur des hits), 6 low · 
- 2026-10-26 09:21 · 9.8 · décision · measured seulement si toutes les parts suivies sont mesurées, sinon mixed (cohérence A8) ; AC 3 réécrit · 
- 2026-10-26 09:21 · 9.8 · review · lancé (Opus) · 
- 2026-10-26 09:22 · 9.2 · fusion · suite complète 1260 passed (13 min 45), fast-forward sur main · 3436cb7
- 2026-10-26 09:22 · 9.7+9.1 · décision · pile 9.7 puis 9.1 rebasée sur main, une suite complète pour la pile · 
- 2026-10-26 09:22 · 9.3 · dev · lancé (Opus, story/9-3 depuis la pile ef72d47) · 
- 2026-10-26 09:29 · 9.6 · review · 1 high corrigé (Catalogue, date et chemins), contenu du Jeu vérifié par le Gel ; sonde sur la source réelle : acceptée, 76/76 ok · 3a5e104
- 2026-10-26 09:30 · 9.8 · review · 4 medium corrigés (règle mixed, GPU visibles, pas d'énergie sur les hits, lignes de contrats 9.2 restaurées) · 2a83b26
- 2026-10-26 09:33 · 9.7 · fusion · suite complète de la pile 1285 passed (10 min 20), fast-forward · 05eb5b5
- 2026-10-26 09:33 · 9.1 · fusion · même pile · a9819d0
- 2026-10-26 09:33 · 9.6+9.8 · décision · pile 9.6 puis 9.8 rebasée sur main (sans conflit), une suite complète · 
