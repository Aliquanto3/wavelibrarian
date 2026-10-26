# Vérifications réelles du 2026-10-26 (lot v0.3.0, stories 9.9 à 9.11)

Windows 11. `WL_HOME` = `C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0` (hors dépôt, non commité). Commandes lancées depuis la racine du dépôt principal (`.env`), avec `uv run --extra energy` : sans l'extra, `wl calibrer` s'arrête au démarrage (« installer l'extra energy »), avant tout appel.

| # | Vérification | Résultat | Sortie |
|---|---|---|---|
| a | 9.9 : calibration d'Opus avec le prompt du lot (justification courte, `na`), 5 passes | `claude-opus-5-5` au-dessus du seuil sur les 3 Critères : 1,00 / 0,72 / 0,76 ; 3,32 USD | `calibration-opus.json` → `corpora/minicorpus/calibration/opus.json` |
| b | 9.10 : rejugement du run mini-cpu par Opus, Juge unique, 18 Questions dev | `completed`, 72 Réponses, 0 Critère sans verdict ; 0,43 USD ; IC recouvrants | `20261026-093758-1afc6b` |

## (a) Calibration d'Opus (story 9.9)

Commande :

```
WL_HOME=C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0 uv run --extra energy wl calibrer experiments/calibration-opus.yaml --annotations corpora/minicorpus/annotations --run 20261018-115941-a2a512 --sortie C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0/runs/20261018-115941-a2a512/calibration-opus.json
```

- Exécution annotée : `20261018-115941-a2a512` (run mini-cpu de la 8.8). Annotations : `anael.yaml` après la 9.3 (5 fidélités de Réponses vides passées à `na`). Gel b2 : les 4 lignes de q-044 sont ignorées (88 lignes sur 92), comme prévu (limite (iv) de `fix-arbitrages-8-3-8-8`).
- Juges : `claude-opus-5-5` et `claude-haiku-5-5` (`wl calibrer` exige un Panel admissible de 2 Juges ; Haiku coûte quelques centimes). 5 passes (FR-38). Plafond `per_run` 5,00 USD.
- 354 appels, de 10:20 à 10:35 environ. **Coût : 3,32 USD** (Poste `judging`). Aucun appel servi par le Cache : le prompt et le schéma des Juges ont changé (9.2, 9.3).

| Juge | Critère | n | Kappa | Instabilité | `na` (accords / désaccords) | Kappa 8.11 (réannotation) |
|---|---|---|---|---|---|---|
| claude-opus-5-5 | correctness | 12 | **1,00** | 0,00 | 0 / 0 | 1,00 |
| claude-opus-5-5 | completeness | 38 | **0,72** | 0,00 | 0 / 0 | 0,73 |
| claude-opus-5-5 | faithfulness | 28 | **0,76** | 0,03 | 5 / 5 | 0,84 (0,80 sans les Réponses vides) |
| claude-haiku-5-5 | correctness | 9 | 1,00 | 0,00 | 0 / 0 | 0,55 |
| claude-haiku-5-5 | completeness | 34 | 0,61 | 0,13 | 0 / 0 | 0,14 |
| claude-haiku-5-5 | faithfulness | 25 | 0,64 | 0,32 | — | 0,64 |

- **Opus reste au-dessus du seuil de 0,6 sur les trois Critères** : il peut être Juge unique calibré (story 9.5). Son instabilité est quasi nulle (une Réponse sur 38 change de verdict en fidélité entre passes).
- Fidélité : le kappa est calculé hors `na`, sur 28 items. Les 5 accords `na` sont les 5 Réponses vides de PageIndex (`na` automatique, sans appel). Les 5 désaccords `na` sont des Réponses non vides où Opus a répondu `na` (rien de vérifiable affirmé) alors qu'Anaël avait dit oui ou non : à regarder en recette (la consigne de la page de réannotation ne proposait pas « sans objet »).
- Haiku passe désormais le seuil (correctness 1,00, completeness 0,61, faithfulness 0,64), mais de justesse et avec une instabilité forte (0,13 et 0,32) et 28 sorties non conformes sur ses appels. Il n'est pas retenu.
- `opus.json` est versionné (Mini-corpus fictif, publiable) et référencé par `judges.excluded_from` de `mini-cpu.yaml` et `lazy-seuil-cpu.yaml` (bascule de la story 9.5, plafonds 3,00 et 2,00 USD).

## (b) Rejugement du run mini-cpu par Opus (story 9.10)

Commande (aucun appel Ollama : Réponses copiées, préflight des seuls Juges) :

```
WL_HOME=C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0 uv run --extra energy wl rejuger 20261018-115941-a2a512 experiments/mini-cpu.yaml
```

- Exécution `20261026-093758-1afc6b`, `rejudged_from: 20261018-115941-a2a512`, de 10:37:56 à 10:39:09 (1 min 13). Statut `completed`, code 0. q-044 écartée (hors du split dev depuis le Gel b2) : 18 Questions × 4 Configurations = 72 Réponses, toutes `ok`, 0 Critère sans verdict, 0 égalité (Juge unique).
- 72 appels de Juge, dont **47 servis par le Cache** : la passe 0 de la calibration 9.9 a posé les mêmes requêtes sur les 40 Réponses annotées. **Coût : 0,43 USD** (Registre), plafond 3,00 USD.
- Rapport : mention « Juge unique calibré » avec les kappas d'`opus.json` ; coûts, énergie et latence de génération marqués « copiés de `20261018-115941-a2a512` ».

Scores, phase `base`, palier `all`, taux de oui avec IC bootstrap à 95 %, n = 18 Questions (fidélité hors `na`) :

| Configuration | Qualité | correctness | completeness | faithfulness | citation_correctness | abstention_correctness |
|---|---|---|---|---|---|---|
| bm25 | 0,28 [0,06 ; 0,50] | 0,28 [0,06 ; 0,50] | 0,22 [0,06 ; 0,44] | 0,33 [0,13 ; 0,53] (n 15, 3 na) | 0,56 [0,33 ; 0,78] | 0,83 [0,67 ; 1,00] |
| rag-naif | 0,22 [0,06 ; 0,44] | 0,22 [0,06 ; 0,44] | 0,17 [0,00 ; 0,33] | 0,40 [0,13 ; 0,67] (n 15, 3 na) | 0,67 [0,44 ; 0,89] | 0,89 [0,72 ; 1,00] |
| raptor | 0,22 [0,06 ; 0,44] | 0,22 [0,06 ; 0,44] | 0,17 [0,00 ; 0,33] | 0,43 [0,14 ; 0,71] (n 14, 4 na) | 0,61 [0,39 ; 0,83] | 0,89 [0,72 ; 1,00] |
| pageindex | 0,22 [0,06 ; 0,44] | 0,17 [0,00 ; 0,33] | 0,17 [0,00 ; 0,39] | 0,40 [0,10 ; 0,70] (n 10, 8 na) | 0,22 [0,06 ; 0,44] | 0,67 [0,44 ; 0,89] |

Comparaison au jugement de la 8.8 (granite4.2:3b + qwen3.5:4b, 19 Questions, `verifications-reelles-2026-10-18-v0.2.0.md` (a)) :

| Configuration | Qualité 8.8 → 9.10 | completeness 8.8 → 9.10 | faithfulness 8.8 → 9.10 |
|---|---|---|---|
| bm25 | 0,26 → 0,28 | 0,42 → 0,22 | 0,47 → 0,33 |
| rag-naif | 0,32 → 0,22 | 0,44 → 0,17 | 0,50 → 0,40 |
| raptor | 0,37 → 0,22 | 0,50 → 0,17 | 0,61 → 0,43 |
| pageindex | 0,33 → 0,22 | 0,50 → 0,17 | 0,61 → 0,40 |

- Les Juges locaux étaient indulgents : Opus divise par 2 à 3 les taux de completeness et baisse la fidélité de 0,1 à 0,2. La Qualité (correctness, en grande partie par correspondance exacte) baisse moins ; RAPTOR, en tête à la 8.8, rejoint les autres.
- **Aucune Configuration n'est séparable** : IC recouvrants, McNemar p = 1,00 sur toutes les paires (n_common 18). Sur 18 Questions et avec un Generator de 1 B, le banc mesure surtout la faiblesse du Generator ; pour classer les Architectures, il faut plus de Questions ou un Generator plus capable.
- Fidélité : 18 `na` sur 72, dont 8 pour PageIndex (Réponses vides ou abstentions, `na` automatique, et `na` d'Opus pour une Réponse qui n'affirme rien).
- Énergie et coût de génération : ceux de la source (énergie de l'exécution initiale étiquetée `nvml` à tort avant fix-8-8, limite (d) de la série du 18/10). Le jugement d'API est estimé (EcoLogits).

## Dépense API du lot

| Étape | USD |
|---|---|
| 9.9 calibration d'Opus | 3,32 |
| 9.10 rejugement mini-cpu | 0,43 |
| **Total** | **3,75 / 10** |
