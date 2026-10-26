# Epic 9 Context: Juge calibré et scores de qualité fiables (lot v0.3.0)

<!-- Compilé au début du run v0.3.0 (2026-10-26). Sources : epics.md l. 2276-2580, sprint-change-proposal-2026-10-26.md (approuvée, A1 à A10), verifications-reelles-2026-10-26-v0.2.0.md. -->

## Goal

Scores de qualité jugés par `claude-opus-5-5`, Juge unique calibré ; modalité « sans objet » ; justification courte ; calibration écrite au fil de l'eau ; paquet et page d'annotation dans le code ; rejugement sans Ollama ; balayage LazyGraphRAG refait ; énergie `mixed`, `judging`, GPU.

## Stories

| Story | Lignes `epics.md` | Réseau | Dev |
|---|---|---|---|
| 9.1 Verdicts de `wl calibrer` au fil de l'eau | 2286-2312 | non | Sonnet |
| 9.2 Justification courte des Juges | 2313-2338 | non | Sonnet |
| 9.3 Modalité « sans objet » | 2339-2376 | non | Opus |
| 9.4 Paquet et page d'annotation | 2377-2407 | non | Sonnet |
| 9.5 Juge unique calibré, Opus dans les Expériences | 2408-2435 | non | Sonnet |
| 9.6 `wl rejuger` | 2436-2463 | non | Opus |
| 9.7 Decider LazyGraphRAG, Cache isolé | 2464-2486 | non | Sonnet |
| 9.8 Énergie mixed, judging, GPU | 2487-2513 | non | Sonnet |
| 9.9 Calibration réelle d'Opus | 2514-2531 | API (~2,5 $) | orchestrateur |
| 9.10 Rejugement réel mini-cpu | 2532-2546 | API (~1 $) | orchestrateur |
| 9.11 Balayage réel du seuil | 2547-2561 | Ollama CPU (accord) + API | orchestrateur |
| 9.12 Double annotation | 2562-2580 | humaine | hors run |

## Contrats partagés (décidés au départ, à respecter mot pour mot)

- Verdict : `Literal["yes", "no", "na"]` ; `na` = sans objet. Constante `VERDICTS` du chargeur d'annotations étendue (9.3).
- Justification : constante `JUSTIFICATION_MAX = 200` (caractères) dans `llm/roles.py` (9.2) ; troncature avec « … ».
- Calibration au fil de l'eau (9.1) : `<sortie>_verdicts.jsonl`, une ligne JSON par (Juge, `answer_id`, `pass_id`), écrite et vidée (`flush` + `os.fsync`) à réception ; options `wl calibrer --reprendre` et `--ecraser`.
- Juge unique (9.5) : `judges.panel_size: 1` admis seulement avec `judges.excluded_from` (fichier de calibration) où le Juge passe `kappa_threshold` sur chaque Critère. Fichier versionné : `corpora/minicorpus/calibration/opus.json` (produit par 9.9 ; 9.5 le référence, et ses tests utilisent un fichier de calibration factice).
- Rejugement (9.6) : `wl rejuger <run_id> <experience.yaml>` ; manifeste `rejudged_from: <run_id>`.
- Cache (9.7) : champ d'Expérience `llm_cache: {isoler_configurations: bool}` (défaut `false`, clés inchangées).
- Énergie (9.8) : `EnergyMethod = Literal["measured", "mixed", "estimated", "unknown"]` ; phase d'énergie `judging` ; champ de profil `energy: {gpu: bool}` (défaut `false`, `true` dans `gpu.yaml`).
- Annotations (9.4) : `wl annotations page <paquet.yaml> --vers <page.html>`, `wl annotations importer <paquet.yaml> <verdicts.json>`, `wl annotations exporter ... --depuis <paquet annoté>`.

## Règles du run

- Tests sans réseau (Faux LLM, profil `test`), ciblés pendant le dev ; suite complète une fois avant intégration (orchestrateur).
- Ollama et GPU : aucun appel (pas même `/api/tags`) sans accord écrit d'Anaël dans la session.
- API Anthropic : seulement les stories réelles 9.9 à 9.11 et les vérifications de revue ; plafond total du lot 10 USD.
- Non décidable seul : valeur par défaut hors arbitrages A1 à A10, modification d'AC, dépassement de budget.
- Chaque story met à jour les sections de `contracts.md` qu'elle touche et écrit sa spec `implementation-artifacts/9-N-<slug>.md` (Réalisé, Reports, Revue).
- `uv run python`, jamais `python` nu ; lint `uv run ruff check .`, `uv run pyright`, contrôle rapide `py .claude/cost-kit/controle_rapide.py`.

## Points de code connus

`scoring/calibration.py` (VERDICTS l. ~102, kappa, `fiches_du_juge`), `cli.py:240` (`calibrer`), `components/judges/llm.py:15` (`_SYSTEM`, budget `200 × n + 100`), `llm/roles.py:26` (`verdict: Literal["yes","no"]`), `scoring/panel.py`, `config/validate.py:144` (Panel admissible), `config/resolve.py:295`, `components/deciders/llm.py:14` (`SYSTEM`), `llm/cache.py:25` (`cache_key`), `measure/energy.py` (`EnergyMethod`, `CodecarbonMeter`, `_retirer_gpu`), `report/paquet.py` (export), `report/couts.py`, `report/generer.py`, `scripts/page_annotation.py`, `scripts/importer_verdicts.py`, `runner/resume.py`, `runner/rundir.py`.
