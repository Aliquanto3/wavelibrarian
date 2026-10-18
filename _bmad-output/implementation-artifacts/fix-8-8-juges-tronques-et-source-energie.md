---
story: "fix-8-8"
title: "Juges tronqués et source d'énergie nvml à tort"
status: review
---

# Correctif 8.8 : Juges tronqués et source d'énergie `nvml` à tort

Révélé par le run réel `20261018-115941-a2a512` (mini-cpu, story 8.8). Exigences : FR-36 (Juge), AD-17 (énergie), `contracts.md` §6. Aucun AC, schéma, prompt ni valeur par défaut de l'epic ne change.

## Défaut 1 : Juges tronqués au budget

- Constat : 48 réponses `JudgeCriteriaOutput` `non_conformant` (granite4.2:3b 44, qwen3.5:4b 4), toutes arrêtées exactement au budget `120 × n + 60` (300 tokens pour 2 Critères, 420 pour 3) ; les réponses conformes montent à 414 tokens (p95 357). D'où 55 Critères sans verdict et `completed_with_errors`.
- Correctif (`components/judges/llm.py`) : `budget_sortie(n, max_output_tokens)` = `200 × n + 100`, borné par `max_output_tokens` du Catalogue (2048 pour les Juges locaux). 2 Critères : 500 ; 3 Critères : 700, soit 70 % au-dessus du maximum conforme observé (414), et plus de 1,6 fois le budget qui coupait.
- Cohérence : la passerelle estime la sortie à `max_tokens` (`gateway.py`, réservation du plafond) : le budget plus large augmente la réservation du Juge d'au plus 280 tokens de sortie par appel à 3 Critères (Juge API ; 0 pour un Juge local), cohérent avec une sortie réellement possible. La clé du Cache contient `max_tokens` (`llm/cache.py`) : les verdicts mis en cache avec l'ancien budget ne sont plus relus, les `non_conformant` ne sont jamais cachés. Aucune migration.
- Tests : `test_llm_judge.py::test_budget_de_sortie_couvre_les_sorties_observees`.

## Défaut 2 : source d'énergie `nvml` avec le GPU désactivé

- Cause réelle (reproduite) : sur ce poste (RTX 3050), le 1er tracker codecarbon du processus garde `GPU.gpu_ids == []`, mais dès le 2e tracker codecarbon y remet `[0]` (état NVML du processus) malgré `gpu_ids=[]`. La revue de 8.6 se fiait à `hw.gpu_ids` : `nvml`/`measured` pour toutes les phases sauf la première (`windows_emi`). L'énergie du GPU (au repos, `CUDA_VISIBLE_DEVICES=-1`) était aussi comptée dans le total de la phase.
- Correctif (`measure/energy.py`) : (1) `CodecarbonMeter.start` retire le `GPU` de `tracker._hardware` : son énergie n'entre plus dans la phase ; (2) `energy_source` et `is_hardware_counter` ne tiennent compte d'un `GPU` que si la demande `tracker._gpu_ids` (à défaut `hw.gpu_ids`) désigne un GPU, et non selon l'état du matériel. Vérifié en réel : 3 phases successives donnent `measured` / `windows_emi`.
- Tests : `test_gpu_present_mais_non_suivi_ne_donne_ni_source_ni_methode` (matériel GPU `[0]`, demande `[]`) et `test_le_meter_retire_le_gpu_de_codecarbon`.
- Effet sur les données : les spans `nvml` du run 20261018-115941-a2a512 sont à relire comme `windows_emi` ; leur énergie incluait le GPU au repos. Les runs suivants sont corrects (relancer, ou reprendre : l'énergie des phases refaites est recalculée).

## Spans `unknown` (156) et sans attribut (22)

Tous sont des spans `judge` du Poste `judging` ; ce n'est pas un défaut du compteur, c'est le périmètre de la mesure :

- 156 `unknown` : appels réels de Juges locaux (granite4.2:3b 47 + 44 non conformes, qwen3.5:4b 61 + 4). La passerelle laisse l'énergie d'un modèle local au runner (mesure par phase, AD-17), et le Poste `judging` n'ouvre pas de phase d'énergie (seules `index`, `update`, `query` en ont une) : leur énergie n'est ni mesurée ni répartie, donc `unknown`/`unknown`, volontairement.
- 22 sans attribut : hits du Cache (`wl.llm_cache_hit=true`, 9 + 13) ; la passerelle n'émet pas d'attribut d'énergie pour un hit (`energie=False`), l'appel n'a pas eu lieu.
- Documenté, non corrigé : mesurer l'énergie du Poste `judging` serait une nouvelle exigence (phase d'énergie des Juges, comptabilité du Rapport), hors du périmètre de ce correctif.

## Reports

- Énergie des Juges locaux (Poste `judging`) non mesurée : à arbitrer par Anaël (phase `judging` dans `energie_de_phase`, ou mention au Rapport).
- Relancer `wl run --reprendre` du run 8.8 pour rejuger les 55 Critères avec le nouveau budget.
