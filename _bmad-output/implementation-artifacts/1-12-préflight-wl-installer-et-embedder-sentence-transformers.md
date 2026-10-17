---
story: "1.12"
title: Préflight, `wl installer` et embedder sentence-transformers
status: review
---

# Story 1.12 : Préflight, `wl installer` et embedder sentence-transformers

## Code Map

- `src/wavelibrarian/llm/preflight.py` : `preflight(models, catalog, profile, *, http_client, env_file) -> PreflightResult(errors, ok)`. Ollama (une seule requête `GET /api/tags`), clé `ANTHROPIC_API_KEY` (via `providers/secrets.py`), embedder dans le cache Hugging Face ; `fake` ignoré.
- `src/wavelibrarian/llm/providers/ollama.py` : `list_models(base_url, http_client=, timeout_s=3)` (httpx reste confiné aux providers).
- `src/wavelibrarian/llm/local_models.py` : `hf_cache_dir()`, `embedder_installe(hf_repo)` (système de fichiers seul, sans dépendance).
- `src/wavelibrarian/components/embedders/sentence_transformers.py` : `SentenceTransformersEmbedder`, enregistré `("embedder", "sentence_transformers")`, `Params(model, batch_size=32)`.
- `src/wavelibrarian/runner/installer.py` : `installer(profil)`, avec `telecharger_encodage`, `telecharger_embedder`, `ollama_list` (fonctions de module remplaçables en test).
- `src/wavelibrarian/cli.py` : `wl run` enchaîne validation puis préflight (code 4) ; nouvelle commande `wl installer --profil cpu|gpu`.
- Tests : `tests/unit/llm/test_preflight.py`, `tests/unit/runner/test_installer.py`, `tests/unit/components/test_sentence_transformers.py`.

## Design Notes

- Le préflight examine les modèles des Configurations résolues et le réservoir de Juges. Il ne contrôle pas l'encodage tiktoken (le contrat `layers` interdit `llm` -> `measure`) ; `ReferenceTokenizer` lève déjà une `WlError` explicite au premier usage (story 1.7).
- Ollama : un modèle sans tag est cherché aussi sous `:latest`. Injoignable = un seul message qui nomme l'URL du profil et les modèles attendus ; sinon un message par modèle absent.
- `PreflightResult` n'est pas une exception : `cli.py` décide du code de sortie (4). Aucune clé n'apparaît dans les messages.
- L'embedder ne télécharge jamais : `SentenceTransformer(repo, device=embedder_device, local_files_only=True)`. Import au premier usage, `ImportError` -> `WlError("installer l'extra local")`. Un chargement échoué (cache absent) -> `WlError` qui renvoie à `wl installer`. Vecteurs re-normalisés (norme 1), forme contrôlée contre `dim` du Catalogue, un span `embed` par lot (`provider=sentence_transformers`, coût nul), jetons comptés sur le texte préfixé.
- `wl installer` : encodage `o200k_base` (via `tiktoken.get_encoding`, qui vérifie l'empreinte), embedder du profil (`huggingface_hub.snapshot_download`, extra `local`), puis compare `ollama list` aux modèles Ollama du profil. Jamais de `ollama pull` : les manquants sont listés. Code 4 si des modèles manquent (contrat : « modèle absent »), 1 si un téléchargement ou `ollama list` échoue.
- Lecture du critère « embedder absent du cache local » : cache Hugging Face (`HF_HUB_CACHE`, `HF_HOME/hub`, `~/.cache/huggingface/hub`), au moins un fichier dans un instantané.

## Tâches et critères

- [x] Préflight : Ollama muet nomme `http://localhost:11434` -> `test_ollama_injoignable_nomme_l_url`.
- [x] Modèle absent de `/api/tags`, clé manquante, embedder hors cache signalés par leur nom -> `test_modele_ollama_absent_signale_par_son_nom`, `test_cle_anthropic_manquante`, `test_embedder_absent_du_cache_puis_present`, `test_erreurs_cumulees`.
- [x] Les modèles `fake-*` ne demandent aucune vérification -> `test_modeles_fake_sans_verification`.
- [x] `wl run` : préflight en échec -> code 4 et message français -> `test_wl_run_preflight_en_echec_code_4`, `test_wl_run_cle_manquante_code_4` (préflight réel, environnement vide) ; réussite -> `test_wl_run_preflight_reussi`. Les tests de la story 1.6 (code 2) passent inchangés.
- [x] `wl installer --profil cpu` : `o200k_base`, `intfloat/multilingual-e5-small`, comparaison à `ollama list` -> `test_profil_cpu`, `test_cli_installer_modeles_manquants`, `test_cli_installer_tout_present`.
- [x] `--profil gpu` : `bge-m3` et modèles Ollama GPU -> `test_profil_gpu_vise_bge_m3_et_les_modeles_gpu`.
- [x] Composant enregistré, construction sans l'extra, `WlError("installer l'extra local")` au premier usage -> `test_enregistre_et_construit_sans_l_extra`, `test_premier_usage_sans_l_extra_leve`.
- [x] `query_prefix` / `passage_prefix`, `embedder_device`, vecteurs normalisés, un span `embed` par lot -> `test_prefixes_du_catalogue`, `test_bge_m3_sans_prefixe_et_device_cuda`, `test_device_du_profil_et_cache_local`, `test_vecteurs_normalises_et_modele_charge_une_fois`, `test_un_span_embed_par_lot`.
- [x] Test `real_local` qui encode deux phrases, sauté sans modèle -> `test_real_local_encode_deux_phrases` (écrit, **non exécuté** : contrainte du run, aucun `pytest -m real_local`).

## Auto Run Result

Livré sans réseau : aucune requête Ollama (transport factice), aucune commande `ollama`, aucun téléchargement, `wl installer` jamais lancé pour de vrai, `sentence_transformers` et `huggingface_hub` absents (doubles via `sys.modules`). Reports : encodage tiktoken non contrôlé par le préflight (voir Design Notes) ; `real_local` à exécuter quand Ollama et le GPU seront libres, après `wl installer --profil cpu` et `uv sync --extra local`.
