---
story: "9.1"
title: "`wl calibrer` écrit ses verdicts au fil de l'eau"
status: review
---

# Story 9.1 : `wl calibrer` écrit ses verdicts au fil de l'eau

Exigences : FR-38, FR-33 ; AD-3 ; `contracts.md` §4.6 et §8. Corrige le report de la 8.11 : un plafond atteint ou une `ProviderError` non réessayable en cours de calibration perdait tous les verdicts payés.

## Réalisé

- `runner/calibrer.py` : chaque appel de Juge est écrit dans `<sortie>_verdicts.jsonl` dès sa réception (`flush` + `os.fsync`, classe `_Ecrivain`, fichier ouvert au premier verdict). Une ligne JSON par (Juge, `answer_id`, `pass_id`) : `answer_id`, `judge_model`, `pass_id`, `empreinte`, et `verdicts` (`{critère: {verdict, justification}}`) ou, pour une sortie non conforme après nouvel essai, `missing: true` + `error`. Ce format remplace l'ancienne ligne par Critère (clés `judge_model`, `answer_id`, `pass_id` conservées).
- Empreinte portée par chaque ligne (choix : dans chaque ligne, pas d'en-tête, pour garder « une ligne par triplet ») : 16 premiers caractères du SHA-256 de `experiment_id`, `run_id`, des Juges, de `calibration_passes` et des annotations (annotateur, réponse, critère, verdict). Elle change si l'Expérience (identifiant, Juges, passes), l'Exécution ou une annotation change.
- `--reprendre` : relit le fichier, vérifie l'empreinte de chaque ligne (sinon `ConfigError`, code 2), ne rappelle que les triplets absents ; un triplet `missing` est rappelé ; une dernière ligne tronquée par un arrêt brutal est écartée ; une ligne illisible ailleurs est refusée (code 2). `calibration.json` est calculé sur l'ensemble (identique à celui d'une calibration sans interruption). `n_appels` ne compte que les appels de la reprise.
- Un fichier de verdicts existant sans `--reprendre` ni `--ecraser` est refusé (code 2, avant tout appel payé) ; `--ecraser` le supprime ; les deux ensemble : code 2.
- `BudgetExceeded` (code 3) et `ProviderError` (code 4) à mi-parcours : l'exception porte `verdicts_recus` et `fichier_verdicts` ; `cli.py` affiche le nombre de verdicts conservés, le fichier et la commande de reprise (avec `--sortie` s'il a été passé). `calibration.json` n'est écrit qu'en fin de calibration complète ; sans interruption, son contenu est inchangé.
- `contracts.md` §4.6 (format du fichier, empreinte) et §8 (options, codes) mis à jour.
- Tests : `tests/unit/runner/test_story_9_1.py` (SDK Anthropic factice qui lève HTTP 400 au 5e appel : 4 verdicts relus, reprise qui n'appelle que les manquants et `calibration.json` égal à une calibration complète ; `fsync` espionné ligne par ligne ; plafond code 3 avec message ; refus sans option, `--ecraser`, incompatibilité des deux options ; empreinte différente (annotations, Expérience) ; ligne tronquée et verdict manquant ; ligne illisible). `test_story_8_11.py` et `test_story_5_2.py` réalignés (verdicts conservés au plafond, lignes `missing`, relance avec `--ecraser`).

## Reports

- Le Cache de réponses sert toujours la passe 0 d'une requête identique : après une interruption, le nombre d'appels SDK réels d'une reprise peut être inférieur au nombre de triplets rappelés (tests bornés en conséquence).
- Les avertissements d'une première tentative (Juge en échec) ne sont pas reconstitués à la reprise ; seuls les échecs de la reprise sont signalés.
- Une calibration interrompue n'écrit pas `calibration.json` partiel (pas demandé).

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/runner/test_story_9_1.py tests/unit/runner/test_story_8_11.py tests/unit/runner/test_story_5_2.py
```

## Revue

### Passe 1 (2026-10-26, SHA revu 15d2d1c)

Rebase : branche déjà à jour sur `main` (95ef5be). Aucun appel réseau (SDK Anthropic factice).

- Important, medium (high dès la 9.2), second avis 1 : l'empreinte ignorait le prompt des Juges, leur budget de sortie, le Catalogue et le contenu des Réponses : une reprise après changement de prompt mêlait deux prompts. Corrigé : `LLMJudge.requete` (requête et schéma sans envoi) ; l'empreinte couvre l'empreinte de la requête de chaque (Juge, Réponse) à la passe 0, schéma et entrée de Catalogue compris. Calcul après construction des Juges, avant tout appel. Test : prompt modifié → code 2, aucun appel, fichier intact.
- Important, medium, second avis 2 : `id_cal` neuf à chaque invocation, `per_run` repartait de zéro à la reprise. Corrigé : `calibration_id` porté par chaque ligne et repris par `--reprendre` (même Registre, mêmes Traces ; le coût de `judging` couvre toutes les tentatives). Test : reprise sous plafond déjà atteint → code 3, aucun appel.
- Important, low, second avis 3 : ligne complète sans saut de ligne final acceptée, l'ajout suivant s'y collait. Corrigé : seule une ligne terminée par « \n » compte ; la dernière, sans saut, est retirée et son triplet rappelé. Test.
- Important, low, second avis 4 : `x["verdicts"]` hors du `try` (KeyError non traduite) ; une ligne unique d'ancien format était supprimée comme tronquée. Corrigé : validation complète de chaque ligne (code 2 « illisible »), ancien format reconnu (code 2 avec consigne), une ligne complète n'est jamais supprimée. Tests paramétrés.
- Important, low, second avis 5 : `--ecraser` supprimait le fichier avant `Context.from_experiment` et `construire_juges`. Corrigé : suppression juste avant le premier appel, après toute validation. Test (panne injectée dans `construire_juges`, seule doublure interne, justifiée comme injection de panne).
- Nit, low, second avis 6 : interruption clavier sans phrase de reprise. Corrigé : `KeyboardInterrupt` porte le nombre de verdicts ; CLI code 1 avec la commande de reprise. Test. `OSError` d'écriture (disque plein) : rejeté, rare, et la reprise traite déjà la dernière ligne incomplète.
- Nit, low, second avis 7 : docstring de `calibrer` (code 4 sans `ProviderError`) et aide de `--reprendre`. Corrigé.
- Nit, low, second avis 8 : réécriture de la ligne tronquée non atomique. Corrigé : écriture temporaire puis `os.replace`.
- Nit, low, second avis 9 : ancien format par Critère illisible par le nouveau code. Corrigé : `contracts.md` §4.6 le dit et indique comment le relire ; `--reprendre` le refuse avec consigne (§8 à jour).
- Nit, low, second avis 10 : tests manquants. Corrigé : 7 tests ajoutés (points 1 à 6).
- Complexité : 0 constat (écriture en ajout O(1) par appel, fichier relu une fois).

Vérification : `test_story_9_1` (16), `8_11`, `5_2`, `8_9`, `test_llm_judge`, `8_3`, `test_providers`, `4_9` verts ; ruff, pyright, contrôle rapide verts.
