---
story: "9.8"
title: "Énergie : méthode mixte, poste judging et GPU du profil gpu"
status: review
---

# Story 9.8 : Énergie : méthode `mixed`, poste `judging`, GPU du profil `gpu`

Exigences : FR-31, FR-32 ; AD-17 (amendé) ; `contracts.md` §1, §4.3, §6, §7. Origines : question `mixed` de la 8.6, GPU et poste `judging` non mesurés de fix-8-8.

## Réalisé

- `measure/energy.py` : `EnergyMethod` gagne `mixed`. `energy_method(tracker, gpu)` : `measured` si toutes les parts suivies sont lues par un compteur matériel, `mixed` si une part est lue et une autre estimée (la RAM de codecarbon l'est toujours), `estimated` si aucune (revue, décision du 2026-10-26). `CodecarbonMeter(gpu=...)` : `gpu_ids=None` (tous les GPU visibles, `CUDA_VISIBLE_DEVICES` respecté par codecarbon 3.3.x) et pas de `_retirer_gpu` quand `energy.gpu` est vrai (source `nvml`) ; sinon comportement fix-8-8 inchangé.
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

### Passe 1 (2026-10-26, SHA revu d3a5ed1)

Branche à jour sur `main` (95ef5be), pas de rebase.

- Important · medium · second avis 1 · corrigé : [RAM, CPU lu, GPU] donnait `measured` et [RAM, CPU lu] `mixed`. `measured` seulement si toutes les parts suivies sont lues, `mixed` dès qu'une part est estimée (RAM comprise), `estimated` sinon. Tests, docstring, légende du Rapport, `contracts.md` §6 et 3e AC d'`epics.md` réalignés. Conséquence : avec codecarbon, qui ajoute toujours la RAM, un GPU lu donne `mixed`.
- Important · medium · second avis 2 · corrigé : `gpu_ids=[0]` en dur. Remplacé par `gpu_ids=None` (tous les GPU visibles ; codecarbon 3.3.x lit `CUDA_VISIBLE_DEVICES`, vérifié dans sa source). `_materiels_suivis` compte le GPU demandé même quand aucun indice n'est encore résolu (sinon `None` l'aurait écarté). Tests.
- Nit · medium · second avis 3 · consigné : la phase `judging` couvre aussi les attentes des Juges d'API et les Critères automatiques, et son énergie va aux seuls spans locaux. C'est la convention des autres phases ; c'est maintenant écrit dans la légende du Rapport et dans `contracts.md` §6.
- Important · medium · second avis 4 · corrigé : une phase faite seulement de hits du Cache répartissait son énergie à parts égales sur ces hits. `Tracer.end_phase` exclut désormais les hits de la répartition (0 kWh, méthode de la phase) ; `spread_energy` est inchangée (répartition à parts égales entre spans réels de durée nulle), donc les phases index et query ne bougent pas (tests 4.5, 4.7, fix-8-8 et measure verts). Test.
- Nit · low · second avis 5 · consigné : les spans `judge` locaux restent en mémoire jusqu'à `end_phase` ; après un kill -9, ils sont perdus et leurs appels sont refaits à la reprise (même limite que les phases index et query).
- Nit · low · second avis 6 · corrigé : test de bout en bout au profil `cpu` (`make_meter`, RAM + `windows_emi` + GPU retiré, résultat `mixed`).
- Nit · low · second avis 7 · rejeté : `kwh_local` additionne les trois méthodes pour calculer la possession en €. C'est légitime pour un coût ; l'affichage de l'énergie (colonnes, CSV, fronts) ne les additionne jamais (vérifié dans `section_couts.py`, `ligne_csv` et `fronts._kwh`).
- Nit · low · second avis 8 · rejeté : codecarbon fait partie de l'extra optionnel `energy` (`pyproject.toml`), absent du `.venv`. Les doublures `sys.modules` sont donc justifiées (frontière externe). Dépendances inchangées.
- Nit · low · second avis 9 · corrigé : l'assertion tautologique `q.real + q.fake < q.real + q.fake + j.fake` (`test_story_4_12.py`) est remplacée. Test de reprise ajouté : `_juger` interrompu avec la phase ouverte, phase refermée, puis second passage.
- Nit · low · second avis 10 · reporté : Filtre closed-book hors phase `judging`, hors périmètre.
- Important · medium · revue · corrigé : le diff de `contracts.md` supprimait des lignes de la story 9.2 (justification de Juge « ≤ 200 car. » au §5, attribut `wl.justification_truncated` au §6). Lignes restaurées depuis `main`.
- Complexité : 0 constat. `end_phase` reste en O(n) sur le tampon de la phase.
