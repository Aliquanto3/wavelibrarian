---
story: "8.6"
title: "Énergie CPU mesurée sous Windows"
status: review
---

# Story 8.6 : Énergie CPU mesurée sous Windows

Exigences : FR-32 ; AD-17 ; `contracts.md` §6 (`wl.energy_source`, arbitrage P4). Constat de départ : `measure/energy.py` ne connaissait pas `windows_emi`, donc l'énergie CPU sous Windows restait `estimated`.

## Réalisé

- `measure/energy.py` : `energy_source(tracker)` donne le mode du compteur lu (`nvml` si un GPU est suivi, sinon le mode matériel, sinon le premier mode connu, sinon `unknown`) ; `CodecarbonMeter.source` le conserve à chaque phase, `FakeMeter.source = "fake"`.
- `measure/tracing.py` (`end_phase(kwh, method, source)`) et `runner/execute.py` : `wl.energy_source` est écrit sur chaque span local (valeur `unknown` si l'énergie est inconnue). `llm/gateway.py` : `ecologits` pour une énergie d'API estimée.
- Rapport : `report/couts.py` compte les spans par source, `report/section_couts.py` affiche la ligne « Source de l'énergie (`wl.energy_source`) ». `report/generer.py` n'est pas touché.
- `windows_emi` ajouté à `_MODES_MATERIELS` (voir la mesure ci-dessous) : méthode `measured` sous Windows.
- Tests unitaires (mode injecté, sans réseau ni compteur) : `intel_rapl`, `intel_power_gadget`, `apple_powermetrics`, `nvml`, `windows_emi`, `cpu_load`, `tdp_constant` et un mode inconnu donnent chacun leur méthode et leur source ; sources écrites dans les spans ; sources au Rapport.

## Mesure réelle (2026-10-18)

Poste : Windows 11, AMD Ryzen 5 7600 (6 coeurs), codecarbon 3.3.1, `gpu_ids=[]`, `CUDA_VISIBLE_DEVICES=-1`, `OMP_NUM_THREADS=4`. Mode détecté par codecarbon pour le CPU : `windows_emi` (matériels suivis : RAM, GPU sans id, CPU). Charge : 4 processus Python/numpy (produit matriciel 300x300 en boucle). Durées : 60 s au repos (`sleep`) et 60 s sous charge, dans les deux ordres. Charge de fond avant chaque série : CPU total 4,5 % à 9,5 % en moyenne sur 30 s (sous le seuil de 15 %), aucune attente nécessaire.

| Répétition | Repos : kWh, W moyens | Charge : kWh, W moyens | Rapport charge / repos |
|---|---|---|---|
| 1 (repos puis charge) | 0,00072937 kWh, 43,5 W | 0,00179040 kWh, 107,4 W | 2,47 |
| 2 (charge puis repos) | 0,00074308 kWh, 44,6 W | 0,00177514 kWh, 105,9 W | 2,39 |
| 0 (essai, mode non relevé) | 0,00088630 kWh, 49,9 W | 0,00178804 kWh, 107,3 W | 2,15 |

Les durées réelles vont de 60,0 à 63,9 s (démarrage du tracker). Les watts incluent la part RAM que codecarbon ajoute à la même mesure.

Critère « le compteur suit la charge » (fixé avant la conclusion) : sur deux répétitions de 60 s au moins, chacune avec le mode `windows_emi` détecté, (a) la puissance moyenne sous charge est au moins 1,5 fois celle du repos, et (b) chaque valeur reste à moins de 10 % de la moyenne des deux répétitions pour la même condition. Résultat : (a) 2,47 et 2,39, soit au moins 1,5 ; (b) repos 43,5 et 44,6 W (écart de 1,3 % à la moyenne), charge 107,4 et 105,9 W (0,7 %). Le critère est rempli.

## Conclusion

Le compteur suit la charge : `windows_emi` est ajouté à `_MODES_MATERIELS`, la méthode vaut `measured` sous Windows, et les spans et le Rapport portent `wl.energy_source=windows_emi`. Limite : une seule machine (Ryzen 5 7600) ; un autre matériel Windows sans EMI donnerait un autre mode (`cpu_load`, `tdp_constant`), resté `estimated`, avec sa source écrite.

## Acceptance Criteria

1. Repos puis charge calibrée de même durée : écart consigné (valeurs, durée, version de codecarbon) ci-dessus.
2. Le compteur suivant la charge, `windows_emi` est dans `_MODES_MATERIELS` ; méthode `measured` ; spans et Rapport portent `wl.energy_source=windows_emi`.
3. (Cas où le compteur ne bougerait pas : `estimated` gardé, `wl.energy_source` écrit quand même ; non retenu ici, le compteur suit la charge.)
4. Tests unitaires de `measure/energy.py` : chaque mode donne sa méthode et sa source, sans réseau ni compteur réel.

## Reports

- Reproduire la mesure sur un second poste Windows (autre CPU, ou Intel) avant de généraliser.
- L'énergie `measured` de `windows_emi` vient du compteur CPU du poste entier, pas du seul processus : le repos du poste (environ 44 W) y est inclus, comme pour RAPL. La part RAM n'est pas mesurée : codecarbon l'ajoute par formule (la RAM n'a pas de mode, `windows_emi` ne lit pas la DRAM). La phase reste `measured` (AC 2, arbitrage P4) ; le Rapport le rappelle dès qu'il y a des kWh `measured`.
- **À arbitrer par Anaël** : faut-il une méthode `mixed` (ou une colonne à part) quand la part RAM d'une phase `measured` est estimée ? Aujourd'hui la règle P4 la compte `measured`.
- Anciennes traces sans `wl.energy_source` : comptées sous `absent` au Rapport.

## Revue

- medium, second avis 1 : `measured` pour une phase dont la RAM est estimée par formule. Corrigé sans changer la règle (AC 2, P4) : spec rectifiée (« CPU et RAM mesurés » était faux), mention au Rapport dès qu'il y a des kWh `measured`, test du cas mixte (`test_cas_mixtes_cpu_ram_gpu`, matériels RAM sans mode, GPU vide, CPU `windows_emi`) ; question `mixed` reportée à Anaël.
- low, second avis 2 : contrat §6 citait `rapl` et omettait `ecologits`, `fake`, `unknown`, `absent`. Corrigé : `contracts.md` aligné sur le code.
- low, second avis 3 : la docstring annonçait `nvml` prioritaire, le code suivait l'ordre de `_hardware`. Corrigé : `nvml` prioritaire explicitement, testé dans les deux ordres.
- low, second avis 4 : `_mode` lu avant la branche GPU. Rejeté : la branche GPU écrase le mode, aucun effet observable (le GPU de codecarbon n'a pas de `_mode`).
- low, second avis 5 : pas de test mixte. Corrigé par le même test que le constat 1 (CPU estimé + GPU mesuré compris).
