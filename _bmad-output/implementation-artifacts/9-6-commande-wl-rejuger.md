---
story: "9.6"
title: "Commande `wl rejuger`"
status: review
---

# Story 9.6 : commande `wl rejuger`

Exigences : FR-1, FR-37, FR-40 ; AD-11 ; `contracts.md` §5, §8 ; limites (iii) et (iv) de `fix-arbitrages-8-3-8-8`. AC : `epics.md` l. 2436-2463.

## Réalisé

- `runner/rejuger.py` (nouveau) : `rejuger(experience, questions, *, wl_home, source, reprendre=None, providers=None)`. Il crée une nouvelle Exécution (nouveau `run_id`, manifeste `rejudged_from`, `source_freeze_sha256`, `excluded_questions`) et copie de la source, pour les seules Questions du split courant du Jeu gelé (`load_questions`) :
  - les lignes effectives d'`answers.jsonl`, octet pour octet. Leur `answer_id` garde le `run_id` source, si bien que les annotations faites sur la source s'y rapportent toujours (cas de la 9.10) ;
  - les spans de `traces.jsonl` hors Poste `judging` (indexation comprise, Questions écartées exclues) ;
  - `corpus_profile.json` et `applicability.json`.
  
  Il recalcule ensuite les Critères automatiques et le Panel de l'Expérience fournie par `_Runner.juger`, le chemin de jugement de `wl run`, sans aucune duplication : la modalité `na` (9.3) y passera telle quelle. Il traite comme `run_experiment` le plafond (`budget_exceeded`), `completed_with_errors` (`causes_execution`, erreurs copiées comprises) et `--reprendre`.
- Contrôles, code 2 avant tout appel :
  - `differences()` compare les Expériences résolues section par section, hors `judges`, `budget` et `max_error_rate`, et nomme l'écart (`seed`, `split`, `configurations.bm25.params`, Configuration ajoutée ou absente, ordre) ;
  - le contenu du Corpus et du Scénario doit être celui de `inputs` de la source ;
  - la source doit être `completed` ou `completed_with_errors` ;
  - le `run_id` doit être valide.
  
  Le Gel peut différer : c'est l'usage. Les Questions sorties du split courant sont écartées, listées par la CLI et consignées dans le manifeste. `wl run --reprendre` sur l'ancien Gel reste refusé (limite (iii)).
- Reprise d'un rejugement : `wl rejuger <source> <exp> --reprendre <run_id du rejugement>` applique les contrôles de `verifier_reprise` (Juges figés, plafonds relevables), exige `rejudged_from == <source>`, puis redemande seulement les Critères sans verdict. Sur un rejugement déjà terminé, la commande sort en code 0 avec le message « déjà terminée ».
- `cli.py` : commande `rejuger`. Le préflight ne porte que sur les Juges : aucune génération, donc pas d'Ollama pour mini-cpu. La fin de `run` (Rapport, codes 1/3, causes) est extraite dans `_conclure` et partagée par les deux commandes ; la ligne « Reprise : » propose la commande adaptée.
- `runner/rundir.py` : `create_run_dir(..., extra=...)`, des champs ajoutés au manifeste.
- Rapport :
  - `report/generer.py` : en-tête « Rejugement de l'Exécution `<run_id>` » et Questions écartées ;
  - `report/section_couts.py` : les titres du coût total, des Postes et de la latence portent « (copiés de `<run_id>`) », et une ligne précise que le Poste `judging` est celui du rejugement. `report/couts.py` n'est pas touché (9.8).
- `contracts.md` : §5 (rejugement, champs du manifeste) et §8 (commande).
- Tests, `tests/unit/runner/test_story_9_6.py` (7 tests, Faux LLM, Catalogue de test avec un 4e Juge `fake-llm-d`) :
  - Réponses, profil, applicabilité et spans de génération identiques octet pour octet ;
  - Critères automatiques identiques, verdicts de `fake-llm-d` inversés, Panel `(d, c)` à égalités ;
  - Rapport marqué ;
  - Question sortie du dev par re-Gel : écartée, listée au manifeste, dans la CLI et dans le Rapport, et `wl run --reprendre` refusé ;
  - refus d'une Configuration modifiée (code 2, différence nommée, aucun dossier créé) ;
  - `differences` : plafonds et Juges admis, `seed`, `split` et Configuration ajoutée nommés ;
  - source inconnue, `run_id` invalide, source non terminée ;
  - plafond (code 3) puis reprise : Juges changés refusés, reprise d'une Exécution qui n'est pas un rejugement refusée ;
  - Juge en échec : `completed_with_errors` (code 1), puis reprise jusqu'à `completed`.

## Reports

- Le Catalogue n'est pas comparé à la source : un nouveau Juge peut y entrer. Les coûts de génération copiés sont ceux écrits dans les spans de la source. `experiment_id`, `catalog` (chemin) et `catalog_date` doivent en revanche rester égaux (lecture stricte de l'AC 2). À assouplir si la 9.10 en a besoin.
- Les Questions du split courant sans Réponse dans la source (entrées dans le split après un re-Gel) ne sont ni posées ni listées.
- Les Réponses `error` copiées de la source comptent dans `completed_with_errors`. Une reprise du rejugement ne peut pas les corriger, il faut un nouveau `wl run`.

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/runner/test_story_9_6.py
```
