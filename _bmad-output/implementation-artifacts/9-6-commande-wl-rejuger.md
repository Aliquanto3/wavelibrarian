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

- Le Catalogue n'est pas comparé à la source (`catalog`, `catalog_date`, `models_frozen_at` admis, revue) : un nouveau Juge peut y entrer. Les coûts de génération copiés sont ceux écrits dans les spans de la source. `experiment_id` et `costs` doivent rester égaux.
- Les Questions du split courant sans Réponse dans la source (entrées dans le split après un re-Gel, ou par décalage de `max_questions`) sont refusées en code 2, nommées (revue).
- Le contenu du Jeu est contrôlé par l'empreinte du Gel recalculée avec le `split` de la source : la source ne garde pas le contenu de ses Questions, le refus nomme donc le Jeu, pas la Question ni le champ. Avec `max_questions`, une Question non posée qui a changé de split fait refuser (sûr, mais strict).
- Les Réponses `error` copiées de la source comptent dans `completed_with_errors`. Une reprise du rejugement ne peut pas les corriger, il faut un nouveau `wl run` (aide CLI, contrat §5). La source de la 9.10 a 76/76 Réponses `ok`.
- Le préflight ne porte que sur les Juges : le cache tiktoken et Ollama ne sont pas vérifiés (aucune génération).
- Les spans copiés gardent `wl.run_id` de la source (copie octet pour octet ; le Rapport ne lit pas ce champ). Les spans `query` d'anciennes tentatives (Réponse reprise après `budget_exceeded`) sont copiés comme `wl run --reprendre` les garde.

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/runner/test_story_9_6.py
```

## Revue

### Passe 1 (2026-10-26, SHA revu 51a38f7)

Base à jour (`main` 95ef5be). Cas réel 9.10 sondé en mémoire (copie de `manifest.json`, `experiment.resolved.yaml` et `answers.jsonl` de `20261018-115941-a2a512` dans un `WL_HOME` temporaire, aucun appel) avec `experiments/mini-cpu.yaml` et un Panel `[claude-opus-5-5]`, `panel_size: 1` : avant correctif, refus sur `catalog_date`, `corpus`, `models_frozen_at`, `questions` (chemins du dépôt principal contre ceux d'un worktree) ; après, accepté, empreinte du Corpus égale, Jeu conforme au Gel de la source au `split` près, `q-044` écartée. `costs`, `profile_settings` et les Configurations sont égaux.

- Important · high · second avis 1 · corrigé : `catalog`, `catalog_date` et `models_frozen_at` comparés, le cas réel était refusé. Le Catalogue est admis ; test `test_catalogue_et_chemins_changes_acceptes`.
- Important · medium · revue · corrigé : `corpus`, `questions` et `scenario` comparés par chemin, un rejugement lancé depuis un autre dossier (worktree) était refusé. Ils sont désormais comparés par leur contenu (`inputs`, Gel), `scenario` par sa présence.
- Important · medium · second avis 2 · corrigé : le contenu d'une Question gardée n'était pas contrôlé. L'empreinte du Gel est recalculée avec le `split` de la source et doit égaler celle de la source (code 2). Le refus nomme le Jeu, pas la Question ni le champ : la source ne garde pas le contenu de ses Questions (consigné en Reports). Test `test_refus_contenu_d_une_question_gardee_modifie`.
- Important · medium · revue · corrigé : une Question du split courant sans Réponse dans la source (entrée par re-Gel ou par décalage de `max_questions`) était jugée absente en silence. Refus code 2, Questions nommées ; test `test_refus_question_entree_dans_le_split_sans_reponse` ; le test des Questions écartées passe sans `max_questions`, comme mini-cpu.
- Nit · medium · second avis 3 · consigné : Réponses `error` recopiées, non réparables par `--reprendre` (aide CLI, contrat §5, Reports). Source réelle : 76/76 `ok`.
- Important · low · second avis 4 · corrigé : source `completed` sans `answers.jsonl` → code 2 « sans Réponse » ; test `test_refus_source_sans_reponse`.
- Nit · low · second avis 5 · consigné : préflight limité aux Juges, cache tiktoken non vérifié (Reports).
- Nit · low · second avis 6 · consigné : `wl.run_id` des spans copiés = source, non lu par le Rapport (Reports).
- Nit · low · second avis 7-8 · rien à faire.
- Nit · low · second avis 9 · consigné : spans `query` d'anciennes tentatives copiés, comme `wl run --reprendre` (Reports).
- Nit · low · second avis 10 · corrigé : tests Catalogue changé et `--tolerer-erreurs` sur rejugement ajoutés.
- Nit · low · second avis 11 · corrigé : un écart dans une section objet est nommé par ses clés (`retries.max_attempts`, `costs.fx`) ; test `test_differences_nomme_les_cles_d_une_section`.
- Complexité : 0 constat (lectures linéaires d'`answers.jsonl` et `traces.jsonl`, une fois par commande).
