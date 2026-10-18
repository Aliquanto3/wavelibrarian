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

## Deuxième série (après-pilote, Ollama libre)

Série interrompue par consigne du coordinateur : Anaël a repris Ollama pour un autre projet. Le `wl run` était déjà terminé ; les modèles ont ensuite été déchargés (`ollama stop` sur `granite4.2:3b`, `qwen3.5:4b`, `minicpm5:1b-q4_k_m`, `ollama ps` vide). Aucun correctif de code, aucun appel Ollama après l'avis. `OMP_NUM_THREADS=4`, `CUDA_VISIBLE_DEVICES=-1`, aucune clé API chargée. Les dossiers de run sont dans le scratchpad, non commités.

| # | Vérification | Résultat | Chiffre clé |
|---|---|---|---|
| 1 | `uv run pytest -q --tb=short -m real_local` | OK | 2 passés, 1 « échec » = la sentinelle `test_real_local_deselectionne`, attendue (à écarter par `--deselect`). 29 s |
| 2 | `wl installer --profil cpu` puis `WL_HOME=<neuf> uv run wl run experiments/mini-cpu.yaml` | partiel | code de sortie 0, statut `completed`, 8 Réponses, 958 s (16 min) |
| 3 | Non-conformité de `minicpm5:1b` | mesuré, cause non investiguée | 4 Réponses sur 8 en `error` (50 %) |
| 4 | Petit `wl run` GPU | non fait | interrompu |
| 5 | Repérages 7.6 (`AUCUN_POINT_UTILE`) et 7.7 (`relevance_threshold`) | non faits | interrompus |

### Détail du run mini-cpu (2 Questions, 4 Configurations)

Commande : `WL_HOME=<scratchpad>/home1 uv run wl run experiments/mini-cpu.yaml`.

| Configuration | ok | error | Cause des erreurs |
|---|---|---|---|
| bm25 | 2 | 0 | |
| rag-naif | 1 | 1 | q-004 : sortie de `minicpm5` non conforme à `GenerateOutput` |
| raptor | 1 | 1 | q-004 : idem `GenerateOutput` |
| pageindex | 0 | 2 | q-002 et q-004 : sortie non conforme à `SelectNodesOutput` (étape `select_model`) |

- Conformité : `GenerateOutput` 2 échecs sur 6 appels de Generator (33 %), toujours sur q-004 ; `SelectNodesOutput` 2 sur 2 (100 %). PageIndex n'a donc produit aucune Réponse avec `minicpm5:1b` : à signaler comme limite du modèle, pas comme bug prouvé.
- Juges réels : tous en échec de schéma `JudgeCriteriaOutput`, `granite4.2:3b` comme `qwen3.5:4b`, sur chaque Réponse jugée. 8 Critères sans verdict de panel (message « relancer avec --reprendre »), panel admissible « aucun » pour les 4 Configurations, donc `scores.csv` sans score réel. C'est le résultat le plus important de la série : le schéma ou le prompt des Juges ne passe pas sur ces petits modèles.
- `ollama ps` (échantillons toutes les 15 s) : `minicpm5:1b-q4_k_m` 832 Mo, `100% CPU`, contexte 4096 ; `granite4.2:3b` 5,1 Go et `qwen3.5:4b` 4,2 Go, `100% CPU`, contexte 32768. Aucune couche GPU. `nvidia-smi` : 0 Mio sur tout le run. Remarque : le contexte de `minicpm5` est 4096, pas 32768 comme les juges ; à confirmer (fenêtre du Catalogue ou `num_ctx` non transmis).
- RAM : non mesurée (l'échantillonneur PowerShell a échoué à cause d'un cast). Reste à faire.
- Latences `ok` : bm25 p50 10,2 s ; rag-naif 33,5 s (n=1) ; raptor 5,1 s (n=1).
- Rapport : `report.md` complet (sections Expérience, non dominées, Profil de corpus, Juges, Inapplicables, Scores, Qualité par Type, Fraîcheur, Contaminées, Recherche, Comparaisons appariées, Coûts/énergie/latence avec Point mort, Réponses non notées) ; `pareto.csv` présent mais ses fronts reposent sur des notes issues de panels vides, à ne pas interpréter.
- Observation : `wl run` sort avec 0 et `completed` malgré PageIndex en erreur sur toutes ses Questions et un panel entièrement en échec (déjà reporté : seuil ou avertissement à décider).

### Reste à faire (Ollama doit être libre)

1. Cause des non-conformités `JudgeCriteriaOutput` : appeler un Juge (`granite4.2:3b`) sur une Réponse de bm25 et inspecter la sortie brute et le `format` envoyé (schéma JSON de `JudgeCriteriaOutput`, prompt, troncature, balise de réflexion de `qwen3.5`). Relance : `WL_HOME=<dossier> uv run wl run --reprendre <id>` sur le run existant pour ne refaire que le jugement.
2. Cause des non-conformités `GenerateOutput` (q-004) et `SelectNodesOutput` de `minicpm5:1b` : même méthode ; tester `minicpm5` avec `format` = schéma contre un Generator plus gros (`granite4.2:3b`).
3. Mesurer la RAM pendant `wl run` (échantillonner `Win32_OperatingSystem.FreePhysicalMemory` sans cast en `[int]`).
4. Profil `gpu` : voir si une Expérience l'utilise (aucune dans `experiments/` à ce jour : seulement `mini-cpu`, `mini-real-haiku`, `mini-test`) ; sinon pas de contrôle GPU.
5. 7.6 et 7.7 : Expérience ad hoc sur 3 à 5 Questions du Mini-corpus (graphrag global, lazy_graphrag), distribution des notes et recommandation de seuil. Aucune donnée collectée.

### Recommandations (provisoires)

- Seuil lazy_graphrag : aucune donnée ; garder 0,4 par défaut jusqu'à mesure (plage à tester 0,3 à 0,5).
- Generator CPU : `minicpm5:1b` échoue au schéma dans un tiers des appels et sur tous ceux de PageIndex ; prévoir un Generator de 3-4 B (`granite4.2:3b`, 5,1 Go à 32 768) ou des relances, après avoir vérifié le `format` Ollama.

## Troisième série (correctif des sorties structurées)

Code testé : `fix-juges-schema` à `f0762bc` (`inline_refs`, `think: false`, `clean_content`). `OMP_NUM_THREADS=4`, `CUDA_VISIBLE_DEVICES=-1`, un seul serveur Ollama, aucune API Anthropic. Aucun changement de code dans cette série. Run et script d'essai dans le scratchpad, non commités.

### Test express (un appel par rôle, `OllamaProvider`, vrai schéma, 3 Critères pour le Juge)

| Appel | Avant | Après | Tokens (entrée / sortie) |
|---|---|---|---|
| Juge `granite4.2:3b` (`JudgeCriteriaOutput`) | KO | OK, 25 s | 209 / 259 |
| Juge `qwen3.5:4b` | KO | OK, 16 s | 193 / 156 |
| `minicpm5:1b` `SelectNodesOutput` | KO | OK, 2 s | 74 / 23 |
| `minicpm5:1b` `GenerateOutput` | KO (33 %) | OK, 1 s | 61 / 30 |

`think: false` est accepté sans erreur HTTP par granite et minicpm (modèles sans réflexion). Les trois Critères reçoivent un verdict.

### Run de bout en bout (`WL_HOME=<neuf> wl run experiments/mini-cpu.yaml`)

| Mesure | Avant (2e série) | Après |
|---|---|---|
| Durée | 958 s | 9 min 30 s |
| Réponses ok / error | 4 / 4 | 7 / 1 |
| Critères sans verdict | 8 (tous) | 0 (49 lignes de verdicts) |
| Panel admissible | aucun pour les 4 Configurations | `granite4.2:3b` + `qwen3.5:4b` pour les 4 (égalités : 1 pour rag-naif et raptor) |
| `GenerateOutput` non conforme | 2 sur 6 appels | 0 |
| `SelectNodesOutput` non conforme | 2 sur 2 | 2 appels non conformes, une seule Question (q-004) |
| PageIndex | 0 Réponse | q-002 ok (qualité 1,00), q-004 en erreur |
| Contexte `ollama ps` de minicpm5 | 4096 | 32768 (le `num_ctx` du Catalogue est maintenant transmis) |
| `pareto.csv` | non interprétable | lisible (fronts qualité-coût et qualité-énergie ; bm25 et pageindex non dominés, rag-naif et raptor dominés) |

Critères d'acceptation atteints : plus aucun « Critère sans verdict », panel admissible non vide. `scores.csv` porte des scores réels (bm25 0,50 ; rag-naif 0,50 ; raptor 0,50 ; pageindex 1,00 sur n = 1, tous avec n très petit).

Reste : PageIndex q-004. Les deux essais de `minicpm5:1b` à l'étape `pageindex.select.1` s'arrêtent à `output_tokens = 256` = `select_max_tokens` (entrée 1932 tokens) : la sortie est tronquée, très probablement une dégénérescence répétitive de la liste `node_ids` d'un modèle de 1 B, plutôt qu'un défaut de schéma. Non investigué davantage (hors critères) ; pistes : `select_max_tokens` plus haut, `repeat_penalty` dans `ollama.options`, ou un `select_model` de 3-4 B. `wl run` sort toujours avec 0 et `completed` malgré cette erreur (seuil ou avertissement à décider, déjà reporté).

Fin de vérification : `ollama stop` sur les trois modèles, `ollama ps` vide.
