---
story: "1.4"
title: Catalogue de modèles, paramètres de coût et profils d'exécution
status: review
---

# Story 1.4 : Catalogue de modèles, paramètres de coût et profils d'exécution

## Code Map

- `src/wavelibrarian/defaults/` : `models.yaml`, `costs.yaml`, `profiles/{cpu,gpu,test}.yaml` (données du paquet).
- `src/wavelibrarian/config/schemas.py` : `Pricing`, `PriceTier`, `ModelEntry`, `CostSettings`, `ProfileSettings` et leurs sous-schémas ; `valider` (erreur pydantic vers `ConfigError` au chemin pointé).
- `src/wavelibrarian/config/catalog.py` : `ModelCatalog` (`get`, `cost`), `load_catalog`.
- `src/wavelibrarian/config/defaults.py` : `load_profile`, `load_costs` (fusion clé par clé), `defaults_dir`, `charger_yaml`.
- `tests/unit/config/test_catalog.py`.

## Design Notes

- Tous les schémas sont gelés avec `extra="forbid"`. Les montants sont des `Decimal` (tarifs en chaînes dans le YAML).
- `ModelEntry.pricing` est validé par défaut (`validate_default`) : l'absence de prix d'un modèle `kind: api` sort avec le chemin `models[i].pricing`.
- `ModelCatalog.cost` : le multiplicateur du plus haut palier franchi s'applique à tous les postes quand entrée + lecture + écriture de cache dépassent le seuil ; un modèle local coûte 0 (coût de possession, FR-31). `cache_write_1h` est déclaré mais non facturé : `Usage` n'a pas de poste 1 h.
- `load_costs` fusionne des dictionnaires bruts (défauts, `WL_HOME` ou variable d'environnement, fichier d'Expérience) avant de valider : les dates de section restent celles des défauts si seule une valeur est surchargée.
- `RunContext.catalog` et `.profile` restent typés `Any` : `ports` est sous `config` dans le contrat `layers`, y importer un type est interdit ; un Protocol dupliquerait le schéma. Reporté.
- `wl_home` : paramètre explicite, sinon variable `WL_HOME`. Le branchement sur l'Expérience (clé `costs:`) revient à la story 1.5.

## Tâches et critères

- [x] Catalogue livré (Haiku, modèles Ollama CPU et GPU, e5, bge-m3, `fake-llm-a/b/c`, `fake-embedder` dim 64) : `test_catalogue_livre`.
- [x] Modèle `api` sans `pricing` refusé à `models[i].pricing` : `test_api_sans_prix_refuse` ; clé inconnue : `test_cle_inconnue_et_yaml_invalide`.
- [x] `catalog.get("absent")` lève `ConfigError` nommant le modèle : `test_get_absent`.
- [x] Coût Haiku en `Decimal`, 0.60 pour 1 M / 1 M sans palier : `test_cout_un_million_sans_palier` (voir Auto Run Result).
- [x] Palier x5 sur tous les postes dès que le prompt dépasse 100 000, cache compris : `test_cout_palier_tous_postes` ; tarifs de cache : `test_cout_cache_et_local`, `test_cout_fake`.
- [x] Fusion défauts, `WL_HOME`, Expérience, dates conservées : `test_costs_fusion_cle_par_cle`, `test_costs_wl_home_par_variable`, `test_costs_defauts`, `test_costs_cle_inconnue`.
- [x] Profils `cpu`, `gpu`, `test` : `test_profils`, `test_profil_inconnu` ; cohérence avec le Catalogue : `test_coherence_profils_catalogue`.

## Auto Run Result

- Statut : prêt pour revue.
- Écart : l'exemple de la story (`Usage` de 1 M d'entrée et 1 M de sortie égale 0.60) contredit sa propre règle de palier (1 M dépasse 100 000, donc x5 soit 3.00). Le code suit la règle et le contrat `contracts.md` §4.2 ; le test vérifie 0.60 sans palier et 3.00 avec. À arbitrer par l'orchestrateur.
- Reports : typage de `RunContext.catalog` et `.profile` ; branchement de `costs:` d'Expérience (1.5) ; `cache_write_1h` non facturé.
- Aucun appel réseau, ni Ollama, ni GPU (`CUDA_VISIBLE_DEVICES=-1`, threads à 4).
