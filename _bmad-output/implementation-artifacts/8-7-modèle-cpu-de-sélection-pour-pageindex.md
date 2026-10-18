---
story: "8.7"
title: "Modèle CPU de sélection pour PageIndex"
status: review
---

# Story 8.7 : Modèle CPU de sélection pour PageIndex

Exigences : FR-24 ; AD-4 (rôle `select_nodes`), AD-14 ; `experiments/mini-cpu.yaml`, profil `cpu`. Limite L4 : `minicpm5:1b` atteint `select_max_tokens = 256` sur q-004.

## Réalisé

- Étude réelle sur Ollama (CPU seul : `CUDA_VISIBLE_DEVICES=-1`, `OMP_NUM_THREADS=4`, profil `cpu`, `WL_HOME` neuf par essai), sur q-002, q-004, q-011 et q-013 (4 premières Questions du split dev), PageIndex seul, Juges granite4.2:3b et qwen3.5:4b.
- Option retenue : (b) `repeat_penalty: 1.15` dans `ollama.options` du profil `cpu` (`src/wavelibrarian/defaults/profiles/cpu.yaml`). Aucune valeur par défaut du code ni de l'Expérience ne change : `mini-cpu.yaml` est inchangé.
- `tests/unit/test_story_8_7.py` : le profil `cpu` porte `repeat_penalty` ; un `select_model` de la Famille d'un Juge du réservoir (`granite4.2:3b`) laisse les Panels et les `answer_producers` de PageIndex inchangés (AD-14, sans réseau).

## Résultat de l'étude (2026-10-18, 4 Questions, sorties de `pageindex.select.*`)

| Essai | Réponses ok | Sorties à `select_max_tokens` | Latence select.1 | RAM (`ollama ps`, 32 768 tokens) |
|---|---|---|---|---|
| Témoin, 256, minicpm5:1b | 3 / 4 (q-004 error) | 3 appels (q-004 x2, q-013 x1) | 5 à 10 s | 1,6 Go |
| (a) 512, seed 42 | 4 / 4 | 0 | 6 à 8 s | 1,6 Go |
| (a) 512, seed 7 | 4 / 4 | 0 | 3 à 5 s | 1,6 Go |
| (a) 512 sur `mini-cpu.yaml` tel quel | 7 / 8 (q-004 error) | 2 (q-004 x2, à 512) | 10,5 s | 1,6 Go |
| (b) `repeat_penalty` 1.15, seed 42 | 4 / 4 | 0 | 5 à 7 s | 1,6 Go |
| (b) seed 7 | 4 / 4 | 0 | 6 s | 1,6 Go |
| (b) sur `mini-cpu.yaml` tel quel | 8 / 8 | 0 | 5,4 s | 1,6 Go |
| (c) `select_model` granite4.2:3b, 256 | 4 / 4 | 0 | 18 à 20 s | 5,1 Go |

(a) réussit sur deux essais mais la boucle dégénérée revient à 512 sur le run `mini-cpu` complet : elle ne suffit pas. (b) passe les trois essais pour un coût nul (pas de modèle de plus, latence inchangée) ; (c) passe aussi mais triple la latence et la RAM. Latences indicatives (d'autres tests tournaient sur la machine).

## Acceptance Criteria

1. Trois options essayées dans l'ordre, consignées ci-dessus ; la moins coûteuse qui passe est (b).
2. `repeat_penalty` reporté dans le profil `cpu` ; `mini-cpu.yaml` tel quel (`max_questions: 2`) : PageIndex 2 / 2 `ok`, aucune sortie à `select_max_tokens`.
3. `test_select_model_de_la_famille_d_un_juge_ne_change_pas_le_panel` vérifie que `select_model` n'est pas un `answer_producer`.

## Reports

- `repeat_penalty` est global au profil : il s'applique aussi aux appels de Generator, de Résumé et de Juges Ollama des autres Configurations CPU (le provider ne l'accepte que par `ollama.options`, partagé). Sur `mini-cpu` complet, 8 / 8 Réponses `ok`. À surveiller si le run du split dev (8.8) montre un effet de qualité.
- Le profil n'a pas de clé pour `select_max_tokens` (schéma `config/schemas.py`, hors périmètre) : pas d'option (a) reportée au profil.
- Le comportement de `wl run` (code 0 malgré une Réponse en `error`) reste reporté (déjà noté).
