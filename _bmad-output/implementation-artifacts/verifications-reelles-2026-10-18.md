# Vérifications réelles du 2026-10-18

Worktree `wavelibrarian-wt-verif`, branche `verif-reelle`, depuis `8b30f60`. Windows 11, CPU seul pour le profil `cpu`.

| # | Vérification | Résultat | Preuve |
|---|---|---|---|
| 1 | Ollama | OK | `/api/version` : `0.40.5` ; `ollama list` : 31 modèles, dont `granite4.2:3b` (2,2 Go), `minicpm5:1b-q4_k_m`, `nomic-embed-text`. Aucun `pull`. |
| 2 | `uv sync --extra local`, `wl installer --profil cpu` | OK | sync code 0 ; installer code 0 : tiktoken `o200k_base` prêt, embedder `intfloat/multilingual-e5-small` téléchargé (cache HF 2,2 Go : le dépôt contient 43 fichiers, dont les variantes onnx/openvino), modèles Ollama du profil tous présents. |
| 3 | `embedder_installe('intfloat/multilingual-e5-small')` | OK | `True`. |
| 4 | `pytest -m real_local` | OK après correction | Voir défaut 1 : sockets bloqués, 2 tests sur 2 passent après correction (16 s). `test_real_local_deselectionne` est une sentinelle qui échoue exprès si elle tourne : l'écarter avec `--deselect`. `ollama ps` : `minicpm5:1b-q4_k_m` 832 Mo `100% CPU`, contexte 4096 (le test n'envoie pas `num_ctx`). `granite4.2:3b` appelé avec `num_gpu: 0` et `num_ctx: 32768` : `100% CPU`, contexte 32768, 5,1 Go de mémoire (poids 2,2 Go + cache KV). `nvidia-smi` : 0 Mio utilisés. |
| 5 | `wl run` sur une Expérience `cpu` | n/a | Pas de dossier `experiments/` (attendu en story 4.14). |
| 6 | Énergie, extra `energy` | OK après correction | codecarbon 3.3.1. `_hardware` et `_mode` existent (`RAM`, `GPU`, `CPU` en mode `windows_emi`). Avec `gpu_ids=[]`, aucun processus python dans `nvidia-smi`. Méthode `measured` avant correction (défaut 2), `estimated` après. |
| 7 | API Anthropic | n/a | Non appelée (story 4.15). |

## Défauts

1. **Corrigé.** `addopts = --disable-socket` bloquait les tests `real_local` et `real_api` (`SocketBlockedError`), qui ne pouvaient donc jamais joindre Ollama. `tests/conftest.py` pose maintenant `enable_socket` sur les tests marqués `real_local` ou `real_api` ; test dans `test_garde_fous.py`.
2. **Corrigé.** `is_hardware_counter` comptait tout objet `GPU` comme compteur matériel. codecarbon 3.3.1 en instancie un même avec `gpu_ids=[]`, donc la méthode valait toujours `measured`. Il faut désormais que `gpu_ids` soit non vide ; test ajouté.

## Point à trancher (non modifié)

Sous Windows, codecarbon 3.3.1 lit le CPU par `windows_emi` (Energy Meter Interface), un compteur matériel absent de `_MODES_MATERIELS`. La méthode vaut donc `estimated` ici, alors que la mesure CPU vient d'un compteur. Si la story 1.7 veut `measured` dans ce cas, il faut ajouter `windows_emi` à l'ensemble.

## Téléchargements

Embedder `multilingual-e5-small` : environ 2,2 Go (cache HF), plus torch CPU et dépendances Python (extras `local` et `energy`). Aucun modèle Ollama.
