---
story: "1.11"
title: Providers Anthropic et Ollama
status: review
---

# Story 1.11 : Providers Anthropic et Ollama

## Code Map

- `src/wavelibrarian/llm/providers/anthropic.py` : `AnthropicProvider` (SDK, `cache_control`, outil `emit_output` imposé pour la sortie structurée, lecture de `response.impacts`, traduction des erreurs).
- `src/wavelibrarian/llm/providers/ollama.py` : `OllamaProvider` (`POST /api/chat` seul, options du profil, `keep_alive`, `format`).
- `src/wavelibrarian/llm/providers/secrets.py` : `load_secret` (`.env` par python-dotenv puis environnement, `SecretStr`). `logs.py` : `limiter_journaux(handler)` (loggers `anthropic`, `httpx`, `httpcore` à `WARNING` + filtre de gestionnaire pour `run.log`).
- `src/wavelibrarian/llm/providers/base.py` : `Provider.complete(..., output_schema=None)`, `ProviderResponse.energy_kwh`. `fake.py` accepte `output_schema`.
- `src/wavelibrarian/llm/gateway.py` : schéma JSON transmis au provider, poids du schéma dans l'estimation, `ProviderError(sent=True)` réglé à l'estimation, énergie lue par le provider prioritaire sur l'estimateur. `core/errors.py` : `ProviderError(sent=)`.
- `src/wavelibrarian/measure/energy.py` : `init_ecologits()` (`EcoLogits.init(providers=["anthropic"])`). `pyproject.toml` : `httpx2` confiné à `llm.providers`. `contracts.md` : protocole `Provider` précisé.
- Tests : `tests/unit/llm/test_providers.py` (nouveau), `test_gateway.py` (4 tests ajoutés), `test_roles_fake.py` (espion à `**kw`).

## Design Notes

- **Le SDK `anthropic` 1.15 s'appuie sur `httpx2`**, pas sur `httpx` : le client et le `MockTransport` des tests Anthropic sont ceux de `httpx2` (un `httpx.Client` est refusé). Ollama garde `httpx`. Le contrat import-linter confine aussi `httpx2`.
- `temperature` n'est plus un paramètre typé de `messages.create` dans le SDK 1.15 : il part par `extra_body`. Le corps natif porte bien `temperature: 0`. Acceptation par l'API réelle à confirmer par le test `real_api` (non exécuté).
- Sortie structurée Anthropic par outil imposé (`tool_choice`), pas par `output_config` : le texte rendu est l'entrée de l'outil sérialisée. Le schéma compte comme entrée dans l'estimation (`schema_in_prompt = True`, surcoût fixe `schema_prompt_overhead = 400`, majorant) ; Ollama l'envoie dans `format` (grammaire), poids nul.
- Le SDK ne réessaie pas (`max_retries=0`) : seule la passerelle réessaie. 429, 408, 409, 5xx (529 compris) et erreurs réseau : `retryable=True` ; autres 4xx : non.
- Délai dépassé après envoi : `ProviderError(sent=True)`. La passerelle règle alors la réservation à l'estimation (span `error` au coût estimé) au lieu de la libérer. Anthropic : réessayable ; Ollama : non réessayé (un modèle trop lent ne ira pas plus vite). Une connexion refusée ou un `ConnectTimeout` ne sont pas `sent`.
- Énergie : `EcoLogits.init` patche le SDK, la réponse porte `impacts.energy.value` (kWh, milieu de la fourchette). Lu par duck-typing (aucun import d'`ecologits` dans l'adaptateur). Absent ou modèle inconnu : `energy_kwh=None`, la passerelle retombe sur l'estimateur, d'où `unknown` si lui non plus ne sait pas. Vérifié dans le code d'ecologits 0.11.2 (cache uv, 0.11.3 non disponible hors réseau) : `llm_impacts(provider, model_name, output_token_count, request_latency, electricity_mix_zone)` rend un `ImpactsOutput` dont `energy` est `None` pour un modèle inconnu (jamais `None` lui-même) ; `EcoLogitsEstimator` s'y accorde déjà.
- Clé : lue au premier appel (pas à la construction), absente = `ProviderError` non réessayable. Aucun message d'erreur ne cite en-tête ni clé.
- Ollama : options du profil, puis `temperature` et `num_predict` (= `max_tokens`) de la requête, `seed` si fourni. `num_ctx` n'est pas posé (défaut du serveur) : à renseigner dans `ollama.options` du profil si un prompt long est tronqué.

## Tâches et critères

- [x] Requête Anthropic : `cache_control` sur system et message, `temperature: 0`, `model_id`, `Usage` complet (`test_anthropic_cache_control_temperature_et_modele`, `test_anthropic_usage_sans_champs_de_cache`).
- [x] 429 et 529 : `retryable=True`, 400 : `retryable=False` (`test_anthropic_erreurs_http`).
- [x] Énergie `estimated` si les impacts existent, `unknown` sans erreur sinon (`test_energie_estimee_quand_les_impacts_existent`, `test_energie_inconnue_sans_erreur`, `test_reponse_sdk_ordinaire_sans_impacts`, `test_energie_lue_par_le_provider_prime_sur_l_estimateur`).
- [x] Ollama profil `cpu` avec schéma : `num_gpu: 0`, `seed`, `keep_alive`, `format` = schéma ; `Usage` de `prompt_eval_count` / `eval_count` ; `call_timeout_s` appliqué (`test_ollama_corps_du_profil_cpu_avec_schema`, `test_ollama_delai_du_profil_applique_par_la_passerelle`).
- [x] Clé d'un `.env` temporaire en `SecretStr` ; ni clé ni `x-api-key` dans `traces.jsonl` ni dans les journaux après un appel réussi puis un appel en erreur (`test_cle_lue_dans_le_env_en_secretstr`, `test_la_cle_ne_fuit_ni_dans_les_traces_ni_dans_les_journaux`).
- [x] Loggers réseau forcés à `WARNING`, logging racine en `DEBUG` et `ANTHROPIC_LOG=debug` sans fuite (`test_les_loggers_reseau_sont_forces_a_warning`, même test de fuite).
- [x] Reports : délai après envoi réglé à l'estimation (`test_delai_apres_envoi_regle_a_l_estimation`, `test_delai_ollama_apres_envoi_regle_a_l_estimation_par_la_passerelle`) ; poids du schéma selon le mode (`test_schema_dans_l_estimation_selon_le_mode_d_envoi`, `test_schema_json_transmis_au_provider`) ; `init_ecologits` (`test_init_ecologits`).
- [x] Test `real_local` (Ollama local, `minicpm5:1b-q4_k_m`, `num_gpu` accepté par `/api/chat`, saut sans Ollama) : `test_real_local_num_gpu_accepte_par_api_chat`, **écrit, non exécuté dans ce run**. Test `real_api` Haiku (`test_real_api_anthropic_haiku`) : **écrit, non exécuté**. Les deux sont désélectionnés par défaut (4 tests désélectionnés au total).

## Auto Run Result

Livré sans réseau, sans GPU, sans appel Ollama ni Anthropic. Reports non traités : (1) `llm_impacts` vérifié sur ecologits 0.11.2 seulement (0.11.3 absent du cache uv) ; (2) comportement réel d'un appel interrompu et acceptation de `temperature` par l'API Anthropic restent à confirmer par `real_api` ; (3) le runner (epic 4) doit appeler `init_ecologits()` si le profil demande `ecologits`, `limiter_journaux(handler_run_log)` à l'ouverture de `run.log`, et construire `AnthropicProvider` / `OllamaProvider(profil.ollama)` pour `build_gateway`.
