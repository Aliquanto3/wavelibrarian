---
story: "fix-arbitrages-8-3-8-8"
title: "Arbitrages d'Anaël du 2026-10-19 sur 8.3 et 8.8 restés non codés"
status: review
---

# Correctif fix-arbitrages-8-3-8-8 : arbitrages du 2026-10-19 restés non codés

Source : `RUN-STATUS-v0.2.0.md`, journal 2026-10-19. Exigences : FR-1, FR-40, FR-13 ; AD-11, AD-15 ; `contracts.md` §4.5 (Questions, Gel), §5 (`manifest.json`), §8 (codes de sortie) ; stories 8.3, 8.8, 2.6, 3.6, 3.7. Trois arbitrages à réaliser sur 8.3 (AC 1 à 3 ci-dessous), un sur 8.8 (AC 4, bloqué — voir Reports), plus la bascule de 8.8 en `done` (AC 5).

## AC 1 : `all_failed` sort en 1 même avec `--tolerer-erreurs`

- Modification d'AC validée par Anaël (AC 2 de la story 8.3, mise à jour dans sa spec). Avant ce correctif, `cli.py` ne faisait sortir en 1 pour `completed_with_errors` que si `not tolerer_erreurs` ; `all_failed` (aucune Réponse `ok`, au moins une `error`) suivait la même règle et sortait donc en 0 avec `--tolerer-erreurs`.
- Correctif (`cli.py::run`) : une Exécution `all_failed` sort toujours en 1, avant le test sur `--tolerer-erreurs`. Le message « Aucune Réponse valide : toutes les Questions sont en erreur. » reste affiché dans les deux cas.
- Test réaligné : `tests/unit/runner/test_story_8_3.py::test_toutes_en_erreur_tolerer_erreurs_code_0` (qui affirmait l'ancien comportement, lui-même issu d'un correctif de second avis sur cette même règle) renommé `test_toutes_en_erreur_code_1_meme_tolerer_erreurs` et réécrit pour les deux appels (sans puis avec `--tolerer-erreurs`, code 1 dans les deux cas).

## AC 2 : Configuration seulement `inapplicable` n'est pas une erreur

- Confirmé par Anaël : déjà conforme avant ce correctif. `core/bilan.py::causes_execution` n'ajoute `no_ok_answer` que si `erreurs > 0` (une Configuration purement `inapplicable` n'entre dans aucune cause) ; `RunOutcome.all_failed` (`runner/execute.py`) exige de même `counts["error"] > 0`. Déjà figé par `test_taux_d_erreur_strictement_au_dessus_du_seuil` (cas `"c": {"inapplicable": 3}`) et par `test_long_context_inapplicable_les_autres_s_executent` (4.4, bout en bout, `status: completed`).
- Ajouté : `tests/unit/runner/test_fix_arbitrages_8_3_8_8.py::test_configuration_entierement_inapplicable_nest_pas_all_failed`, bout en bout avec une seule Configuration (`contexte-long`, palier dépassant la fenêtre) : `ok: 0, error: 0, inapplicable: 2`, `status: completed`, exit 0, aucune mention `all_failed`. Aucun changement de code, seulement le test qui fige la règle.

## AC 3 : `max_error_rate` relevable à la reprise

- Choix : `max_error_rate` suit désormais exactement la règle déjà en place pour `budget` (AC 2 de la 4.8), plutôt qu'une nouvelle option CLI `--max-error-rate`. Justification : le mécanisme de reprise distingue déjà « plafonds » (exceptés de l'empreinte `experiment.sha256`, relevables en modifiant l'Expérience avant `--reprendre`) du reste (toute autre différence refusée, code 2) ; `max_error_rate` est de la même nature qu'un plafond (un seuil de tolérance, pas une donnée d'exécution comme le Corpus ou les modèles). Ajouter une option CLI dédiée aurait dupliqué ce mécanisme pour un seul champ sans le généraliser aux futurs plafonds, et aurait demandé une donnée supplémentaire (valeur par défaut si l'option est absente) que l'Expérience porte déjà.
- Correctif :
  - `runner/resume.py::verifier_reprise` : l'empreinte compare l'Expérience demandée à `experiment.sha256` en figeant `budget` **et** `max_error_rate` à leur valeur stockée (`stockee.max_error_rate`), comme `budget` l'était déjà seul. Tout autre écart reste refusé.
  - `runner/rundir.py::reopen_run_dir` : prend `max_error_rate: float` en paramètre, consigné dans `resumptions[i]["max_error_rate"]` (comme `resumptions[i]["budget"]`) — la valeur effective en vigueur pour la reprise.
  - `runner/execute.py::run_experiment` : passe `experience.max_error_rate` à `reopen_run_dir`. `experience` est déjà l'Expérience résolue de l'appel courant (celle qui porte la nouvelle valeur si l'Expérience a été modifiée) : aucun autre changement n'est nécessaire, `causes_execution` lisait déjà `experience.max_error_rate` de l'appel courant.
- Sans modification de l'Expérience, le comportement est inchangé (même valeur stockée que relevée).
- Tests : `tests/unit/runner/test_fix_arbitrages_8_3_8_8.py::test_max_error_rate_relevable_a_la_reprise` (erreur déterministe sur la 2e Question distincte : rate 0,5 > 0,2 par défaut → `completed_with_errors`, code 1 ; `max_error_rate: 0.6` à la reprise → `completed`, code 0, `resumptions[0]["max_error_rate"] == 0.6`) et `test_max_error_rate_non_releve_refuse_un_autre_ecart` (un autre écart, ex. `seed`, reste refusé en code 2).

## AC 4 : q-044 en phase `update` — bloqué

- Constat : q-044 a déjà `scenario_target: {operation: op-1, state: after}` (comme q-045, q-046, q-047, les 3 autres Questions « phase update » du Mini-corpus, cf. story 3.7). Ce qui diffère : q-044 est en `split: dev`, les 3 autres en `split: test`. C'est cet écart qui cause l'Ancrage non résolu observé au run 8.8 (`experiments/mini-cpu.yaml` a `split: dev` et ne déclare aucun `scenario:` ; q-044 est donc posée en phase `base` seule, sur un Corpus qui n'a pas encore le Document `chronique-1415.md` ajouté par `op-1`).
- Blocage : `split` n'est pas un champ libre du Jeu gelé, il est **recalculé en entier** par `wl questions geler` à partir de `(type, dev_ratio, graine)` seul (`evalset/freeze.py::geler` → `_partager`), sans tenir compte de `scenario_target`. Un re-Gel avec la même graine (42) et le même ratio (0,4) — y compris avec `--forcer` — redonne la même répartition pour toutes les Questions `factual`, donc `dev` pour q-044, qu'on ait ou non édité son `split` à la main au préalable (vérifié : `freeze.geler(doc, 0.4, 42, forcer=True)` redonne `q-044.split == "dev"` et la même empreinte que le Gel actuel). Changer la graine ou le ratio pour faire basculer q-044 rebrasserait toutes les autres Questions `factual` (dev ↔ test), bien au-delà du périmètre de ce correctif.
- Pas réalisé : déplacer q-044 en `test` demanderait soit une nouvelle exigence (un mécanisme de Gel qui respecte `scenario_target` ou une exception explicite par Question, hors périmètre, à faire arbitrer), soit de casser à la main l'empreinte du Gel (contraire à la contrainte « respecter le mécanisme de gel » de ce correctif). `wl questions controler --scenario` reste vert (0 signalement) : le Jeu n'est pas modifié.
- Report à Anaël : comment traiter une Question `scenario_target` tombée en `dev` par le tirage stratifié (le Gel ne connaît pas `scenario_target`) ? Options possibles pour un prochain lot : (a) étendre `_partager` pour stratifier aussi par présence de `scenario_target` ; (b) exclure les Questions `scenario_target` du tirage aléatoire et les assigner à `test` par construction ; (c) ajouter `scenario:` à `experiments/mini-cpu.yaml` pour que la phase `after_update` soit jouée (mais la story 8.8 ne demandait que la phase `base`, et un Corpus mis à jour changerait aussi les Réponses des 3 autres Configurations).

## AC 5 : 8.8 passe en `done`

- `sprint-status.yaml` : `8-8-run-mini-cpu-sur-tout-le-split-dev-et-seuil-de-lazygraphrag` passe de `review` à `done` (commentaire « à arbitrer » retiré, remplacé par le rappel de l'arbitrage B1) ; `last_updated` mis à jour.

## Reports

- AC 4 non réalisé : voir blocage ci-dessus, à arbitrer par Anaël avant toute tentative.
- Justification du Decider et seuil `relevance_threshold` (B2 de l'arbitrage 8.8) et méthode `mixed` (8.6) : reportés au lot suivant, hors périmètre de ce correctif (non demandés par la consigne).

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/runner/test_story_8_3.py tests/unit/runner/test_fix_arbitrages_8_3_8_8.py tests/unit/runner/test_story_4_8.py
```

## Revue

Revue Opus du 2026-10-23, branche rebasée sur `origin/main` (e1b50aa) avant jugement.

- medium · second avis · corrigé · `contracts.md` §8 et `epics.md` (AC de la 8.3) disaient encore « code 0 avec `--tolerer-erreurs` » pour `all_failed` : réalignés (code 1 toujours). L'aide CLI de `--tolerer-erreurs` était déjà juste.
- medium · second avis · corrigé · `report/generer.py::_bandeau` citait le seuil de `experiment.resolved.yaml` (valeur du départ) : après une reprise au seuil relevé mais encore dépassé, le Rapport affichait 20 % au lieu du seuil appliqué. Il lit désormais `resumptions[-1].max_error_rate` s'il existe ; test `test_bandeau_du_rapport_cite_le_seuil_releve_a_la_reprise`.
- low · second avis · corrigé en partie · le constat « la branche `plafonds_egaux` n'est pas testée » est faux : `test_max_error_rate_relevable_a_la_reprise` sort en 2 sans le correctif. Renforcé tout de même : relever `max_error_rate` en même temps qu'un autre écart (`seed`) reste refusé.
- low · second avis · rejeté · reprise d'une Exécution `completed` (« rien à reprendre ») : sans cause, aucun seuil n'a d'effet, relever `max_error_rate` n'y changerait rien. Le seuil modifié ne figure alors pas dans `resumptions` (aucune reprise n'a lieu), ce qui est cohérent.
- low · second avis · corrigé · `sprint-status.yaml` : commentaire « B3 (q-044) reporté » ajouté sur 8-8 (décision de l'orchestrateur : 8-8 reste `done`).
- low · second avis · corrigé · `contracts.md` (ligne `max_error_rate` et §5 `manifest.json`) : relevable à la reprise, consigné dans `resumptions[i]`.
- Complexité : 0 constat (aucune structure qui grossit n'est parcourue par événement dans le diff ; `resumptions[-1]` est en O(1)).
