---
story: "9.2"
title: "Justification courte des Juges"
status: review
---

# Story 9.2 : Justification courte des Juges

Exigences : FR-36 ; AD-14. Constat 8.8 (b) : 7 sorties tronquées au budget par une `justification` qui délibère (arbitrage B1).

## Réalisé

- `llm/roles.py` : constante `JUSTIFICATION_MAX = 200`. `CriterionVerdict.justification` porte `Field(max_length=200)` (donc `maxLength: 200` dans le schéma émis) et un `BeforeValidator` (`tronquer_justification`) qui tronque à 200 caractères au plus, « … » compris, avant la contrainte : une justification trop longue n'est jamais non conforme (Anthropic, Fake, tout provider sans grammaire). `verdict` reste avant `justification` dans l'ordre des propriétés ; type `Literal["yes","no"]` inchangé (la 9.3 ajoutera `na`).
- `components/judges/llm.py` : prompt système « décide d'abord (yes ou no), puis une justification d'une seule phrase de 200 caractères au plus, sans délibération ni hésitation ».
- Ollama : le schéma part déjà dans `format` (`inline_refs` conserve `maxLength`) ; la grammaire borne la longueur.
- `contracts.md` §3 : sortie du rôle `judge` annotée (≤ 200 car.).
- Tests : `tests/unit/components/test_llm_judge.py` (prompt, bornes exactes 200/201, rejeu des 3 cas 8.8 q-044 rag-naif et raptor, q-017 pageindex avec un Faux LLM à justification de ~1300 caractères : aucun `NonConformantOutput`, un seul appel), `tests/unit/llm/test_providers.py` (corps Ollama : `format` avec `maxLength` et ordre `verdict`, `justification` ; outil Anthropic : idem).

## Reports

- Cache des Juges : le prompt système change, donc les clés du Cache de réponses des Juges changent ; les verdicts précédemment cachés ne sont plus servis (à refaire, y compris les calibrations).
- Le budget de sortie (`200 × n + 100`) n'est pas revu ; à réévaluer sur un run réel (mesure hors périmètre, sans Ollama ici).
- Aucune vérification réelle (Ollama/API) : l'effet sur les 7 troncatures n'est démontré qu'avec un Faux LLM.

## Commande de vérification

`uv run pytest -q --tb=short tests/unit/components/test_llm_judge.py tests/unit/llm tests/unit/scoring tests/unit/runner/test_story_8_11.py tests/unit/runner/test_story_5_2.py`
