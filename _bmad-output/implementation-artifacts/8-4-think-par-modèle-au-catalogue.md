---
story: "8.4"
title: "`think` par modèle au Catalogue"
status: review
---

# Story 8.4 : `think` par modèle au Catalogue

Exigences : FR-30 ; AD-3, AD-4 ; `contracts.md` §4.2 (`ModelEntry.think`, arbitrage P7).

## Réalisé

- `ModelEntry.think: bool | None = False` (`config/schemas.py`). `defaults/models.yaml` est inchangé : tous les modèles gardent le défaut `False`.
- `LLMRequest.think: bool | None = False` (`ports/gateway.py`) : la passerelle y pose la valeur du Catalogue pour un modèle Ollama, comme pour `temperature` (4.15).
- `OllamaProvider.native_request` envoie `think: false`, `think: true`, ou n'envoie pas le champ pour `None`.
- Clé du Cache de réponses (`cache_key`) : `params.think` entre dans la clé pour le provider `ollama` seul (`None` distinct de `False`). Les clés des autres providers ne changent pas ; celles d'Ollama changent une fois (les caches Ollama existants sont invalidés, sans effet sur les résultats).
- Span : `wl.think_omitted = true` quand le champ n'est pas envoyé (pendant de `wl.temperature_omitted`).
- Tests sans réseau : `test_ollama_think_selon_la_requete` (les trois valeurs, `tests/unit/llm/test_providers.py`) ; `test_think_du_catalogue_dans_la_requete_la_cle_et_le_span` (valeur du Catalogue sur la requête, hit puis clés distinctes, span, `tests/unit/llm/test_gateway.py`).

## Vérification réelle (2026-10-18, Ollama local, profil `cpu`, `CUDA_VISIBLE_DEVICES=-1`, `OMP_NUM_THREADS=4`)

- `uv run pytest -m real_local` : 2 tests réels passent (après `uv sync --extra local --extra energy`). Le garde-fou `test_real_local_deselectionne` (`tests/unit/test_garde_fous.py`) échoue par construction dès qu'on sélectionne le marqueur : ce n'est pas un échec du produit.
- `wl run experiments/mini-cpu.yaml` (`WL_HOME` neuf) : code 0, `completed`.

| Mesure | Référence (3e série) | Cette story |
|---|---|---|
| Durée | ~9 min 30 s | 9 min 11 s |
| Réponses ok / error | 7 / 1 | 7 / 1 |
| Erreur | PageIndex q-004 | PageIndex q-004, `NonConformantOutput` (`SelectNodesOutput`, `minicpm5:1b`) |
| Lignes de verdicts | 49 | 49 |
| Critères sans verdict | 0 | 0 |
| `ollama ps` | num_ctx 32768 | 100 % CPU (0 couche GPU), num_ctx 32768 (granite4.2:3b, qwen3.5:4b) |

Aucun écart. `ollama stop` sur les modèles chargés, `ollama ps` vide en fin de vérification.

## Reports

- PageIndex q-004 (sortie arrêtée à `select_max_tokens`) : story 8.7, non corrigé ici.
- Aucun modèle du Catalogue ne passe encore à `think: true` ou `None` : le réglage est disponible, sans changement de valeur.
