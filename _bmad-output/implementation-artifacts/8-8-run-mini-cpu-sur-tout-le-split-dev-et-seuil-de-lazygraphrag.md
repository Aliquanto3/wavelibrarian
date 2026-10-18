---
story: "8.8"
title: "Run mini-cpu sur tout le split dev et seuil de LazyGraphRAG"
status: review
---

# Story 8.8 : Run mini-cpu sur tout le split dev et seuil de LazyGraphRAG

Exigences : FR-1, FR-26 ; SM-3 ; arbitrage P8. Story réelle (Ollama, profil `cpu`), sans code produit : le défaut révélé par le run est traité dans `fix-8-8-juges-tronques-et-source-energie.md` (intégré, `360ea0f`). Détail et chiffres : `verifications-reelles-2026-10-18-v0.2.0.md`.

## Réalisé

- `experiments/mini-cpu.yaml` : sans `max_questions` (19 Questions du split dev), 4 Configurations (bm25, rag-naif, raptor, pageindex avec `select_model` granite4.2:3b, décision 8.7). Run `20261018-115941-a2a512` lancé le 2026-10-18 à 13:59 (heure locale), `WL_HOME` hors dépôt. **Ce `run_id` est la source de la story 8.9** (`corpora/minicorpus/annotations/anael.yaml`).
- `experiments/lazy-seuil-cpu.yaml` : 3 Configurations LazyGraphRAG (`relevance_threshold` 0,1 ; 0,3 ; 0,5) sur le split dev, index partagé. Run `20261018-131800-492c48`.
- Aucun code, aucune Expérience, aucune valeur par défaut modifiés par cette synthèse.

## Résultats

| Mesure | mini-cpu (`20261018-115941-a2a512`) | lazy-seuil-cpu (`20261018-131800-492c48`) |
|---|---|---|
| Durée | 1 h 18 min initiale + 16 min de reprise (après fix-8-8) | 10 min 29 s initiale + 31 s de reprise |
| RAM libre | 22,1 Go max ; minimum 0,34 Go (14:33) ; sous 1 Go sur 17 relevés | sous 1 Go à 15:25 (jugement) |
| Dépense | 0 $ API | 0 $ API |
| Réponses | 76 `ok` / 0 `error` (19 par Configuration) | 57 `ok` / 0 `error` |
| Statut final | `completed_with_errors` (7 Critères sans verdict) | `completed` |
| Qualité (IC 95 %, n = 19) | bm25 0,26 [0,11 ; 0,47] ; rag-naif 0,32 [0,11 ; 0,53] ; raptor 0,37 [0,16 ; 0,58] ; pageindex 0,33 [0,11 ; 0,56] (n = 18) | 0,32 [0,11 ; 0,53] aux trois seuils |

- mini-cpu : IC tous recouverts, aucune Configuration séparable. Avant fix-8-8, 55 Critères sans verdict (48 sorties de Juges tronquées au budget `120 × n + 60`) ; après, 7.
- lazy-seuil-cpu : **0 Passage retenu sur 19 Questions aux trois seuils**, 19 abstentions par seuil, recall 0. Le Decider `minicpm5:1b` note 0,0 tous les Passages (64 réponses de Cache identiques `{"scores": [0.0 x 5]}`) ; 3 Questions (q-017, q-033, q-036) n'ont aucune communauté candidate. La latence ne dépend pas du seuil (notes et latences relues du Cache aux seuils 0,3 et 0,5). Balayage non discriminant.
- RAM : modèles chargés et `size_vram` non relevés (relevé `ollama ps` défaillant) ; saturation due aux deux Juges chargés avec le Generator sans GPU.

## Acceptance Criteria

1. `mini-cpu` sans `max_questions` : Réponses `ok` pour les 4 Configurations (76 / 76), mais statut `completed_with_errors` et non `completed` : 7 Critères sans verdict. Causes analysées (sorties de Juges tronquées au budget), consignées et soumises à Anaël ci-dessous avant `done`.
2. Balayage {0,1 ; 0,3 ; 0,5} exécuté, scores, nombre de Passages retenus et latence par seuil consignés dans la série datée ; valeur par défaut inchangée.
3. `run_id`, durée, RAM et dépense consignés ; `run_id` noté comme source de 8.9.

## Reports

- Énergie du Poste `judging` non mesurée (156 spans `unknown`) et énergie du run initial étiquetée `nvml` avant fix-8-8 : voir `fix-8-8-...` et série datée (d).
- Modèles chargés et `size_vram` non relevés pendant le run.
- Balayage refaisable avec un Decider `granite4.2:3b` pour mesurer le seuil (environ 20 min pour le seuil 0,1 seul, estimation).

## À arbitrer par Anaël

1. **`completed_with_errors` résiduel (7 Critères)** : rag-naif et raptor sur q-044 (2 Critères chacun, `qwen3.5:4b` coupé à 500 tokens, 2 essais identiques), pageindex sur q-017 (3 Critères, `granite4.2:3b` coupé à 700 tokens). Cause : justifications qui partent en délibération quand Réponse, contexte et référence se contredisent ; le budget `200 × n + 100` ne les contient pas. Options : (a) accepter les 7 Critères non jugés (ils sortent des scores : n = 18 au lieu de 19 pour rag-naif, raptor et pageindex sur certaines colonnes) et passer 8.8 à `done` ; (b) consigne de justification courte ou schéma sans `justification`, qui change les prompts des Juges et le Cache ; (c) relever encore le budget (ne traite pas la cause).
2. **Valeur de `relevance_threshold`** : la mesure ne départage pas les trois seuils (0 Passage retenu partout, Decider `minicpm5:1b` à 0,0). Recommandation : maintenir 0,1 ; refaire le balayage avec un Decider plus gros avant de décider, ou le reporter.
3. **q-044** : Ancrage de référence (`chronique-1415.md`) créé par le Scénario, absent du Corpus de la phase `base`, avertissement à l'export ; la Question est impossible à répondre en `base` et provoque la dérive des Juges. Options : la marquer comme Question de phase `update` seulement, ou l'exclure des scores `base`.
4. Énergie du Poste `judging` et GPU du profil `gpu` (reports de fix-8-8) : ouvrir ou non une phase d'énergie des Juges.
