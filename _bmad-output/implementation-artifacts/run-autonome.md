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
| 9.9 calibration d'Opus (354 appels) | 3,32 $ |
| 9.10 rejugement mini-cpu (72 appels, 47 du Cache) | 0,43 $ |
| Total | 3,75 $ / 10 $ |

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
- 2026-10-26 09:44 · 9.6+9.8 · CI · rouge : 1 failed (test_installer, double sans max_error_rate après refactor _conclure), 1319 passed · 
- 2026-10-26 09:44 · 9.6+9.8 · décision · double de test corrigé (test seul), test relancé vert · e48ac4f
- 2026-10-26 09:44 · 9.6 · fusion · fast-forward · 65acfc5
- 2026-10-26 09:44 · 9.8 · fusion · fast-forward · e48ac4f
- 2026-10-26 09:52 · 9.3 · dev · fini · 920da8f
- 2026-10-26 09:52 · 9.3 · second-avis · lancé · 
- 2026-10-26 09:52 · 9.4 · dev · lancé (Sonnet, depuis story/9-3) · 
- 2026-10-26 09:52 · 9.5 · dev · lancé (Sonnet, depuis story/9-3) · 
- 2026-10-26 09:52 · 9.5 · décision · bascule de mini-cpu et lazy-seuil-cpu sur Opus commitée par l'orchestrateur après la 9.9 (opus.json absent avant), pour garder main vert · 
- 2026-10-26 09:56 · 9.3 · second-avis · 2 medium (majorité sur les passes ; Exécutions v0.2.0 non corrigées sans rejugement), 3 low ; rien de high · 
- 2026-10-26 09:56 · 9.3 · décision · règle de majorité « voix confondues » gardée (passes: 1 livré), consignée ; anciennes Exécutions corrigées par wl rejuger seulement · 
- 2026-10-26 09:56 · 9.3 · review · lancé (Opus) · 
- 2026-10-26 10:00 · 9.5 · dev · fini (code ; bascule YAML après 9.9) · 6b88688
- 2026-10-26 10:00 · 9.5 · second-avis · lancé · 
- 2026-10-26 10:03 · 9.5 · second-avis · 1 medium (kappa exigé sur correctness même non jugé), 5 low ; rien de high · 
- 2026-10-26 10:03 · 9.5 · review · lancé (Opus) · 
- 2026-10-26 10:07 · 9.4 · dev · fini ; cible -50 % non atteinte (-4,7 % sur le run réel : les Passages n'étaient déjà pas répétés, la mesure de départ de l'epic était fausse) · 1d297e1
- 2026-10-26 10:07 · 9.4 · second-avis · lancé · 
- 2026-10-26 10:10 · 9.3 · review · 2 low corrigés (non jugés sans Corpus, tableau de contrats), comptes na au Rapport de calibration · 2ed872c
- 2026-10-26 10:11 · 9.4 · second-avis · 1 medium (verdict vidé non signalé), 6 low ; dédup des Passages possible seulement à contenu identique · 
- 2026-10-26 10:11 · 9.4 · décision · table de Passages partagée par contenu, aucune troncature ; écart à la cible -50 % soumis à Anaël en recette s'il reste · 
- 2026-10-26 10:11 · 9.4 · review · lancé (Opus) · 
- 2026-10-26 10:11 · 9.5 · review · 2 low corrigés (exclu en tête sauté, mention par Configuration), 3 Critères toujours exigés (validation sans Questions), contrats §4.4 · 251ff1b
- 2026-10-26 10:19 · 9.3 · fusion · suite complète 1348 passed (7 min 55), fast-forward · 2ed872c
- 2026-10-26 10:19 · 9.9 · décision · calibration-opus.yaml : Opus + Haiku (wl calibrer exige 2 Juges ; Haiku ~0,05 $), 5 passes, plafond 5 $ au lieu de 4 $ (A2) d'après le coût mesuré en 8.11 · 
- 2026-10-26 10:19 · 9.9 · dev · calibration réelle lancée (Opus + Haiku, 5 passes, run 20261018-115941-a2a512, sortie calibration-opus.json) · 
- 2026-10-26 10:25 · 9.4 · review · 3 Important corrigés (table de Passages : -56,2 % sur le run réel, cible atteinte ; verdict vidé signalé ; importer qui reportait sur la mauvaise ligne) · 4f3e029
- 2026-10-26 10:25 · 9.4 · review · passe 2 lancée (format du paquet changé) · 
- 2026-10-26 10:28 · 9.5 · fusion · suite complète 1368 passed (8 min 27), fast-forward ; bascule YAML après 9.9 · e3a2264
- 2026-10-26 10:32 · 9.4 · review · passe 2 : aucun Important, 2 Nit corrigés · f9327f8
- 2026-10-26 10:37 · 9.9 · décision · relancée avec uv run --extra energy (1er lancement arrêté au démarrage, sans appel : extra energy absent) · 
- 2026-10-26 10:37 · 9.9 · dev · fini : Opus 1,00 / 0,72 / 0,76 au-dessus du seuil ; 354 appels ; 3,32 $ · 
- 2026-10-26 10:37 · 9.5 · décision · bascule appliquée : mini-cpu et lazy-seuil-cpu en Juge unique Opus (opus.json), tests e2e et 8.7 réalignés · 
- 2026-10-26 10:38 · 9.10 · dev · rejugement réel lancé (wl rejuger 20261018-115941-a2a512, mini-cpu, Opus seul, plafond 3 $) · 
- 2026-10-26 10:38 · 9.11 · attente humaine · feu vert Ollama CPU demandé à Anaël (notification) · 
- 2026-10-26 10:41 · 9.10 · dev · fini : rejugement 20261026-093758-1afc6b completed, 72 Réponses, 0,43 $ (47 verdicts du Cache) ; IC recouvrants · 
- 2026-10-26 10:51 · 9.4 · fusion · suite complète 1406 passed (7 min 53) après rebase sur 9.9 et 9.10, fast-forward · 5d375a0
- 2026-10-26 10:51 · 9.12 · décision · préparée : paquet de 25 lignes (--depuis anael.yaml, graine 9), page, Expérience de calibration à 2 passes (minimum du schéma), consigne · 
- 2026-10-26 10:51 · 9.12 · attente humaine · second annotateur · 
