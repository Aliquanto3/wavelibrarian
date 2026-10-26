# Vérifications réelles du 2026-10-26 (lot v0.3.0, stories 9.9 à 9.11)

Windows 11. `WL_HOME` = `C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0` (hors dépôt, non commité). Commandes lancées depuis la racine du dépôt principal (`.env`), avec `uv run --extra energy` : sans l'extra, `wl calibrer` s'arrête au démarrage (« installer l'extra energy »), avant tout appel.

| # | Vérification | Résultat | Sortie |
|---|---|---|---|
| a | 9.9 : calibration d'Opus avec le prompt du lot (justification courte, `na`), 5 passes | `claude-opus-5-5` au-dessus du seuil sur les 3 Critères : 1,00 / 0,72 / 0,76 ; 3,32 USD | `calibration-opus.json` → `corpora/minicorpus/calibration/opus.json` |

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

## Dépense API du lot

| Étape | USD |
|---|---|
| 9.9 calibration d'Opus | 3,32 |
| **Total** | **3,32 / 10** |
