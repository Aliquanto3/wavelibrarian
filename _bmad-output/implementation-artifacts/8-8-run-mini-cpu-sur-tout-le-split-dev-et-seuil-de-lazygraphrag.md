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
- lazy-seuil-cpu : **0 Passage retenu sur 19 Questions aux trois seuils**, 19 abstentions par seuil, recall 0. Fait : 64 réponses de Cache identiques `{"scores": [0.0 x 5]}` du Decider `minicpm5:1b` ; 3 Questions (q-017, q-033, q-036) bloquées en amont (`_candidats` vide, aucune communauté candidate). Cause des zéros non établie : hypothèses ordonnées (biais de l'exemple `[0.0, 0.0]` du SYSTEM du Decider, `components/deciders/llm.py:14-18`, non testé ; capacité de `minicpm5:1b`) dans la série datée (c). Balayage non discriminant.
- Latence par seuil (AC 2) : p50 12,18 s / p95 17,7 s à 0,1 (mesurée) ; 12,12 s / 17,7 s à 0,3 et 0,5, **non mesurée** : ces deux seuils rejouent les notes du Cache (128 hits, 64 par seuil) et la latence d'origine de `latency_s`. Aucune latence propre à un seuil n'existe donc.
- RAM : colonne `ollama=` de `ram.log` vide (défaut du script de relevé, à corriger) ; relevé manuel de l'orchestrateur, `/api/ps` à 14:27 : `granite4.2:3b` 5,1 Go et `qwen3.5:4b` 4,2 Go, `size_vram` nul. Saturation attribuée aux deux Juges chargés avec le Generator sans GPU (hypothèse, un seul relevé).

## Acceptance Criteria

1. `mini-cpu` sans `max_questions` : Réponses `ok` pour les 4 Configurations (76 / 76), mais statut `completed_with_errors` et non `completed` : 7 Critères sans verdict. Causes analysées (sorties de Juges tronquées au budget), consignées et soumises à Anaël ci-dessous avant `done`.
2. Balayage {0,1 ; 0,3 ; 0,5} exécuté, scores, nombre de Passages retenus et latence par seuil consignés dans la série datée ; valeur par défaut inchangée. Latence : mesurée à 0,1 seulement, rejeu du Cache aux deux autres seuils (voir Résultats) : critère rempli en partie, à arbitrer (point 2).
3. `run_id`, durée, RAM et dépense consignés ; `run_id` noté comme source de 8.9.

## Reports

- Énergie du Poste `judging` non mesurée (177 spans `unknown`) et énergie du run initial étiquetée `nvml` avant fix-8-8 : voir `fix-8-8-...` et série datée (d).
- Modèles chargés et `size_vram` : un seul relevé manuel (14:27) ; script de relevé de `ram.log` à corriger (colonne `ollama=` vide).
- Balayage refaisable avec un Decider `granite4.2:3b` pour mesurer le seuil (environ 20 min pour le seuil 0,1 seul, estimation).

## À arbitrer par Anaël

1. **`completed_with_errors` résiduel (7 Critères)** : rag-naif et raptor sur q-044 (2 Critères chacun, `qwen3.5:4b` coupé à 500 tokens, 2 essais identiques), pageindex sur q-017 (3 Critères, `granite4.2:3b` coupé à 700 tokens). Cause : justifications qui partent en délibération quand Réponse, contexte et référence se contredisent ; le budget `200 × n + 100` ne les contient pas. Options : (a) accepter les 7 Critères non jugés (ils sortent des scores : n = 18 au lieu de 19 pour rag-naif, raptor et pageindex sur certaines colonnes) et passer 8.8 à `done` ; (b) consigne de justification courte ou schéma sans `justification`, qui change les prompts des Juges et le Cache ; (c) relever encore le budget (ne traite pas la cause).
2. **Valeur de `relevance_threshold`** : la mesure ne départage pas les trois seuils (0 Passage retenu partout, Decider `minicpm5:1b` à 0,0). Recommandation : maintenir 0,1. Avant de décider, refaire le balayage avec (i) une variante du prompt du Decider (exemple de format sans `0.0`) et/ou un Decider plus gros, et (ii) un Cache isolé par seuil, sans quoi la latence des seuils 0,3 et 0,5 reste un rejeu (latence par seuil de l'AC 2 non mesurée). Ou reporter.
3. **q-044** : Ancrage de référence (`chronique-1415.md`) créé par le Scénario, absent du Corpus de la phase `base`, avertissement à l'export ; la Question est impossible à répondre en `base` et provoque la dérive des Juges. Options : la marquer comme Question de phase `update` seulement, ou l'exclure des scores `base`. Le paquet d'annotation de 8.9 contient 4 lignes de q-044 (rag-naif et raptor, `completeness` et `faithfulness`) : Anaël peut les annoter en connaissance de l'Ancrage manquant ou les retirer (paquet non modifié).
4. Énergie du Poste `judging` et GPU du profil `gpu` (reports de fix-8-8) : ouvrir ou non une phase d'énergie des Juges.

## Revue

Revue unique (Sonnet) de la synthèse, avec la liste du second avis (Haiku) vérifiée contre `traces.jsonl`, `verdicts.jsonl`, `panel.jsonl`, `ram.log` et le code de LazyGraphRAG.

| # | Sévérité | Source | Constat | Décision |
|---|---|---|---|---|
| 1 | medium | second avis | « Cause identifiée / Decider facteur limitant » plus fort que la preuve. | Corrigé : le fait certain (64 réponses `[0.0 x5]`) est séparé des hypothèses ordonnées (exemple `[0.0, 0.0]` du SYSTEM, capacité de `minicpm5:1b`) ; 3 Questions bloquées en amont à part (`_candidats` vide, vérifié). |
| 2 | medium | second avis | Latence par seuil (AC 2) absente du tableau. | Confirmé et corrigé : 128 hits de Cache aux seuils 0,3 et 0,5 (vérifié), latence non mesurée, écrite en Résultats et AC 2 ; refaire le balayage à Cache isolé par seuil ajouté aux points à arbitrer. |
| 3 | medium | second avis | Comptes de Juges faux. | Confirmé : initial 130 ok / 48 `non_conformant`, reprise 19 ok / 7 (5 à 500, 2 à 700), pas 8. Corrigé. |
| 4 | low | second avis | 373 lignes de panel, 7 Critères à un verdict. | Partiel : 373 est exact pour `panel.jsonl` (204 sans Juge + 169 avec deux Juges), précisé avec 345 lignes de Juges. Les 7 Critères à un verdict sont 4 sur q-044 et 3 sur q-017 (le second avis inversait). |
| 5 | low | second avis | 177 spans `unknown`, 27 hits. | Confirmé et corrigé (156 et 22 étaient faux). |
| 6 | medium | second avis | Relevé manuel `/api/ps` de 14:27 à ajouter. | Corrigé : 5,1 + 4,2 Go, `size_vram` nul, un seul relevé ; défaut du script de relevé de `ram.log` signalé. |
| 7 | medium | second avis | 4 lignes de q-044 dans le paquet 8.9. | Confirmé (4 lignes, vérifié). Paquet non modifié ; signalé en 8.9, dans la série datée et aux points à arbitrer. |
| 8 | low | second avis | Réserve sur la possession du calcul local. | Corrigé en (a). |
| 9 | low | revue | Latence « spans `answer` » p50 12,2 s inexacte (le champ `latency_s` du span `answer` donne 0,07 s) : la valeur vient du rapport. | Corrigé : colonne renommée, p50 12,18 / 12,12 / 12,12 et p95 17,7 s du rapport. |
| 10 | low | orchestrateur | Commande d'export de 8.9 « reconstituée ». | Remplacée par la commande exacte. |

Reporté (demande Ollama) : refaire le balayage (prompt du Decider, Cache isolé par seuil) et corriger le script de relevé de `ram.log`.
