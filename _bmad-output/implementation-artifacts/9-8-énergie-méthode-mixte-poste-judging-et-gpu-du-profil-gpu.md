---
story: "9.8"
title: "Énergie : méthode mixte, poste judging et GPU du profil gpu"
status: review
---

# Story 9.8 : Énergie : méthode `mixed`, poste `judging`, GPU du profil `gpu`

Exigences : FR-31, FR-32 ; AD-17 (amendé) ; `contracts.md` §1, §4.3, §6, §7. Origines : question `mixed` de la 8.6, GPU et poste `judging` non mesurés de fix-8-8.

## Réalisé

- `measure/energy.py` : `EnergyMethod` gagne `mixed`. `energy_method(tracker)` : `estimated` sans compteur matériel ; `mixed` si une part reste estimée (RAM de codecarbon à côté d'un CPU lu, cas Windows `windows_emi`, ou CPU estimé à côté d'un GPU lu) ; `measured` si un GPU `nvml` suivi domine (CPU lu aussi) ou si aucun matériel estimé n'est présent. `CodecarbonMeter(gpu=...)` : `gpu_ids=[0]` et pas de `_retirer_gpu` quand `energy.gpu` est vrai (source `nvml`) ; sinon comportement fix-8-8 inchangé.
- `config/schemas.py` : `EnergySettings.gpu: bool = False` ; `defaults/profiles/gpu.yaml` : `gpu: true` (cpu et test inchangés).
- `runner/execute.py` : `juger` ouvre une phase d'énergie `judging` (mesureur nommé `judging:judging`) seulement si un Panel contient un modèle de fournisseur `ollama` ; le corps de l'ancien `juger` devient `_juger`. `energie_de_phase` accepte `conf=None` pour ce Poste. Les spans `judge` locaux reçoivent l'énergie au prorata de la latence ; les Juges d'API gardent l'énergie estimée par appel (gateway), hors phase.
- `report/couts.py`, `section_couts.py`, `fronts.py`, `section_fronts.py` : colonnes `kwh_mixed` et `co2e_g_mixed` (en fin de `costs.csv`), colonnes « kWh mixtes » et « CO2e mixte (g) » dans les tableaux, légende de `mixed`, avertissement « trois colonnes jamais additionnées », front `qualite-energie-mixte` dans `pareto.csv`. L'énergie `judging` (possession comprise) reste au poste `judging`, hors `total_configuration` (déjà le cas : `POSTES_CONFIGURATION`). `measure/tco.py` : aucun changement.
- Contrats mis à jour : `contracts.md` §1, §4.3, §6, §7 ; AD-17 l'était déjà.

## Tests

- Ajoutés : `tests/unit/measure/test_story_9_8.py` (méthode par combinaison de matériels, meter mixte Windows, GPU demandé non retiré et source `nvml` via `gpu_ids=[0]`, fix-8-8 inchangé sans `gpu`, champ de profil, phase `judging` répartie au prorata avec méthode/source, Juge d'API hors phase, aucune phase sans Juge local) ; `test_story_4_12.py` (colonnes mixed, judging hors Configuration, légende, CSV) ; `test_story_4_13.py` (front mixte).
- Tests existants qui lisaient `measured` : aucun n'a changé de résultat. Les tests de 8.6/fix-8-8 (`test_mode_injecte_donne_methode_et_source`, `test_le_meter_retire_le_gpu_de_codecarbon`) injectent des matériels sans RAM, donc `measured` reste correct ; le cas réel (RAM + `windows_emi`) est couvert par `test_methode_de_la_phase` et `test_meter_mixte_sous_windows`.

## Reports

- Vérification réelle GPU (`nvml`) : en attente de l'accord d'Anaël (ni GPU, ni Ollama, ni mesure réelle lancés).
- `wl calibrer` (Poste `judging` hors Exécution) n'a pas de mesureur d'énergie : ses Juges locaux gardent une énergie non mesurée.
- Vérifier sur le poste réel que la RAM de codecarbon apparaît bien comme `RAM` dans `_hardware` (API privée) ; sinon le cas Windows retomberait sur `measured`.
- Les valeurs `measured` des `costs.csv` d'Exécutions antérieures (Windows `windows_emi`) ne sont pas réétiquetées.

## Commande de vérification

`uv run pytest -q --tb=short tests/unit/measure tests/unit/report/test_story_4_12.py tests/unit/report/test_story_4_13.py tests/unit/runner/test_story_4_5.py`

## Revue

À faire.
