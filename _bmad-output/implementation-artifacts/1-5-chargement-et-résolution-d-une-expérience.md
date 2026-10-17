---
story: "1.5"
title: Chargement et résolution d'une Expérience
status: done
---

# Story 1.5 : Chargement et résolution d'une Expérience

## Code Map

- `src/wavelibrarian/config/experiment.py` : schémas `Experiment`, `Configuration`, `Budget`, `JudgesSettings`, `StatsSettings`, `RetrySettings` ; formes résolues `ResolvedExperiment` et `ResolvedConfiguration`.
- `src/wavelibrarian/config/load.py` : `load_experiment(chemin)` (`yaml.safe_load`, schéma strict, identifiants uniques, `params` validés par le registre).
- `src/wavelibrarian/config/resolve.py` : `resolve_experiment`, parcours récursif des `Params` (`resoudre_params`, `resoudre_composant`), `to_yaml`, `fingerprint`, `write_resolved`.
- `config/schemas.py` : `valider(..., prefixe=)` pour les chemins sous un nœud englobant. `ports/components.py` : `ComponentSpec` en `extra="forbid"`.
- `tests/unit/config/test_experiment.py`.

## Design Notes

- `load_experiment` valide les `params` de chaque Configuration contre le `Params` enregistré (nécessaire pour le chemin `configurations[1].params.kk`) : une Architecture ou un Composant inconnu y lève donc déjà une `ConfigError` au premier échec. La story 1.6 agrège les refus statiques ; elle peut réutiliser `resoudre_params`.
- Le `kind` d'un champ `ComponentSpec` de `Params` est le nom du champ s'il est un `kind`, sinon l'alias `store`, `lexical`, `graph` (vers `vector_store`, `lexical_index`, `graph_store`), sinon `Field(json_schema_extra={"kind": ...})`. Sans l'un des trois, `ConfigError`.
- Précédence : défaut du code, profil (`ModelRef` à `None` remplacé via `role_default`, `embedder` omis), Expérience. `judges.pool` et `panel_size` omis prennent ceux du profil ; `models_frozen_at` omis prend la date du Catalogue.
- Les chemins (`corpus`, `questions`, `scenario`, `costs`, `catalog`, `judges.excluded_from`) deviennent absolus (POSIX) par rapport au fichier. L'empreinte dépend donc de l'emplacement des fichiers ; `costs` est remplacé par les `CostSettings` résolues (branche `load_costs(experiment_costs=...)`, report de la 1.4).
- Empreinte : sha256 (64 hex) du JSON canonique (clés triées) de l'Expérience résolue, profil et coûts compris ; l'ordre des Configurations compte.
- `parser: auto` reste `auto` : seul le runner, qui connaît les formats du Corpus, le remplace.

## Tâches et critères

- [x] Clé inconnue `configurations[1].params.kk` et valeur mal typée `seed` : `test_cle_inconnue_dans_params`, `test_cle_inconnue_dans_composant_imbrique`, `test_cle_inconnue_dans_spec_de_composant`, `test_valeur_mal_typee`.
- [x] Balise `!!python/object` refusée : `test_balise_python_refusee`.
- [x] Profil `cpu` par défaut, `ModelRef` rempli par `claude-haiku-5-5`, modèles et `answer_producer` exposés : `test_resolution_profil_cpu_par_defaut`, `test_modele_explicite_prime_sur_le_profil`.
- [x] `embedder` omis, `fake` ou `sentence_transformers` selon le Catalogue : `test_embedder_omis_cpu_sentence_transformers`, `test_embedder_omis_profil_test_fake`.
- [x] Chemins relatifs au fichier de l'Expérience : `test_chemins_relatifs_au_fichier`.
- [x] `experiment.resolved.yaml` complet (défauts, `CostSettings`, `models_frozen_at`) et `experiment.sha256` stable : `test_serialisation_et_empreinte`, `test_defauts_juges_et_date_gel`.
- [x] Même empreinte quel que soit l'ordre des clés : `test_empreinte_insensible_a_l_ordre_des_cles` (et `test_empreinte_change_avec_une_valeur`).
- [x] Identifiants en double ou hors `[a-z0-9-]+` vers `configurations[i].id` : `test_id_en_double`, `test_id_hors_motif`.

## Auto Run Result

- Statut : prêt pour revue.
- Reports : arbitrer avec 1.6 qui valide quoi (le chargement refuse déjà un nom inconnu) ; `parser: auto` à résoudre par le runner ; le `kind` des champs `ComponentSpec` repose sur une convention de nommage (les Architectures des epics suivants doivent la suivre ou déclarer `json_schema_extra`) ; empreinte liée aux chemins absolus.
- Aucun appel réseau, ni Ollama, ni GPU (`CUDA_VISIBLE_DEVICES=-1`, threads à 4).

## Revue

- medium, second avis 1 : `ModelRef` nu (classe en métadonnée) ignoré par `resolve`, modèle absent de `models`. Corrigé : `registry.register` refuse un `ModelRef` nu (contracts.md l. 36 impose l'instance `ModelRefMeta(role_default, ...)`) ; fixture `fake` passée à l'instance, `conf.models` vérifié.
- medium, second avis 2 : `or` écrasait `pool`/`panel_size` explicites faux. Corrigé : test `is None` ; `panel_size >= 1` et `pool` non vide imposés par le schéma.
- medium, second avis 3 : `seed: "42"` et `seed: true` acceptés par coercition. Corrigé : `seed` (et `max_questions`, `>= 1`) en `strict` ; AC « valeur mal typée refusée » (FR-9).
- medium, second avis 4 : `parser: auto` non remplacé avant hachage. Reporté : la résolution exige les formats du Corpus (story 2.1) et les parsers du registre (story 2.2) ; le runner (story 4.4) remplace `auto` avant `write_resolved`, consigné dans sa docstring. Vérification : `experiment.resolved.yaml` d'une Exécution ne contient plus `auto`.
- low, second avis 5 : chemins absolus et `WL_HOME` dans l'empreinte. Rejeté : le contrat attend l'empreinte de l'Expérience telle qu'exécutée sur la machine, stable d'un appel à l'autre, pas une portabilité inter-machines ; `config_id` est l'`id` déclaré, non haché.
- low, second avis 6-8 : tests (empreinte, `WL_HOME`, cas manquants). Partiellement corrigé : tests ajoutés pour juges explicites, graine stricte, `ModelRef` nu ; le reste écarté (l'empreinte est déjà testée contre un changement de valeur et l'ordre des clés).
