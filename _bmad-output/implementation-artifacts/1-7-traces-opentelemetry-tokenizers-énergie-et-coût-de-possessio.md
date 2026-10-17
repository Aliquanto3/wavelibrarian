---
story: "1.7"
title: Traces OpenTelemetry, tokenizers, énergie et coût de possession
status: done
---

# Story 1.7 : Traces OpenTelemetry, tokenizers, énergie et coût de possession

## Code Map

- `src/wavelibrarian/measure/tracing.py` : `Tracer` (port `Tracer`), `JsonlSpanExporter`, protocole `TraceContext` ; un `SimpleSpanProcessor`, OTLP seulement si `otlp_endpoint` est donné.
- `src/wavelibrarian/measure/tokenizers.py` : `ApproxTokenizer`, `ReferenceTokenizer` (tiktoken `o200k_base`), `ScaledTokenizer`, `make_tokenizer`, `tokenizer_for(model_id, catalog, reference)`.
- `src/wavelibrarian/measure/energy.py` : `FakeMeter`, `FakeEstimator`, `CodecarbonMeter`, `EcoLogitsEstimator`, `spread_energy`, `is_hardware_counter`, `make_meter`, `make_estimator`.
- `src/wavelibrarian/measure/tco.py` : `possession_cost`.
- `tests/unit/measure/test_measure.py`.

## Design Notes

- Le `Tracer` relit `run_id`, `config_id`, `condition`, `tier`, `phase`, `post` et `question_id` dans le contexte à chaque `record` (le runner les change entre deux appels). Les clés de `extra` sont posées d'abord, puis les attributs du contrat les écrasent : l'appelant ne peut pas imposer `wl.post`. `extra` porte `wl.energy_kwh`, `wl.energy_method`, `wl.loop`, `wl.index_cache_hit`, etc.
- `start_time` = maintenant moins la latence, `end_time` = maintenant (ns). Une ligne JSONL par span, attributs à plat à côté de `trace_id` (32 hex), `span_id` (16 hex), `name`, `start_time`, `end_time`. L'export est synchrone (`SimpleSpanProcessor`), le fichier est écrit en ajout, jamais réécrit.
- Tokenizer `reference` : le fichier de cache tiktoken (`sha1` de l'URL de l'encodage, dossier `TIKTOKEN_CACHE_DIR`, `DATA_GYM_CACHE_DIR` ou temporaire) est vérifié avant tout appel à tiktoken ; absent = `WlError` citant `wl installer`, sans téléchargement.
- `tokenizer_for` : un modèle dont le Catalogue déclare `tokenizer: reference` reçoit le tokenizer de référence du profil tel quel ; un modèle `approx` reçoit référence × `token_factor` (`Decimal`, arrondi au supérieur).
- Énergie : `spread_energy(kwh, latences, méthode)` répartit au prorata de la latence ; sans énergie ou sans durée, `(None, "unknown")`. `FakeMeter` est étiqueté `estimated` (jamais `measured`). `CodecarbonMeter` force `gpu_ids=[]` (pas de NVML) et ne marque `measured` que si un matériel suivi lit un compteur (RAPL, Power Gadget, powermetrics, GPU), sinon `estimated` (TDP × charge). `ecologits` et `codecarbon` sont importés au premier usage.
- `possession_cost` : kWh × prix du kWh + prix du matériel ÷ durée de vie × heures de calcul + Go × prix du stockage × mois, en `Decimal` ; l'argument `months` vaut 1 par défaut.

## Tâches et critères

- [x] Deux `record` donnent deux lignes avec identifiants, bornes et tous les attributs §6 typés (`wl.cost` en chaîne) : `test_deux_records_deux_lignes_avec_tous_les_attributs`.
- [x] `wl.tier` absent sans palier, `wl.post` lu dans le contexte : `test_tier_absent_et_post_lu_dans_le_contexte`.
- [x] OTLP désactivé, `SimpleSpanProcessor` unique, aucune connexion : `test_export_synchrone_local_sans_otlp` (pytest-socket bloque tout réseau), `test_otlp_demande_sans_paquet`.
- [x] `approx` compte 12 pour 12 mots : `test_approx_compte_les_mots`.
- [x] `reference` chargé au premier usage, `WlError("… wl installer …")` sans téléchargement : `test_reference_sans_encodage_local_ne_telecharge_pas`, `test_reference_avec_cache_illisible`.
- [x] `tokenizer_for` applique `token_factor` si le Catalogue ne déclare pas `reference` : `test_tokenizer_for_applique_token_factor`.
- [x] Énergie `fake` : démarrage, arrêt, répartition 25/25/50 % avec `wl.energy_method` : `test_fake_demarre_arrete_et_repartit_au_prorata`, `test_energie_portee_par_les_spans`, `test_repartition_sans_energie_ou_sans_duree`.
- [x] Adaptateurs importés au premier usage, `WlError("installer l'extra energy")` s'ils manquent : `test_adaptateurs_sans_extra_energy`, `test_import_paresseux_des_adaptateurs`.
- [x] `measured` seulement avec compteur matériel : `test_mesure_materielle_seulement_avec_compteur`, `test_codecarbon_double_sans_gpu`, `test_ecologits_double`.
- [x] Coût de possession de 0,5 kWh, 3 600 s, 2 Go sur un mois = 0,20005 EUR en `Decimal` : `test_cout_de_possession`.

## Auto Run Result

- Statut : prêt pour revue.
- Contradiction de lecture : le Catalogue donne à Haiku 5.5 `tokenizer: reference` ET `token_factor: 1.5` ; l'AC applique `token_factor` seulement hors `reference`. Retenu : `reference` = tokenizer de référence tel quel ; le facteur 1,5 de Haiku n'est donc pas appliqué par `tokenizer_for`. La passerelle (1.9) doit multiplier explicitement le décompte de référence par `token_factor` pour l'estimation avant appel (spine, séquence de réservation), à arbitrer.
- Reports : 1.9 câble `RunContext.tokenizer_for`, `make_tokenizer(profil.tokenizer)`, le Tracer (`traces.jsonl` dans le dossier de l'Exécution), et lit `FakeEstimator`/`EcoLogitsEstimator` pour `wl.energy_*` ; le runner (epic 4) appelle `spread_energy` par phase locale et `possession_cost` dans le Rapport ; l'adaptateur Anthropic (1.11) lit `response.impacts`. `OfflineEmissionsTracker(gpu_ids=[])` et la détection du compteur matériel (`_hardware`, `_mode`) sont écrits sans codecarbon installé : à confirmer avec l'extra `energy` hors du run autonome.
- Aucun appel réseau, ni Ollama, ni GPU (`CUDA_VISIBLE_DEVICES=-1`, threads à 4) ; codecarbon et ecologits non installés, jamais exécutés.

## Revue

Revue Opus en une passe, avec la liste du second avis (Haiku).

- medium, second avis 1 : corrigé. Avec un cache tiktoken corrompu, tiktoken supprimait le fichier puis tentait `getaddrinfo` (reproduit). `encodage_installe` contrôle désormais le SHA-256 attendu par tiktoken avant tout appel, et tiktoken n'est donc jamais atteint sans fichier intègre. Un test vérifie que la constante reste celle de `tiktoken_ext/openai_public.py`.
- low, second avis 2 : corrigé (immédiat, lié au 1). `TIKTOKEN_CACHE_DIR=""` désactive le cache chez tiktoken (lecture réseau) : c'est maintenant un encodage absent, avec `WlError`.
- medium, second avis 3 : corrigé. Le patch de `builtins.__import__` ne touche pas `importlib.import_module`. Le test pose `sys.modules[nom] = None`, ce qui lève `ImportError` que l'extra soit installé ou non.
- medium, second avis 4 : corrigé en partie, le reste reporté. `llm_impacts` n'est pas documentée (review-versions.md, point 5). Une API absente ou une signature changée lèvent `WlError`, et un modèle inconnu ou un autre échec sont journalisés en `warning` au lieu d'être avalés. Reporté à 1.11 et hors du run, avec l'extra `energy` : vérifier la signature de `ecologits.tracers.utils.llm_impacts` en 0.11.3 et le type de `impacts.energy.value`. AD-17 prescrit `EcoLogits.init` puis `response.impacts` dans l'adaptateur Anthropic : choisir entre les deux voies.
- medium, second avis 5 : reporté. Le code est déjà défensif (sans `_hardware` ni `_mode`, on obtient `estimated`, test à l'appui). À vérifier hors du run, après le pilote, avec l'extra `energy` installé : (a) `OfflineEmissionsTracker(gpu_ids=[])` n'initialise pas NVML (une liste vide peut valoir « tous les GPU », et `CUDA_VISIBLE_DEVICES` ne masque rien à NVML) ; (b) les noms réels des attributs `tracker._hardware` et `hw._mode` en codecarbon 3.3.1 ; (c) sous Windows, la méthode vaut bien `estimated` ; (d) la règle « un matériel lu sur compteur suffit » pour une phase où le CPU est estimé et le GPU mesuré.
- medium, second avis 6 : corrigé. `SimpleSpanProcessor` avale les exceptions d'export. L'exporteur compte ses lignes et garde l'erreur, et `record` lève `WlError` si la ligne n'est pas écrite. Cela couvre aussi `OTEL_SDK_DISABLED`, et le sampler est forcé à `ALWAYS_ON` pour que `OTEL_TRACES_SAMPLER` n'écarte aucun span.
- low, second avis 7 : corrigé (immédiat). L'import paresseux est vérifié dans un processus neuf par `sys.modules`, et non plus sur le texte du source.
- low, second avis 8 : rejeté. `spread_energy` est déjà typée `list[tuple[float | None, EnergyMethod]]`.
- low, second avis 9 : rejeté. Sans modèle (span `local`), l'attribut est omis, comme le veut la convention OTel. §6 donne des types et pas d'obligation de présence, et le Rapport (epic 4) devra tolérer l'absence.
- low, second avis 10 : corrigé. AD-11 impose un export synchrone dans un seul fil, donc l'OTLP passe aussi par `SimpleSpanProcessor`.
- Décision de l'orchestrateur : `tokenizer_for` renvoie le tokenizer de référence brut pour `reference`, et `token_factor` s'applique dans la Passerelle (1.9). Conforme à contracts.md:163, non modifié.
