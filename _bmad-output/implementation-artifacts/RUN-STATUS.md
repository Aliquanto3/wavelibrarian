# RUN-STATUS - run autonome WaveLibrarian

Fichier tenu par l'orchestrateur. Une session neuve (après `/clear`) reprend le run en ne relisant que ce fichier et `sprint-status.yaml`, dans le même dossier.

## État

| Champ | Valeur |
| --- | --- |
| Mis à jour | 2026-10-17 20:55 |
| Story en cours | aucune (prochaine : 1.1) |
| Stories livrées | 0 / 56 |
| Dépense Anthropic | 0,00 $ / plafond 5 $ |
| Pilote slm-quality-bench | en cours (`pilot-report.md` absent) |
| Dernière mesure du banc | voir « Journal de surveillance » |
| Blocages | aucun |

## Consignes du run

Ordre : les stories de `sprint-status.yaml`, epics 1 à 7, dans l'ordre du fichier. Par story : `agent-cost-kit:dev-story` → `agent-cost-kit:second-avis` → `agent-cost-kit:reviewer` (avec la liste du second avis) → intégration sur `main`, puis mise à jour du sprint status et de ce fichier. Appels bloquants, une passe de revue, pas d'imbrication de sous-agents.

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

## Journal de surveillance

| Heure | Débit banc (10 min, modèle / piste) | CPU | RAM libre | Run (CPU s, RSS max, threads) | Décision |
| --- | --- | --- | --- | --- | --- |

## Journal des stories

| Story | Début | Fin | Commit | Dépense | Remarques |
| --- | --- | --- | --- | --- | --- |
