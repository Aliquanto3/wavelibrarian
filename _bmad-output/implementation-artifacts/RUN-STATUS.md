# RUN-STATUS - run autonome WaveLibrarian

Fichier tenu par l'orchestrateur. Une session neuve (après `/clear`) reprend le run en ne relisant que ce fichier et `sprint-status.yaml`, dans le même dossier.

## État

| Champ | Valeur |
| --- | --- |
| Mis à jour | 2026-10-17 21:52 |
| Story en cours | 1.6 |
| Stories livrées | 5 / 56 |
| Dépense Anthropic | 0,00 $ / plafond 5 $ |
| Pilote slm-quality-bench | en cours (`pilot-report.md` absent) |
| Dernière mesure du banc | voir « Journal de surveillance » |
| Blocages | aucun |
| À arbitrer par Anaël | Story 1.4, AC 3 : l'exemple « 1 M + 1 M → 0,60 $ » contredit le palier ×5 au-delà de 100 000 tokens (3,00 $ sur le vrai Catalogue). Règle de palier gardée. |

## Consignes du run

Ordre : les stories de `sprint-status.yaml`, epics 1 à 7, dans l'ordre du fichier. Par story : `agent-cost-kit:dev-story` → `agent-cost-kit:second-avis` → `agent-cost-kit:reviewer` (avec la liste du second avis) → intégration sur `main`, puis mise à jour du sprint status et de ce fichier. Appels bloquants, une passe de revue, pas d'imbrication de sous-agents.

Contexte : ne jamais relire `epics.md` en entier (150 Ko). Lire `epic-<N>-context.md` (compilé une fois par epic dans ce dossier), puis la seule section de la story : repérer `### Story N.M` par une recherche, et lire jusqu'à la story suivante. Transmettre aux sous-agents ce chemin et ces numéros de ligne, pas le fichier entier.

Contraintes du run autonome, reprises de `_bmad-output/planning-artifacts/epics.md`. Elles s'ajoutent aux stories sans changer leurs critères.

### Cohabitation avec slm-quality-bench (jusqu'au 18/10 vers 10 h, ou jusqu'à `pilot-report.md`)

- **Ollama local interdit.** Aucune requête hors `/api/version`, `/api/ps` et `/api/tags`, aucune commande `ollama`, aucun second serveur de modèles. Les tests `real_local` (stories 1.11 et 1.12) sont écrits mais pas exécutés : ne jamais lancer `pytest -m real_local`. Pas de `wl run` sur `mini-cpu.yaml`. Le préflight se limite à `/api/tags`.
- **GPU interdit.** `CUDA_VISIBLE_DEVICES=-1` avant tout code de ML. Après chaque exécution de code de ML, vérifier que son PID n'apparaît pas dans `nvidia-smi --query-compute-apps=pid,process_name --format=csv`.
- **Pas d'extra lourd, aucun téléchargement de plus de 1 Go.** Pas d'extras `local` (torch) ni `docling`, pas de `wl installer`.
- **Ressources.** `OMP_NUM_THREADS=4`, `MKL_NUM_THREADS=4`, `OPENBLAS_NUM_THREADS=4` ; au plus 6 Go de RAM ; priorité `BelowNormal` ; aucun pytest parallèle.
- **API autorisée.** Seule la story 4.15 (SM-4) appelle l'API Anthropic, avec des Juges et un embedder factices, sous le plafond de 5 $.

### Surveillance toutes les 10 minutes

Avant de commencer, puis toutes les 10 minutes environ, consigner une ligne dans le journal ci-dessous :

- débit du banc : réponses des 10 dernières minutes dans `C:\Users\Utilisateur\Documents\GitHub\wavelocalai\data\quality_bench\campaigns\pilot-20261017\log-generate.log`, comparées sur le même modèle et la même piste (champs 2 et 4 de la clé `pilot-20261017|modèle|mode|piste/…`) ;
- CPU total et RAM libre ;
- consommation propre du run : temps CPU, RSS de pointe, threads.

### Seuils d'arrêt

- **Pause** si le débit du banc baisse de plus de 15 %, si le CPU dépasse 80 % de façon soutenue, ou si la RAM libre passe sous 6 Go. Reprendre quand la mesure revient sous les seuils.
- **Arrêt sans rien toucher, et prévenir Anaël**, si une ligne `ERROR` ou « campagne arrêtée » apparaît dans le log du banc.
- Le travail lourd attend `pilot-report.md`.

### Après le pilote

Dès que `pilot-report.md` existe dans le dossier de la campagne, Ollama local redevient utilisable : tests `real_local` (stories 1.11 et 1.12) et `wl run` sur `mini-cpu.yaml`, sur le profil CPU (`num_gpu: 0`). Le GPU reste à `CUDA_VISIBLE_DEVICES=-1` sauf avis contraire d'Anaël. Le noter ici dans « État ».

### Reprise après `/clear`

1. Lire ce fichier, puis `sprint-status.yaml`.
2. Une story `in-progress` sans commit d'intégration est reprise depuis son fichier de story (et son worktree s'il existe).
3. Refaire une mesure du banc avant de relancer un dev-story.

## Reports entre stories

À transmettre au dev-story de la story cible.

- **2.1 / 2.2** : formats du Corpus et parsers du registre, nécessaires pour remplacer `parser: auto` (story 1.5).
- **4.3 / 4.4** : le runner remplace `parser: auto` par le parser concret avant `write_resolved` et `RunContext.parser` (stories 1.2 et 1.5) ; vérifier que `experiment.resolved.yaml` ne contient plus `auto`.
- **Gateway (1.9)** : `cache_write_1h` n'est pas facturé, `Usage` n'a pas de poste 1 h (story 1.4).
- **Story outillage / CI** : lancer `test_socket_tcp_bloque` sous Linux (story 1.1).

## Journal de surveillance

| Heure | Débit banc (10 min, modèle / piste) | CPU | RAM libre | Run (CPU s, RSS max, threads) | Décision |
| --- | --- | --- | --- | --- | --- |
| 20:58 | 8 (lfm2.5-2.6b / reasoning, ~1 réponse/41 s) ; fenêtre précédente sur un autre modèle, référence posée | 9 % | 17,6 Go | 0 s, 86 Mo, 57 thr (aucun pytest) | Mesure de départ, aucune ERROR : on démarre 1.1 |
| 21:09 | 20 (lfm2.5-2.6b / reasoning) ; 11 sur les 10 min précédentes ; +82 % | 12 % | 16,7 Go | 1 s, 86 Mo, 101 thr (uv/pytest du run) | Sous les seuils : on continue (1.2) |
| 21:20 | 19 (lfm2.5-2.6b / reasoning) ; 10 min avant : 23 ; -17 % | 16 % | 17,2 Go | 1 s, 86 Mo, 70 thr (9 proc) | Faux signal : la piste reasoning s'est terminée vers 21:19 (passage à rag), fenêtre incomplète ; intervalle par réponse inchangé (~41 s). On continue (1.3). Mesure passée en secondes par réponse. |
| 21:22 | Indicateur révisé : durée des réponses tronquées (budget de tokens fixe), même modèle / mode / jeu. think_on reasoning/bbeh-mini 42 s vs 41 s (−3 %) | 7 % | 17,0 Go | 0 s, 86 Mo, 54 thr | Pas de ralentissement réel : on continue (1.3). Les comptages bruts par piste mélangent des questions de longueurs très différentes. |
| 21:30 | 2 tronq. (lfm2.5-2.6b) : think_on reasoning/bbeh-mini 1 tronq., 42 s/tronq. (pas de réf.) ; think_on tools/bfcl-multi 1 tronq., 25 s/tronq. (pas de réf.) ; pire +0 % | 12 % | 15.5 Go | 1 s, 86 Mo, 76 thr (9 proc) | Sous les seuils : on continue (1.4) |
| 21:40 | 2 tronq. (gemma4:e2b-it-qat) : think_off instructions/ifbench 2 tronq., 19 s/tronq. (pas de réf.) ; pire +0 % | 23 % | 16.9 Go | 1 s, 86 Mo, 72 thr (9 proc) | Sous les seuils : on continue (1.5) |
| 21:50 | 17 tronq. (gemma4:e2b-it-qat) : think_off reasoning/bbeh-mini 20 s/tronq. (nouveau modèle, référence posée) | 26 % | 15,1 Go | 1 s, 86 Mo, 59 thr | Sous les seuils |
| 21:52 | 19 tronq. (gemma4:e2b-it-qat) : think_off reasoning/bbeh-mini 19 tronq., 20 s/tronq. vs 20 (-0 %) ; pire -0 % | 36 % | 13.3 Go | 1 s, 86 Mo, 70 thr (9 proc) | Sous les seuils : on continue (1.6) |

## Journal des stories

| Story | Début | Fin | Commit | Dépense | Remarques |
| --- | --- | --- | --- | --- | --- |
| 1.1 | 21:00 | 21:09 | 4f3294e21ae06ae43b9c78fefa2887e0c331053c | 0 $ | Revue : 2 high (contrats import-linter inopérants, test lint-imports vide) et 1 medium corrigés ; typer `>=0.26,<1` (conflit docling `<0.27`) ; test socket sous Linux reporté à une story outillage. 14 tests verts. |
| 1.2 | 21:10 | 21:30 | e349d1970419bd0b7d13367023ed0aeca48430a3 | 0 $ | Revue : 2 medium corrigés (index_key lit le parser résolu via RunContext.parser, contracts.md §2.4 mis à jour ; ArchCapabilities gelé + extra=forbid). 33 tests verts. |
| 1.3 | 21:23 | 21:30 | 3908cf1d4686321c7aa58ba162b2c59230b53789 | 0 $ | Revue : 2 medium corrigés (fuite sys.modules dans la fixture ; register exige Params forbid+frozen, AD-2) et 6 low. 42 tests verts. |
| 1.4 | 21:31 | 21:40 | 5b06b7ec0bca3bbb6c44479db7b51da9e8b6ccc6 | 0 $ | AC 3 contradictoire (0,60 vs palier ×5 → 3,00) : règle de palier gardée, à arbitrer. Revue : tarifs obligatoires par poste, pricing refusé sur modèle local, profil = nom de fichier. 62 tests verts. |
| 1.5 | 21:41 | 21:52 | 6414d58681c32a6f6b8f4ccbe6839343a33a80a6 | 0 $ | Revue : ModelRef nu refusé au register, juges explicites non écrasés (is None, ge/min_length), seed strict. parser:auto reporté au runner (voir Reports). 93 tests verts. |
