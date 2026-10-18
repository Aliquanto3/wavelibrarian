# Epic 8 Context: Résultats réels fiables (lot v0.2.0)

<!-- Compilé une fois au début du run v0.2.0 (2026-10-18). Sources : epics.md l. 2002-2255, epics-1-7-retro-2026-10-18.md, sprint-change-proposal-2026-10-18.md. -->

## Goal

Anaël obtient d'un run réel un statut, des coûts et une calibration auxquels il peut se fier, et les 4 Configurations CPU de `experiments/mini-cpu.yaml` tournent sans erreur sur tout le split dev (19 Questions). L'epic reprend les items A à H de la rétro et les arbitrages P1 à P9 (déjà reportés dans `epics.md` stories 1.4, 1.8, 7.5 et dans `contracts.md`).

## Stories (ordre imposé)

| Story | Item rétro | Lignes dans `epics.md` | Réseau |
|---|---|---|---|
| 8.1 Licences SPDX par liste blanche exacte | F (P5) | 2011-2037 | non |
| 8.2 Coûts factices hors du coût réel | B (L2) | 2038-2060 | SM-4 `real_api` (plafond 5 $) |
| 8.3 Statut `completed_with_errors` de `wl run` | A (L1, P9) | 2061-2093 | non |
| 8.4 `think` par modèle au Catalogue | G (P7) | 2094-2116 | vérif. réelle Ollama en attente |
| 8.5 Alignements de spec Catalogue / Registre | H (P1, P2) | 2117-2138 | WebFetch page de prix |
| 8.6 Énergie CPU mesurée sous Windows | E (P4) | 2139-2164 | non (charge CPU locale) |
| 8.7 Modèle CPU de sélection pour PageIndex | D (L4) | 2165-2186 | Ollama |
| 8.8 Run mini-cpu split dev + seuil LazyGraphRAG | P8 | 2187-2210 | Ollama |
| 8.9 Paquet d'annotation et kappas au Rapport | C (1), (4) | 2211-2233 | non (code) ; paquet réel après 8.8 |
| 8.10 Calibration réelle des Juges Ollama | C (2), (3), (5) | 2234-2255 | hors run (annotations d'Anaël) |

## Règles communes

- Toute story qui écrit un test `real_*` l'exécute au moins une fois avant `done`, ou le marque « en attente » dans le sprint status avec la raison.
- Chaque exemple chiffré d'un AC est recalculé contre la règle qu'il illustre ; une contradiction est signalée, pas tranchée seul.
- Un test réel par rôle à sortie structurée (Juge, Generator, sélection) sur le plus petit modèle local du profil, dans `real_local` (action 5 de la rétro).

## Décisions d'Anaël (P1 à P9, 2026-10-18)

- P1 : palier ×5 gardé (1 M + 1 M → 3,00 $, 50 000 + 50 000 → 0,03 $ pour `claude-haiku-5-5`).
- P2 : test 1.8 = 0,90 + 0,90, 0,10 acceptée, 0,30 refusée sous 2,00 $, acceptée le mois suivant.
- P4 : `windows_emi` → `measured` seulement s'il suit la charge ; `wl.energy_source` toujours écrit.
- P5 : liste blanche SPDX exacte (CC0-1.0, CC-BY-4.0, CC-BY-SA-4.0, MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ODbL-1.0, PDDL-1.0, etalab-2.0, LO-2.0), sans casse ni espaces de bord.
- P7 : `ModelEntry.think: bool | None = False`.
- P8 : `relevance_threshold` reste 0,1 jusqu'à la mesure ; changement sur décision d'Anaël.
- P9 : `completed_with_errors`, code 1, `--tolerer-erreurs`, `max_error_rate` = 0,2 (hors [0, 1] → code 2).

## Contrats touchés (`planning-artifacts/architecture/architecture-wavelibrarian-2026-10-17/contracts.md`)

§4.1 licences, §4.2 `ModelEntry.think`, §5 `manifest.json` (`completed_with_errors`, causes, `max_error_rate`), §6 spans (`wl.energy_source`, coûts), §7 fronts, §8 codes de sortie et `--tolerer-erreurs` ; 8.9 ajoute la commande d'export au §8 ; §4.6 format des annotations.

## Points de code connus

- `corpus/declare.py:119` (préfixes de licence), `report/couts.py:186` (somme `wl.cost`), `runner/execute.py:75,910-929` (`RunStatus`), `runner/rundir.py` (`Status`), `runner/resume.py:125` (`deja_terminee`), `report/generer.py:144` (`_bandeau`), `llm/providers/ollama.py:154` (`think: False`), `measure/energy.py:23` (`_MODES_MATERIELS`), `architectures/pageindex.py:144-145` (`select_max_tokens`), `config/resolve.py` (`answer_producer`), `tests/unit/llm/test_ledger_cache.py:72`, `tests/unit/config/test_catalog.py`, `cli.py:224-270` (`wl calibrer`).
- Modèle à suivre pour `think` : `accepts_temperature` (story 4.15), clé de cache sur la valeur effective.

## Contraintes du run

- Tests sans réseau (Faux LLM `fake-llm-a/b/c`, faux embedder dim 64, profil `test`) ; pas de pytest parallèle.
- Ollama : rien au-delà de `/api/version`, `/api/ps`, `/api/tags` sans « Ollama disponible » d'Anaël ; ensuite profil `cpu`, `num_gpu: 0`, `CUDA_VISIBLE_DEVICES=-1`.
- API Anthropic : seulement SM-4 (8.2), plafond 5 $ ; toute dépense > 1 $ soumise à Anaël.
- Non décidable seul : valeurs par défaut (`relevance_threshold`, prix/palier du Catalogue, options PageIndex hors AC), modification d'AC.
- Vider `WL_HOME` (Cache de réponses) après une mise à jour d'un provider (L8).
