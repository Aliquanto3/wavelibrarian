---
story: "8.7"
title: "Modèle CPU de sélection pour PageIndex"
status: review
---

# Story 8.7 : Modèle CPU de sélection pour PageIndex

Exigences : FR-24 ; AD-4 (rôle `select_nodes`), AD-14 ; `experiments/mini-cpu.yaml`, profil `cpu`. Limite L4 : `minicpm5:1b` atteint `select_max_tokens = 256` sur q-004.

## Réalisé

- Étude réelle sur Ollama (CPU seul : `CUDA_VISIBLE_DEVICES=-1`, `OMP_NUM_THREADS=4`, profil `cpu`, `WL_HOME` neuf par essai), sur q-002, q-004, q-011 et q-013 (4 premières Questions du split dev), PageIndex seul, Juges granite4.2:3b et qwen3.5:4b.
- Option retenue : (b) `repeat_penalty: 1.15` dans `ollama.options` du profil `cpu` (`src/wavelibrarian/defaults/profiles/cpu.yaml`). Aucune valeur par défaut du code ni de l'Expérience ne change : `mini-cpu.yaml` ne porte qu'un commentaire qui renvoie au profil (l'Expérience n'a pas de champ `ollama`).
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

## Revue (2026-10-18, Opus, après rebase sur `main`)

Run réel de contrôle : `WL_HOME` neuf, `wl run experiments/mini-cpu.yaml`, CPU seul (`CUDA_VISIBLE_DEVICES=-1`, `OMP_NUM_THREADS=4`), un seul serveur Ollama, `ollama ps` vide à la fin.

| Mesure | Référence (3e série, sans pénalité) | Avec `repeat_penalty: 1.15` |
|---|---|---|
| Durée | 9 min 30 s | 9 min 16 s |
| Réponses ok / error | 7 / 1 (q-004 PageIndex) | 8 / 0 |
| Sorties `pageindex.select.*` à `select_max_tokens` | 2 (q-004) | 0 (26 à 46 tokens de sortie, 1 à 5 s) |
| Lignes de verdicts | 49 | 56 (8 Réponses x 7, aucun `null`) |
| Critères sans verdict / Réponses non jugées | 0 | 0 |
| Panel admissible | `granite4.2:3b` + `qwen3.5:4b` pour les 4 | idem pour les 4 |
| Qualité bm25 / rag-naif / raptor | 0,50 / 0,50 / 0,50 | 0,50 / 0,50 / 0,50 |
| Qualité PageIndex | 1,00 (n = 1, q-002) | 0,00 (n = 2) |

Contre-essai (profil `cpu` sans `repeat_penalty`, non commité ; PageIndex seul, q-002, `WL_HOME` neuf, 133 s) : même nœud choisi (`#h/le-phare-de-keld`), Réponse `1297`, qualité 1,00. Avec la pénalité, même nœud, Réponse `More than 2000`. La pénalité, globale au profil, dégrade donc le Generator de PageIndex sur q-002 (contexte court où `1297` est récent), alors que la sélection passe. Les Juges ne se dégradent pas.

| Sévérité | Source | Constat | Suite |
|---|---|---|---|
| high | second avis 2 | `cache_key` ignorait les options Ollama du profil : un `WL_HOME` déjà servi rejouait les sorties d'avant `repeat_penalty` (dont les sorties tronquées de q-004). | Corrigé : `OllamaProvider.cache_options` (options du profil et `num_ctx`) passé par la passerelle à `cache_key`, pour le provider `ollama` seulement ; clés anthropic et fake inchangées. Tests dans `test_ledger_cache.py`, `test_gateway.py`, `test_providers.py`. |
| high | revue (run réel) | `repeat_penalty` global fait passer la qualité de PageIndex q-002 de 1,00 à 0,00 (Generator), à sélection identique : l'objectif de la story (scores CPU non faussés) n'est pas atteint, bien que l'AC 2 (Réponses `ok`, aucune sortie à `select_max_tokens`) le soit. | À arbitrer par Anaël (option non changée, consigne de l'orchestrateur) : garder (b) ; passer à (c) `select_model` granite4.2:3b (sélection 18 à 20 s, 5,1 Go, sans pénalité globale) ; ou étendre le schéma pour porter `repeat_penalty` par modèle ou par rôle (`select_nodes` seul). À revérifier sur plus de Questions (8.8). |
| medium | second avis 1 | Portée globale de `repeat_penalty` (Generator, Résumés, Juges). | Confirmé, effet mesuré ci-dessus. Reporté, à arbitrer par Anaël : schéma à étendre si une portée par modèle est voulue. |
| medium | second avis 4 | `mini-cpu.yaml` inchangé alors que l'AC 2 demande d'y reporter l'option. | Corrigé en commentaire : l'Expérience n'a pas de champ `ollama` (extra forbid) ; le commentaire renvoie au profil `cpu`. Pas d'extension de schéma. |
| medium | second avis 7 | Juges non revérifiés avec la pénalité. | Vérifié en réel : 56 lignes de verdicts, 0 Critère sans verdict, Panel complet pour les 4 Configurations. |
| low | second avis 3 | `catalog_fingerprint` ne couvre pas le profil. | Rejeté : `experiment.resolved.yaml` porte `profile_settings.ollama.options`, l'empreinte de l'Expérience change avec le profil et une reprise le détecte. |
| low | second avis 5, 6 | Dénominateurs et latences de l'étude à homogénéiser. | Rejeté : l'étude qualifie déjà ses latences d'indicatives ; le run de contrôle ci-dessus donne les chiffres d'un run complet. |
| low | second avis 9 | Hors périmètre, préexistant. | Rejeté (hors story). |
