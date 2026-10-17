---
story: "4.3"
title: Cache d'index et dossier d'Exécution
status: done
---

# Story 4.3 : Cache d'index et dossier d'Exécution

## Code Map

- `src/wavelibrarian/runner/index_cache.py` : `index_key(corpus_fingerprint, architecture)`, `IndexCache(wl_home).build(ctx, factory, corpus, post="indexing")` (rend l'instance chargée et la clé).
- `src/wavelibrarian/runner/rundir.py` : `resolve_parsers`, `create_run_dir`, `set_status`, `JsonlWriter`, `attach_run_log` / `detach_run_log`.
- Tests : `tests/unit/runner/test_story_4_3.py` (Faux LLM, profil `test`, Mini-corpus, `WL_HOME` dans `tmp_path`).

## Design Notes

- `build` prend une `factory` (instance neuve de l'Architecture via `ctx.build`) : une instance calcule la clé et appelle `index`, une autre, neuve, appelle `load`. Les chemins « cache présent » et « cache absent » sont donc identiques (AD-10).
- Un index est présent s'il a un `manifest.json` dans `index/<clé>/`. Un `.tmp-<clé>` laissé par une construction interrompue est supprimé avant de reconstruire ; toute exception pendant `index` supprime le temporaire et ne crée pas le dossier final.
- Le span `local` `index` (un par index chargé ou construit) porte `wl.index_cache_hit` et `wl.index_key`, au Poste `post` (défaut `indexing`, `update` pour la story 4.7). Sa latence couvre la construction éventuelle et le `load`. `embedder_dim` du manifeste est lu sur l'attribut `embedder.dim` de l'Architecture quand il existe.
- `resolve_parsers` remplace `parser: auto` par le nom concret lu sur les formats du Corpus déclaré (`nom_parser_resolu(parsers_par_format(...))`, par exemple `markdown+pdf_text`), la même forme que `CorpusProfile.parser`. `create_run_dir` refuse une Expérience où `auto` reste. `Context.from_experiment` lit ensuite `conf.parser.name` : `RunContext.parser` est concret (report traité).
- `manifest.json` : `run_id`, `experiment_id`, `status: running`, `profile`, `models_frozen_at`, `models` (modèles des Configurations puis du réservoir de Juges), `experiment_sha256`, `freeze_sha256` (donné par l'appelant), `started_at`. `set_status` change `status` et pose `finished_at`. Un `run_id` déjà initialisé est refusé (la reprise relève de la story 4.8).
- `JsonlWriter` n'accepte que `answers.jsonl`, `verdicts.jsonl` et `panel.jsonl` (`traces.jsonl` reste au Tracer), ouvre en ajout, UTF-8, LF, et vide le tampon à chaque ligne.
- `attach_run_log` crée `run.log` (handler sur le logger racine) et appelle `limiter_journaux(handler)`.

## Tâches et critères

- [x] Écriture dans `index/.tmp-<clé>/`, `manifest.json` (`index_key`, `architecture`, `corpus_fingerprint`, `created_at`), `os.replace` : `test_premiere_demande_ecrit_tmp_manifest_puis_renomme`.
- [x] `embedder_dim` s'il y a un embedder : `test_manifest_porte_embedder_dim_quand_l_architecture_en_a_un`.
- [x] `index_key = sha16(canonical_json({...}))`, défaut = Params moins `query_params`, parser, tokenizer : `test_index_key_est_le_hachage_des_trois_elements`.
- [x] Index présent : `index` non appelé, instance neuve + `load`, span `local` `index` avec `wl.index_cache_hit=true` : `test_index_present_pas_de_index_instance_neuve_load_et_span_hit`.
- [x] Exception pendant `index` : pas de dossier final, temporaire supprimé ou ignoré : `test_exception_pendant_index_aucun_dossier_final_ni_tmp`, `test_dossier_temporaire_obsolete_ignore_a_la_reprise`.
- [x] `k` seul : clés égales ; `size` du chunker : clé différente : `test_k_hors_de_la_cle_size_du_chunker_dans_la_cle` ; corpus et parser dans la clé : `test_cle_change_avec_le_corpus_et_le_parser`.
- [x] `runs/<run_id>/` avec `experiment.resolved.yaml`, `experiment.sha256`, `manifest.json` (`status: running`, profil, `models_frozen_at`, modèles) avant tout appel : `test_dossier_d_execution_fichiers_avant_tout_appel`.
- [x] JSONL en ajout seulement, UTF-8, LF, écrits par le runner seul : `test_jsonl_ajout_seulement_utf8_lf`.
- [x] Report 4.3 / 4.4, `parser: auto` remplacé, `experiment.resolved.yaml` sans `auto`, `RunContext.parser` concret : `test_parser_auto_remplace_avant_write_resolved`, `test_parser_explicite_conserve_et_auto_refuse_par_create_run_dir`.
- [x] Report RunContext, fichiers du run : `manifest.json`, `experiment.resolved.yaml` (ci-dessus) et `run.log` : `test_run_log_ecrit_en_utf8`.

## Auto Run Result

- Statut : review. 620 tests verts (suite complète), pyright 0 erreur, ruff propre, contrôle rapide sans erreur.
- Reports traités : « 4.3 / 4.4, `parser: auto` » et, pour « Runner, RunContext », les fichiers `manifest.json`, `run.log`, `experiment.resolved.yaml`.
- Reports non traités (stories 4.4 et suivantes) : tenir le `RunContext` vivant (`with`) pendant toute l'Exécution, câbler `run.lock` puis `Ledger(recover_orphans=True)` dans `wl run`, libération manuelle d'une réservation `hors_execution` orpheline, énergie par phase, `required_paths` des Paliers, `Scénario`, Faux LLM scénarisé.
- Écart : le temps passé dans `build` est mesuré par `time.perf_counter` ; le Poste `update` du Scénario passera `post="update"` en story 4.7. Le nom `markdown+pdf_text` pour un corpus mixte découle de `nom_parser_resolu` (1.2 / 2.2) et non d'un nom unique.
- Risque : `os.replace` d'un dossier sur un dossier final déjà présent échouerait sous Windows ; le cas est écarté par le test de présence préalable (exécution séquentielle, `run.lock`).
- `pyproject.toml` : `wavelibrarian.runner.rundir` rejoint `allowed_importers` du contrat « Providers atteints par la seule passerelle » pour importer `limiter_journaux` seul ; à confirmer en revue.

## Revue

Revue Opus en une passe, après rebase sur `main` (caef354, aucun conflit). Sources : SA = second avis (Haiku), R = revue.

- HIGH, SA 1, corrigé : `ingest(corpus, "markdown+pdf_text")` levait `ConfigError` (reproduit sur le Mini-corpus). Le nom composite reste l'identité du parser (`ctx.parser`, `CorpusProfile.parser`, `index_key`) ; `parsers_par_format` le décompose désormais par format (Parser `auto` du format s'il fait partie des composants), ce qui couvre aussi `corpus/scenario.py`. Test de bout en bout : `resolve_parsers` → `create_run_dir` → `Context.from_experiment` → `ingest(corpus, ctx.parser)` → `IndexCache.build`, plus `test_parser_composite_par_format`.
- HIGH, SA 2, rejeté : `doc_id = sha16_bytes(octets)` (AD-5), donc un contenu modifié change `fingerprint` et `index_key` ; prouvé par `test_contenu_modifie_change_fingerprint_et_cle`.
- medium, SA 3, corrigé : `runner.rundir` retiré des `allowed_importers` (contrats import-linter identiques à `main`) ; `limiter_journaux` réexporté par `llm/gateway.py` et importé de là.
- medium, SA 4, corrigé : `ArchitectureBase.embedder_dim()` (défaut `None`) remplace la lecture de `architecture.embedder.dim`. Report epic 6 : chaque Architecture à embeddings redéfinit `embedder_dim()` pour que le manifeste porte la dimension (FR-3, contrôlée par `config/validate.py`).
- medium, SA 5, corrigé : la clé porte `parser_versions` (version de chaque Parser de `ctx.parser`), ajoutée par `runner/index_cache.index_key` et non par `index_key()` pour qu'une Architecture qui redéfinit `index_key()` ne puisse pas l'omettre. Écart assumé à la formule littérale du critère (quatrième champ), justifié par AD-10 : le `doc_id` hache les octets bruts, une nouvelle version de Parser ne change pas `corpus_fingerprint`. Un parser encore `auto` est refusé par la clé (`ConfigError`).
- medium, SA 6, corrigé : `test_run_log_filtre_les_debug_reseau_et_les_en_tetes` (DEBUG `anthropic`, `httpx`, `httpx2`, `httpcore2.*` relevés après coup, en-tête `x-api-key` absent, WARNING réseau et DEBUG du runner gardés).
- low, SA 7, reporté : chemins absolus dans `experiment.resolved.yaml`, déjà connus depuis la 1.5 (`resolve_experiment` rend les chemins absolus) ; à traiter si l'Expérience résolue doit être publiée telle quelle.
- low, SA 8, corrigé : `create_run_dir` refuse tout `runs/<run_id>/` existant non vide (ou qui n'est pas un dossier), même sans manifeste.
- low, SA 9, corrigé : §5 exige l'empreinte du Gel dans `manifest.json` ; `freeze_sha256` devient obligatoire et doit être un sha256 hexadécimal.
- low, R, reporté (story 4.8, reprise) : une Expérience résolue relue par `resolve_experiment` avec `parser: markdown+pdf_text` échouerait dans `resoudre_composant` (nom composite non enregistré) ; la reprise doit relire `experiment.resolved.yaml` comme `ResolvedExperiment`, ou `resolve_experiment` accepter un composite.
