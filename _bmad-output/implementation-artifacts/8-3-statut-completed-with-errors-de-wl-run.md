---
story: "8.3"
title: "Statut completed_with_errors de wl run"
status: done
---

# Story 8.3 : Statut `completed_with_errors` de `wl run`

Exigences : FR-1, FR-40 ; AD-11 ; `contracts.md` §5 (`manifest.json`, `max_error_rate`), §8 (codes de sortie, `--tolerer-erreurs`) ; arbitrage P9. Limite L1 levée (`runner/execute.py` ne connaissait que `completed` et `budget_exceeded`).

## Réalisé

- `config/experiment.py` : `max_error_rate: float = 0.2` (strict, [0, 1]) dans l'Expérience ; hors bornes, chaîne ou booléen : refus à la validation, code 2. Repris dans `ResolvedExperiment` (défaut 0,2 pour relire une Exécution antérieure).
- `core/bilan.py` (nouveau) : `causes_execution` et `decrire_cause`. Placé dans `core` car `runner` et `report` sont indépendants (AD-1, contrat `import-linter`).
- `runner/execute.py` : `RunStatus` et `rundir.Status` étendus ; décompte par Configuration (`compter`) et Critères sans verdict par Configuration (`juger`) ; en fin d'Exécution non plafonnée, statut `completed_with_errors` si une cause existe ; `RunOutcome.causes`. Le plafond prime : `budget_exceeded`, aucune cause calculée, code 3.
- `manifest.json` : `causes` = liste `{config_id, cause, count}`, `cause` parmi `no_ok_answer`, `error_rate`, `unjudged` (vide si aucune ; retirée à la réouverture d'une reprise). `contracts.md` §5 aligné sur cette forme.
- `cli.py` : `--tolerer-erreurs` ; résumé français sur stderr (une ligne par cause, puis la commande de reprise) ; code 1 sans l'option, 0 avec, après le Rapport. Le message générique « Critère(s) sans verdict de panel » est remplacé par le résumé.
- `report/generer.py` `_bandeau` : avertissement après le titre de `report.md`, une puce par Configuration et cause.
- Reprise : `_Runner.reprendre` ne compte plus les Réponses `error` comme faites (reposées) ; les Critères sans verdict sont rejugés comme avant ; `deja_terminee` reste vraie seulement pour `completed` sans `unjudged` (docstring précisée).
- Tests : `tests/unit/runner/test_story_8_3.py` (11 tests) ; tests 4.4, 4.5 et 4.9 mis à jour (statut attendu, ou `--tolerer-erreurs` quand le statut n'est pas leur objet).

## Règles retenues (à confirmer en revue)

- Taux d'`error` = `error / (ok + error)` ; les `inapplicable` n'y entrent pas. « Dépasse » = strictement supérieur : 1 sur 5 (0,2) ne déclenche pas, 2 sur 5 (0,4) déclenche.
- « Aucune Réponse `ok` » exige au moins une `error` : une Configuration seulement `inapplicable` n'est pas en erreur (même règle que `RunOutcome.all_failed`).
- Une Configuration sans `ok` relève aussi de `error_rate` (taux 1,0) : les deux causes sont listées.

## Recalcul des exemples chiffrés

- Run de référence (`verifications-reelles-2026-10-18.md`, 2e série) : PageIndex 0/2 → `no_ok_answer` (2) et `error_rate` (2/2 = 1,0 > 0,2) ; rag-naif et raptor 1 `error` sur 2 = 0,5 > 0,2 → `error_rate` ; 8 Critères sans verdict → `unjudged`. Statut attendu `completed_with_errors`, code 1 : conforme à l'AC.
- `max_error_rate` 0,2 : cohérent avec P9 et `contracts.md` §4. Aucune contradiction trouvée.

## Acceptance Criteria

1. Statut `completed_with_errors` si une Configuration n'a aucune `ok`, si un Critère reste sans verdict, ou si le taux d'`error` d'une Configuration dépasse `max_error_rate` (0,2 par défaut) ; sinon `completed`. Causes par Configuration dans `manifest.json`.
2. `wl run` : code 1 avec résumé français ; `--tolerer-erreurs` : code 0, même résumé, **sauf `all_failed` (aucune Réponse valide) : code 1 même avec `--tolerer-erreurs`** (AC modifié par arbitrage d'Anaël du 2026-10-19, réalisé par fix-arbitrages-8-3-8-8) ; `budget_exceeded` et code 3 priment.
3. `report.md` commence (sous le titre) par un avertissement nommant Configurations et causes.
4. `--reprendre` repose les Questions en `error` et rejuge les Critères sans verdict ; `deja_terminee` faux pour `completed_with_errors`.
5. Faux LLM : reproduction du run mini-cpu d'avant correctif → `completed_with_errors`, code 1 ; scénario sain → `completed`, code 0. `max_error_rate` hors [0, 1] → code 2.

## Tâches

- [x] Schéma et validation de `max_error_rate`.
- [x] Statut, causes et manifeste (runner).
- [x] CLI : codes de sortie, `--tolerer-erreurs`, résumé.
- [x] Bandeau du Rapport.
- [x] Reprise des `error`.
- [x] Scénarios Faux LLM et tests ; Expériences livrées valides, SM-3 (`tests/e2e`) vert en `completed`.

## Reports et points à arbitrer

- Le bandeau est placé sous le titre `# Rapport`, comme celui de `budget_exceeded` ; « commence par » lu comme « avant toute section ».
- Une Expérience résolue gagne `max_error_rate` : l'empreinte des Exécutions antérieures à 8.3 change, leur `--reprendre` est refusé (code 2).
- Reprise : une Question en `error` est reposée à chaque reprise, y compris après `budget_exceeded` ; une erreur déterministe (sortie non conforme) se reproduit (seuls les succès vont au Cache de réponses).

## Arbitré par Anaël (2026-10-19, réalisé par fix-arbitrages-8-3-8-8)

- `all_failed` (aucune `ok` sur toute l'Exécution) sort en code 1 même avec `--tolerer-erreurs` (AC 2 ci-dessus modifié). Message et résumé toujours affichés.
- Configuration entièrement `inapplicable` (ni `ok` ni `error`) : confirmée non comptée comme cause (règle du dev gardée, inchangée).
- `max_error_rate` entre dans l'empreinte de l'Expérience mais suit désormais la règle des plafonds (comme `budget`) : relevable à la reprise, consigné dans `resumptions`.

## Revue

- medium, second avis 1 : `all_failed` sortait en 1 avant la règle `--tolerer-erreurs`, contre l'AC 2. Corrigé (`cli.py`), test `test_toutes_en_erreur_tolerer_erreurs_code_0` ; point à arbitrer ci-dessus.
- low, second avis 2 : Configuration seulement `inapplicable` non comptée. Rejeté (règle gardée, motif ci-dessus), à arbitrer.
- low, second avis 3 : `max_error_rate` dans l'empreinte. Consigné, non changé (à arbitrer).
- low, second avis 4 : lignes `answers.jsonl` en double pour les Questions rejouées. Rejeté : journal en ajout seul (AD-11), tous les lecteurs (`rundir.read_answers`, `report/lecture.lire_reponses`) gardent la dernière ligne ; même mécanisme que `budget_exceeded` (4.8).
- low, second avis 5 : taux réel absent. Corrigé : `rate` ajouté aux causes `error_rate` du manifeste (`contracts.md` §5 aligné), affiché par la CLI et le bandeau (« taux 50 % au-dessus de `max_error_rate` (20 %) ») ; un manifeste sans `rate` reste décrit sans le taux.
- low, second avis 6 : `wl.resumed` sur les hits de cache des Questions `error` rejouées. Rejeté : l'appel d'origine reste tracé dans `traces.jsonl` avec son coût et son `wl.cost_uncached` ; le hit rejoué n'apporte qu'un coût réel nul et n'est pas recompté (`report/couts.py`). Un appel refait hors cache n'est pas marqué et compte, à juste titre (dépense nouvelle). Aucun coût ne sort du Rapport.
- low, revue : NaN et infini pour `max_error_rate`. Ajoutés au test de refus (code 2) ; pydantic les refuse déjà (bornes [0, 1]).

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/runner/test_story_8_3.py
```
