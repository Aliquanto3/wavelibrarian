# Revue des faits d'adéquation (pile technique, AD-3, AD-16, AD-17)

Date de vérification : 2026-10-17. Les numéros de version ne sont pas revérifiés ici.

## Synthèse par point

1. **Ollama `/api/chat`** : **incertain**. `format` accepte un schéma JSON (confirmé). `options.num_gpu` n'est pas listé pour `/api/chat` ; il n'apparaît que dans l'exemple `/api/generate`. Correction : tester `num_gpu` sur la version Ollama épinglée, ou le documenter comme option générique (paramètre Modelfile). Source : https://raw.githubusercontent.com/ollama/ollama/main/docs/api.md
2. **Anthropic SDK, prompt caching** : **confirmé**. `cache_control` (automatique ou par bloc) ; `usage` renvoie `cache_read_input_tokens` et `cache_creation_input_tokens`. Correction mineure : l'URL `docs.anthropic.com` redirige vers `platform.claude.com`. Source : https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
3. **pytest-socket** : options **confirmées** (`--disable-socket`, `--allow-unix-socket`). Comportement **sous Windows incertain** : ni le README ni la page PyPI ne le mentionnent. Correction : valider par un test réel sous Windows avant de compter dessus. Sources : https://github.com/miketheman/pytest-socket , https://pypi.org/project/pytest-socket/
4. **codecarbon `OfflineEmissionsTracker`** : **confirmé** (classe documentée). Correction : `country_iso_code` est **requis** quand `offline=True` (doc du décorateur) ; sans lui, repli sur une moyenne mondiale. Méthode CPU sous Windows : pas de RAPL (Linux seulement) ; Intel Power Gadget abandonné ; repli sur une estimation TDP × charge CPU (hypothèse de 50 % du TDP). Donc la mesure CPU Windows est une **estimation** : AD-17 doit l'étiqueter `estimated` sur Windows, pas `measured`. Sources : https://docs.codecarbon.io/latest/reference/api/ ; https://docs.codecarbon.io/latest/explanation/rapl/ ; https://docs.codecarbon.io/latest/explanation/power-estimation/ (repérée par recherche, non ouverte)
5. **ecologits** : **infirmé** tel quel. Aucune fonction de calcul directe documentée ; la voie documentée est `EcoLogits.init(providers=[...])` puis lecture de `response.impacts`. Fournisseurs listés : `anthropic`, `cohere`, `google-genai`, `huggingface-hub`, `mistralai`, `openai`. **Ollama absent**, donc les appels Ollama ne seront pas couverts. Anthropic bien connu. Correction : soit accepter le patch du client Anthropic, soit vérifier l'API EcoLogits / Calculator (non documentée dans la page lue). Source : https://github.com/genai-impact/ecologits
6. **tiktoken `o200k_base`** : **confirmé**. Le fichier est téléchargé au premier usage via `requests.get` (URL dans `openai_public.py`, non ouverte). `TIKTOKEN_CACHE_DIR` est pris en compte (prioritaire sur `DATA_GYM_CACHE_DIR`) ; défaut : `tempfile.gettempdir()/data-gym-cache`. Valeur vide = pas de cache. Clé de cache : SHA-1 de l'URL. Pré-téléchargement possible : exécuter une fois avec réseau, ou copier le fichier dans `TIKTOKEN_CACHE_DIR` sous le nom SHA-1 attendu. Sources : https://raw.githubusercontent.com/openai/tiktoken/main/tiktoken/load.py ; https://github.com/openai/tiktoken
7. **bm25s / sentence-transformers** :
   - bm25s : **confirmé** sans téléchargement à l'usage (dépendance NumPy ; PyStemmer et numba optionnels ; téléchargement uniquement pour les fonctions Hugging Face Hub). Source : https://raw.githubusercontent.com/xhluca/bm25s/main/README.md
   - multilingual-e5-small : **incertain**. La page HF n'a pas livré la section d'usage ; chargement par sentence-transformers et préfixes `query: ` / `passage: ` non vérifiés. Correction à vérifier : le modèle e5 attend ces préfixes. Source : https://huggingface.co/intfloat/multilingual-e5-small
   - torch sous Windows : **incertain**. La page PyPI ne dit pas que la roue par défaut est CPU seule. Recommandation : installer explicitement la roue CPU depuis `https://download.pytorch.org/whl/cpu` plutôt que de compter sur PyPI. Source : https://pypi.org/project/torch/ (non concluant)
8. **import-linter, contrat `layers` avec `a | b`** : **confirmé**. `|` marque des modules frères indépendants dans une même couche ; `:` autorise les imports entre frères ; ne pas mélanger les deux sur une même ligne. Source : https://import-linter.readthedocs.io/en/stable/contract_types/layers/ (lue via recherche, pas ouverte directement)

## Points à corriger dans le document
- AD-17 : sur Windows, l'énergie CPU locale est estimée (TDP), pas mesurée ; l'étiquette doit suivre.
- AD-17 : EcoLogits ne couvre pas Ollama ; les appels locaux doivent être étiquetés `unknown` ou estimés autrement.
- Pile : ajouter `country_iso_code` obligatoire pour `OfflineEmissionsTracker`.
- AD-16 : valider `--allow-unix-socket` sous Windows par un test réel.
- Pile : préciser l'index CPU de torch.
