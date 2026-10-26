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
