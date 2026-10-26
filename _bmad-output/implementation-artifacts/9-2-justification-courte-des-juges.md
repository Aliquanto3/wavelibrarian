---
story: "9.2"
title: "Justification courte des Juges"
status: done
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
- Aucune vérification réelle (Ollama/API) : l'effet sur les 7 troncatures n'est démontré qu'avec un Faux LLM. Ce que prouvent les tests : une justification longue dans un JSON complet est tronquée et reste conforme (cas Anthropic, sans grammaire) ; côté Ollama, la grammaire `maxLength` borne la justification, et un calcul de borne montre que la plus longue sortie conforme compacte tient dans `200 × n + 100` tokens même à 1,5 caractère par token. La panne réelle de la 8.8 (coupure au budget, JSON incomplet) n'est pas rejouée : preuve réelle attendue des runs du lot (9.9 et 9.10 côté Opus).
- Ollama réel (accord d'Anaël requis) : vérifier qu'Ollama applique `maxLength` du `format` (grammaire) et respecte l'ordre `verdict` puis `justification` ; vérification : un appel de Juge minicpm sur q-044 rag-naif, justification ≤ 200 caractères, `verdict` émis en premier, pas de `non_conformant`.

## Commande de vérification

`uv run pytest -q --tb=short tests/unit/components/test_llm_judge.py tests/unit/llm tests/unit/scoring tests/unit/runner/test_story_8_11.py tests/unit/runner/test_story_5_2.py`

## Revue

### Passe 1 (2026-10-26, SHA revu 31b08db)

Branche à jour de `main` (95ef5be), pas de rebase.

- Important · medium · second avis 1 · corrigé : le rejeu 8.8 renvoie un JSON complet, pas une coupure au budget ; test renommé (`test_rejeu_8_8_justification_longue_complete_tronquee_et_conforme`), docstring et Reports disent ce qui est prouvé ; ajout d'un calcul de borne (`test_borne_la_justification_bornee_ne_peut_plus_atteindre_le_budget`, n = 1 à 3).
- second avis 2 (medium) · rejeté : la consigne Anthropic en `tool_choice: auto` dit déjà « Réponds uniquement en appelant l'outil, sans autre texte » (`CONSIGNE_OUTIL`), et la délibération d'Opus passe dans le thinking, couvert par la réserve de 4000 tokens (8.11) ajoutée au budget ; pas d'appel réel, aucune dépense.
- Nit · low · second avis 3-4 · reporté : ordre et `maxLength` de la grammaire non prouvés contre un vrai Ollama (Reports).
- Nit · low · second avis 5 · reporté : budget non réévalué (déjà en Reports).
- Nit · low · second avis 6 · corrigé : troncature mesurable ; la passerelle valide avec un contexte (`roles.TRONQUEES`) et pose `wl.justification_truncated` (nombre, absent si nul) sur le span d'une sortie conforme ; `contracts.md` §6 mis à jour.
- Nit · low · second avis 7 · corrigé : test bout en bout Anthropic (`tool_use.input` trop long → texte du provider → validation : tronqué, conforme, compté).
- Nit · low · second avis 8 · déjà consigné (clés de Cache des Juges changées).
- Complexité : 0 constat.
