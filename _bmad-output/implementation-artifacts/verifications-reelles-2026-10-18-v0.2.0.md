# Vérifications réelles du 2026-10-18 (lot v0.2.0, story 8.8)

Worktree `wl-wt-8-8`, branche `story/8-8`, depuis `main` à `3d67958`. Windows 11, profil `cpu` (Ollama sans couche GPU, `CUDA_VISIBLE_DEVICES=-1`). `WL_HOME` = `C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0` (hors dépôt, non commité). Cette synthèse ne fait aucun appel API ni Ollama : elle lit les fichiers des runs. Heures du `run.log` et de `ram.log` en heure locale (UTC+2) ; le manifeste est en UTC.

| # | Vérification | Résultat | Run |
|---|---|---|---|
| a | `experiments/mini-cpu.yaml` sans `max_questions`, 19 Questions du split dev, 4 Configurations | 76 / 76 Réponses `ok` ; `completed_with_errors` résiduel (7 Critères sans verdict) | `20261018-115941-a2a512` |
| b | 3 échecs de Juges restants | Sorties tronquées au budget : justifications trop longues | idem |
| c | Balayage `relevance_threshold` {0,1 ; 0,3 ; 0,5} (`experiments/lazy-seuil-cpu.yaml`) | `completed`, 57 Réponses, **non discriminant** : 0 Passage retenu aux trois seuils | `20261018-131800-492c48` |
| d | Limites | Voir section (d) | |

## (a) mini-cpu sur tout le split dev

**Source de la story 8.9 : `run_id` `20261018-115941-a2a512`.**

- Durée. Exécution initiale : 13:59:43 à 15:17:49, soit 1 h 18 min (index et requêtes jusqu'à 14:11:22, soit 11 min 39 s ; jugement des 76 Réponses de 14:11 à 15:17, soit 66 min). Budget des Juges d'alors : `120 × Critères + 60`, d'où 55 Critères sans verdict. Reprise après le correctif fix-8-8 : 16:14:59 à 16:31:04, soit 16 min 05 s. Total 1 h 34 min.
- RAM. `ram.log` (146 relevés, un par minute, 13:59 à 16:30). RAM libre : 18,9 Go au départ, maximum 22,1 Go, **minimum 0,34 Go à 14:33:14** (jugement de l'exécution initiale). Sous 1 Go pendant 17 relevés (premier à 14:29, dernier à 15:25, ce dernier pendant le jugement du balayage), sous 2 Go pendant 24, sous 3 Go pendant 32. Le « ~1,2 Go vers 14:27 » n'est qu'un palier de la descente (1,24 Go à 14:28, 0,74 Go à 14:29). **Modèles chargés et `size_vram` non relevés** : la colonne `ollama=` de `ram.log` est vide (le relevé de `/api/ps` a échoué sur une erreur de guillemets, le script a continué). Référence des séries précédentes : `granite4.2:3b` 5,1 Go et `qwen3.5:4b` 4,2 Go à 32 768 de contexte (9,3 Go à eux deux), `minicpm5:1b-q4_k_m` 1,6 Go, tous `100% CPU`, `size_vram` nul. La saturation vient des Juges chargés ensemble en plus du Generator, sans GPU.
- Dépense : 0 $ API (budget `per_run` Anthropic à 0,00 ; somme des `wl.cost` d'un fournisseur réel : 0,0000 €). Possession du calcul local : 0,0119 € (rapport).
- Réponses : bm25 19 ok / 0 error ; rag-naif 19 / 0 ; raptor 19 / 0 ; pageindex 19 / 0.
- Verdicts : 549 lignes dans `verdicts.jsonl` (204 critères automatiques, 173 de `granite4.2:3b`, 172 de `qwen3.5:4b`), 373 lignes de panel ; panel admissible `granite4.2:3b` + `qwen3.5:4b` pour les 4 Configurations ; égalités 14 / 12 / 11 / 13. **7 Critères sans verdict** après la reprise (2 rag-naif, 2 raptor, 3 pageindex), voir (b) ; la reprise a ramené les 55 Critères d'avant correctif à 7.
- Appels de Juge (spans `judge`) : 204 ; 149 ok et 55 `non_conformant` à l'exécution initiale (tous à 300 ou 420 tokens), puis 8 spans `non_conformant` à la reprise (budgets 500 et 700).

Scores, phase `base`, palier `all`, taux de oui avec IC bootstrap à 95 % ; n = 19 Questions, sauf mention :

| Configuration | Qualité | correctness | completeness | faithfulness | citation_correctness | abstention_correctness |
|---|---|---|---|---|---|---|
| bm25 | 0,26 [0,11 ; 0,47] | 0,26 [0,11 ; 0,47] | 0,42 [0,21 ; 0,63] | 0,47 [0,26 ; 0,68] | 0,53 [0,32 ; 0,74] | 0,84 [0,68 ; 1,00] |
| rag-naif | 0,32 [0,11 ; 0,53] | 0,32 [0,11 ; 0,53] | 0,44 [0,22 ; 0,67] (n = 18) | 0,50 [0,28 ; 0,72] (n = 18) | 0,63 [0,42 ; 0,84] | 0,89 [0,74 ; 1,00] |
| raptor | 0,37 [0,16 ; 0,58] | 0,37 [0,16 ; 0,58] | 0,50 [0,28 ; 0,72] (n = 18) | 0,61 [0,39 ; 0,83] (n = 18) | 0,58 [0,37 ; 0,79] | 0,89 [0,74 ; 1,00] |
| pageindex | 0,33 [0,11 ; 0,56] (n = 18) | 0,28 [0,11 ; 0,50] (n = 18) | 0,50 [0,28 ; 0,72] (n = 18) | 0,61 [0,39 ; 0,83] (n = 18) | 0,21 [0,05 ; 0,42] | 0,63 [0,42 ; 0,84] |

Les IC se recouvrent tous : aucune Configuration n'est séparable des autres sur 19 Questions. Latence des Réponses `ok` (rapport) : bm25 p50 3,97 s / p95 5,8 s ; rag-naif 3,66 / 5,98 ; raptor 3,67 / 8,29 ; pageindex 15,6 / 26,2 s (sélection par `granite4.2:3b`, décision 8.7). Front Qualité × coût : raptor seule non dominée.

Comparaison à la 3e série (même Expérience limitée à 2 Questions, correctif `fix-juges-schema`) : bm25 0,50, rag-naif 0,50, raptor 0,50, pageindex 1,00, avec n = 1 à 2. Ces valeurs ne se retrouvent pas sur 19 Questions (0,26 à 0,37 ; pageindex 0,33) : 2 Questions ne permettaient pas de classer. Côté exécution : 7 ok / 1 error sur 8 Réponses (PageIndex q-004 en erreur) devient 76 / 76 ; la durée passe de 9 min 30 s (8 Réponses) à 1 h 34 min (76 Réponses), le jugement dominant.

## (b) Les 3 échecs de Juges restants

Données : spans `judge` de `traces.jsonl` (attribut `wl.raw_output`, 2 000 premiers caractères de la sortie brute des spans `non_conformant`) et `run.log`.

| Réponse | Juge | Critères (budget `200 × n + 100`) | Tokens d'entrée | Tokens de sortie | Essais |
|---|---|---|---|---|---|
| rag-naif / q-044 | `qwen3.5:4b` | 2 (500) | 1 873 | **500** | 2, sortie identique (2 029 caractères) |
| raptor / q-044 | `qwen3.5:4b` | 2 (500) | 1 873 | **500** | 2, idem |
| pageindex / q-017 | `granite4.2:3b` | 3 (700) | 559 | **700** | 2 (2 059 et 2 079 caractères) |

Les 8 spans `non_conformant` de la reprise s'arrêtent tous exactement au budget (500 ou 700). Le huitième, rag-naif / q-011 chez `granite4.2:3b` (500 tokens), est couvert par le verdict de `qwen3.5:4b` et ne laisse aucun Critère sans verdict. L'autre Juge avait rendu une sortie conforme sur ces Réponses : granite sur q-044 rag-naif et raptor 272 tokens, qwen sur q-017 pageindex 217 tokens.

Sortie brute : un JSON bien formé jusqu'à la coupure, dont les champs `justification` partent en délibération. Qwen sur q-044, après deux justifications correctes : « on pourrait considérer que la réponse est 'no' pour correctness car elle est factuellement erronée dans le contexte du jeu (elle a été remplacée), mais 'yes' pour faithfulness si l'on considère [...] ou 'no' si l'on considère que dire 'Tamsin Orrelle' quand il » (coupure). Granite sur q-017 : « le critère de faithfulness est généralement appliqué à la r » (coupure), après un raisonnement circulaire entre `reference_answer` et `contexte_texts`.

Lien avec q-044 : Question de type `factual` (« Qui succède à Tamsin Orrelle [...] ? », référence « Ilsa Marenne ») qui cible l'opération `op-1` du Scénario de mise à jour ; son Ancrage de référence est `chronique-1415.md`, document créé par le Scénario et absent du Corpus de la phase `base`, d'où l'avertissement de `export.out` (Ancrage non résolu, métriques sur les seuls Ancrages résolus). En phase `base`, aucune Configuration ne peut lire la réponse : les Réponses (« Tamsin Orrelle », l'ancien titulaire) sont contredites par la référence et absentes du contexte, et un petit Juge délibère sans conclure. Le lien est donc réel pour q-044. **Il n'explique pas q-017** : son Ancrage est résolu, mais le contexte de PageIndex (559 tokens) ne contient pas le fait de la référence, même désaccord entre Réponse, contexte et référence, même dérive.

Cause probable (non corrigée) : quand la Réponse, le contexte et la référence se contredisent, les Juges de 3 à 4 B écrivent un raisonnement dans `justification` jusqu'à la limite de tokens ; le budget de 200 tokens par Critère ne borne pas la longueur d'une justification, et élever le budget ne ferait que repousser la coupure. Pistes pour une story ultérieure : consigne de justification en une phrase dans le prompt du Juge, ou schéma sans `justification`. Aucune n'est implémentée ici.

## (c) Balayage de `relevance_threshold` (LazyGraphRAG, split dev)

Run `20261018-131800-492c48`, `experiments/lazy-seuil-cpu.yaml` : 3 Configurations (`lazy-seuil-01`, `-03`, `-05`), Generator et Decider `minicpm5:1b-q4_k_m`, un seul index (`3470b8772d62b6a2`, 7 s). Lancé à 15:18 avec l'ancien budget des Juges (par le premier script, non prévu à ce moment), fin des Réponses à 15:21:48, jugement jusqu'à 15:28:31 (`completed_with_errors`, 3 Critères sans verdict par Configuration), puis reprise après fix-8-8 à 16:31:42 en 31 s (`run.log`) : `completed`, 57 Réponses `ok`, 0 $ API.

| Seuil | Réponses | Passages retenus par Question | Abstentions | Recall@5 / MRR / nDCG | Qualité [IC] | Latence (spans `answer`) |
|---|---|---|---|---|---|---|
| 0,1 | 19 | 0 (min 0, max 0) | 19 sur 19 | 0,000 (n = 17) | 0,32 [0,11 ; 0,53] | p50 12,2 s, max 18,6 s ; étape 3 min 32 s |
| 0,3 | 19 | 0 | 19 sur 19 | 0,000 (n = 17) | 0,32 [0,11 ; 0,53] | p50 12,1 s (rejeu) ; étape 1,3 s |
| 0,5 | 19 | 0 | 19 sur 19 | 0,000 (n = 17) | 0,32 [0,11 ; 0,53] | p50 12,1 s (rejeu) ; étape 2,0 s |

- **Le balayage ne discrimine rien.** Les 57 Réponses sont des abstentions (`text` vide, aucun Passage retenu, aucun appel `generate`). Cause identifiée : le Decider `minicpm5:1b` note **0,0 chaque Passage**. Les 64 réponses `grade_relevance` du Cache (16 Questions × 4 lots de 5 Passages, 29 tokens de sortie) sont toutes `{"scores": [0.0, 0.0, 0.0, 0.0, 0.0]}`. Les 3 autres Questions (q-017, q-033, q-036) n'ont aucune communauté qui touche la Question : abstention sans appel. Aucun seuil entre 0,1 et 0,5 ne peut retenir un Passage noté 0.
- Latence : réellement mesurée pour le seuil 0,1 seulement (3 min 32 s pour les 16 Questions notées, 64 appels de Decider, environ 3 s chacun d'après les premiers spans, 9,4 s pour le tout premier). Les seuils 0,3 et 0,5 relisent les notes du Cache (`wl.llm_cache_hit` vrai sur 100 % de leurs spans `grade`) et rejouent la latence d'origine dans `latency_s` : les trois latences sont identiques par construction et ne dépendent pas du seuil.
- Scores à lire avec précaution : les Juges accordent `completeness` 0,74 [0,53 ; 0,89] et `faithfulness` 0,89 [0,74 ; 1,00] à des Réponses vides, et `correctness` 0,26 (5 Réponses sur 19) ; `citation_correctness` et `abstention_correctness` 0,05 [0,00 ; 0,16]. Un `correctness` positif sur une abstention est un faux positif de Juge de 3 à 4 B, pas un score d'architecture. Valeurs identiques aux trois seuils, à la borne basse de l'IC de `correctness` près (0,05 contre 0,10, jugements non rejoués à l'identique).
- Conclusion chiffrée : à 0,1, 0,3 et 0,5, 0 Passage retenu sur 19 Questions, 19 abstentions, recall 0 ; la mesure ne justifie aucune valeur. La valeur par défaut 0,1 de `lazy_graphrag.py` est inchangée (décision d'Anaël). Le facteur limitant est le Decider `minicpm5:1b`, pas le seuil. Pour mesurer le seuil : refaire le balayage avec un Decider `granite4.2:3b` (18 à 20 s par appel de sélection dans l'étude 8.7, 5,1 Go), soit environ 64 appels pour le seul seuil 0,1, de l'ordre de 20 min ; non fait ici, hors périmètre.

## (d) Limites

- Énergie du run initial mal étiquetée : 309 spans `wl.energy_source=nvml` (et 1 `windows_emi`) alors que le GPU était désactivé ; cause (codecarbon remet le GPU à partir du 2e tracker) et correctif dans `fix-8-8-juges-tronques-et-source-energie.md`. Ces spans sont à relire comme `windows_emi`, et leur énergie incluait le GPU au repos. Le correctif est vérifié en réel (3 phases `measured` / `windows_emi`), mais ce run n'a pas été rejoué en entier : les kWh du rapport de mini-cpu pour les phases d'index et de requête de l'exécution initiale restent ceux d'avant correctif. Même défaut dans le balayage lancé avant le correctif.
- Poste `judging` non mesuré : 156 spans `judge` `unknown` / `unknown` (aucune phase d'énergie ouverte pour les Juges locaux), 22 hits de Cache sans énergie. Le jugement dure 66 min de l'exécution initiale et n'entre ni dans l'énergie ni dans la possession : l'énergie totale du run est sous-estimée.
- Incident mémoire : la RAM libre est passée sous 1 Go dès 14:29 (minimum 0,34 Go à 14:33). Le script qui enchaînait les deux runs a été arrêté par Claude Code à 14:42 (mémoire système critique) ; le processus `wl run` de mini-cpu a survécu et a fini. Le même script avait lancé seul `lazy-seuil-cpu` (ancien budget des Juges, ancienne étiquette d'énergie) ; les processus orphelins ont été arrêtés à la fin (16:33), `ollama ps` vide. L'ordre prévu (fix, reprise, paquet, balayage) n'a donc pas été tenu à la lettre ; le balayage a été repris après le correctif.
- `ram.log` sans `ollama ps` : modèles chargés et `size_vram` de ce run non relevés (l'absence de couche GPU vient des séries précédentes : `100% CPU`, `nvidia-smi` 0 Mio).
- Cache de réponses : les verdicts de l'ancien budget (clé avec `max_tokens`) ne sont pas relus ; la reprise a rejugé, ses verdicts peuvent différer de ceux de l'exécution initiale.
- Scores de LazyGraphRAG non interprétables (voir c). `calibration.json` absent : le Rapport affiche « Calibration absente », en attente de l'annotation d'Anaël (story 8.10).

## Paquet d'annotation (story 8.9)

`corpora/minicorpus/annotations/anael.yaml` : 40 Réponses (92 lignes Réponse × Critère), 0 doublement annotée, un fichier de 304 Ko, tirées du run `20261018-115941-a2a512` (`completed_with_errors` après la reprise). Sortie de la commande (`export.out`) : « Paquet de 40 Réponse(s) dont 0 doublement annotée(s), 1 fichier(s) dans corpora\minicorpus\annotations », avec l'avertissement sur l'Ancrage de référence non résolu de q-044.
