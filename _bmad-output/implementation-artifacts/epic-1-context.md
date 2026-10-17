# Epic 1 Context: Un banc configurable, mesuré et testable sans réseau

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Poser le socle du banc WaveLibrarian : une Expérience YAML est validée strictement avant tout appel, le registre liste ce que le banc sait faire (`wl registre`), et tout appel de modèle (réel ou factice) passe par une passerelle unique qui applique le Plafond de dépense et le Cache de réponses et trace coût, tokens et énergie. Un agent de développement peut ainsi ajouter un Composant enregistré et le tester avec le Faux LLM et le faux embedder, sans réseau ni clé.

## Stories

- Story 1.1: Squelette du projet et garde-fous sans réseau
- Story 1.2: Types du domaine et ports publiés
- Story 1.3: Registre de Composants et commande `wl registre`
- Story 1.4: Catalogue de modèles, paramètres de coût et profils d'exécution
- Story 1.5: Chargement et résolution d'une Expérience
- Story 1.6: Validation statique d'une Expérience et formation du Panel
- Story 1.7: Traces OpenTelemetry, tokenizers, énergie et coût de possession
- Story 1.8: Registre de dépense et Cache de réponses LLM
- Story 1.9: Passerelle mesurée
- Story 1.10: Rôles LLM, Faux LLM et faux embedder
- Story 1.11: Providers Anthropic et Ollama
- Story 1.12: Préflight, `wl installer` et embedder sentence-transformers

## Requirements & Constraints

- Une clé inconnue ou mal typée dans l'Expérience est refusée avec son chemin pointé ; l'Expérience résolue (défauts compris) et son empreinte sha256 sont écrites avant tout appel.
- Un nom de Composant inconnu donne une erreur qui liste les noms disponibles pour ce `kind` ; ajouter un Composant ne touche pas l'orchestration.
- Refus statiques avant tout appel, regroupés en une seule erreur : Composant ou modèle inconnu, Architecture hybride sur store non hybride, besoin de cache de prompt non satisfait, index réutilisé avec embedder de dimension différente, Juge de la même Famille que le Generator.
- Un modèle d'API sans prix est refusé ; un modèle absent du Catalogue est refusé. Montants en `Decimal`, dans la devise du fournisseur, jamais en float.
- Chaque appel produit une Trace (étape, modèle, tokens entrée/sortie/cache, coût, latence, énergie, Poste) ; la somme des Traces égale le coût du Rapport.
- Plafond de dépense par Exécution et par période (mois civil UTC), par fournisseur ; défaut 5 $ Anthropic. Un appel identique est servi par le cache à coût nul.
- Énergie étiquetée « mesurée » ou « estimée », jamais additionnées entre elles.
- Clés lues depuis `.env` ou l'environnement, jamais dans Traces, Rapports ni journaux. Dépôt public : aucun corpus restreint ni donnée client.
- Python ≥ 3.12, uv, portable Windows et Linux. Messages CLI, Rapport et docstrings en français ; identifiants et clés en anglais.
- Règle commune : `uv run pytest -q --tb=short` et `py .claude/cost-kit/controle_rapide.py` passent sans réseau avec le profil `test` ; un test réseau porte `real_api` ou `real_local`.
- Contraintes du run autonome (17-18/10/2026, un autre banc occupe la machine) :
  - Ollama local interdit (seuls `/api/version`, `/api/ps`, `/api/tags` tolérés, aucune commande `ollama`) ; les tests `real_local` des stories 1.11 et 1.12 sont écrits mais jamais exécutés (pas de `pytest -m real_local`).
  - GPU interdit : `CUDA_VISIBLE_DEVICES=-1` avant tout code de ML.
  - Pas d'extra `local` (torch) ni `docling`, pas de `wl installer`, aucun téléchargement de plus de 1 Go.
  - `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS` à 4 ; RAM ≤ 6 Go ; aucun pytest parallèle.

## Technical Decisions

- Couches (import-linter, contrat `layers`) : `cli` > `runner` | `report` > `architectures` > `components` > `evalset` > `scoring` > `corpus` > `llm` | `measure` | `stats` > `config` > `registry` > `ports` > `core`. Contrats `forbidden` : `anthropic`/`httpx` seulement dans `llm.providers` ; `sentence_transformers` seulement dans `components.embedders` ; `opentelemetry`/`codecarbon`/`ecologits` seulement dans `measure` (exception `llm.providers.anthropic` pour ecologits) ; `llm.providers` importé seulement par `llm.gateway` et `llm.preflight`. `lint-imports` s'ajoute aux commandes du contrôle rapide.
- pyproject : dépendances épinglées `>=x.y,<x+1`, `uv.lock` commité, extras `local` (torch CPU via index PyTorch `explicit = true`, associé à `torch` seul), `energy`, `docling`. Pas de gabarit tiers ; `uv_build`, `src/wavelibrarian/`.
- Registre : `@register(kind, name)`, `Params` pydantic (`extra="forbid"`, `frozen=True`), docstring = description, construction `cls(params, ctx)`, sous-Composants par `ctx.build`, `discover()` par `pkgutil`, liste fermée de `kind`. Un Composant par module, nom au registre = nom du module.
- Types du domaine pydantic `frozen=True, extra="forbid"` ; identités par `core/ids.py` (`sha16`, `canonical_json`, `slug`, `new_run_id`) ; `doc_id = sha256[:16]`, `ParsedCorpus.resolve`. Exceptions de `core/errors.py` seulement (racine `WlError`) ; codes de sortie 0, 1, 2, 3, 4 (validation = 2, préflight = 4).
- Passerelle `MeteredGateway`, point de passage unique, ordre fixe : marqueur `[[wl:role=…]]`, cache, réservation au registre, appel avec 3 essais exponentiels, coût par le Catalogue, règlement, mise en cache, span. Rôles LLM fermés (15), `inputs` rempli par l'appelant et lu par le seul Faux LLM (donc inclus dans la clé de cache pour un provider `fake`). `complete_structured` réessaie une fois puis lève `NonConformantOutput`. Un nouveau rôle modifie `roles.py` et `fake.py` ensemble.
- Providers : `anthropic` (SDK, `cache_control`), `ollama` (`/api/chat` par httpx, options du profil, `format` JSON), `fake`. Spans LLM émis par la seule passerelle ; Embedder et Reranker tracent leurs lots.
- Registre de dépense `ledger.sqlite` (réserver, régler ou libérer ; `BEGIN IMMEDIATE` ; réservation orpheline réglée au montant estimé) ; traces dans `traces.jsonl` via `JsonlSpanExporter` maison et `SimpleSpanProcessor`, OTLP désactivé par défaut.
- Configuration : `yaml.safe_load`, schémas `extra="forbid"`, `ConfigError` au chemin pointé ; précédence code, profil, Expérience ; `costs.yaml` surchargeable par `<WL_HOME>/costs.yaml` puis par `costs:`. Profils `cpu` (défaut, `num_gpu: 0`), `gpu`, `test` (modèles `fake-*`, tokenizer `approx`, énergie `fake`). `config/validate.py` agrège les erreurs statiques en un `ValidationFailed`. Panel : modèles du réservoir hors Famille des `answer_producer` et hors exclus de la calibration, moins de 2 = refus.
- Tests : `pytest-socket` (`--disable-socket --allow-unix-socket`) à vérifier sous Windows, marqueurs `real_api`, `real_local`, `slow`, fixtures `wl_home`, `fake_ctx`. Tarif Haiku 5.5 : palier au-delà de 100 000 tokens (multiplicateur 5 sur tous les postes), `token_factor` 1,5.
- Hors réseau : tokenizer `reference` (tiktoken `o200k_base`) jamais téléchargé en test ; adaptateurs `codecarbon`/`ecologits` importés au premier usage ; `sentence_transformers` lève une erreur à l'usage, pas à l'import.

## Cross-Story Dependencies

- 1.1 est le socle de toutes les autres (couches, pytest-socket, `wl_home`) ; 1.2 (types, ports) précède tout module métier.
- 1.3 (registre) avant 1.5, 1.6 et 1.10 (le faux embedder s'enregistre).
- 1.4 (Catalogue, profils) alimente 1.5, 1.6, 1.8 et 1.9 (coût et estimation).
- 1.7 (Tracer) et 1.8 (registre de dépense, cache) sont requis par 1.9 ; 1.9 est requis par 1.10, 1.11 et 1.12.
- 1.6 est prolongée par 1.12 (le préflight s'insère après la validation dans `wl run`).
- Vers les autres epics : l'epic 4 branche le runner sur la validation et la passerelle ; l'epic 3 réutilise `closed_book_judge` ; les epics 6 et 7 s'appuient sur le registre, le Faux LLM et le faux embedder.

> Mise à jour 2026-10-17 (revue 1.2) : `RunContext` porte désormais `parser: str` (parser résolu de la Configuration), utilisé par `index_key` ; `ArchCapabilities` est gelé avec `extra="forbid"`.
