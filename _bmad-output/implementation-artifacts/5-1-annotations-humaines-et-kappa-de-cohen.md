---
story: "5.1"
title: Annotations humaines et kappa de Cohen
status: review
---

# Story 5.1 : Annotations humaines et kappa de Cohen

## Code Map

- `src/wavelibrarian/stats/kappa.py` : `cohen_kappa(a, b) -> float | None` (fonction pure, sans dépendance).
- `src/wavelibrarian/scoring/calibration.py` : `charger_fichier`, `charger_dossier -> Annotations` (verdicts indexés par (annotateur, `answer_id`, `criterion`)), `answer_ids_de_answers_jsonl`, `rapprocher -> Rapprochement(annotations, ignorees)`.
- Tests : `tests/unit/stats/test_kappa.py`, `tests/unit/scoring/test_calibration.py`.

## Design Notes

- Erreurs en `ConfigError` au chemin pointé : `annotations[3].criterion`, `.verdict`, `.answer_id`, doublon à `annotations[3]`. Un dossier sans `*.yaml`, ou un fichier sans `annotator`, est aussi une `ConfigError` (la story 5.2 en fera le code de sortie 2).
- Contradiction relevée : le contrat §4.6 écrit `verdict: yes` sans guillemets, que PyYAML (YAML 1.1) lit comme le booléen `True`. Lecture retenue : booléens YAML et chaînes `"yes"` / `"no"` acceptés ; tout autre type ou valeur est refusé.
- Le doublon se détecte sur (annotateur, `answer_id`, Critère), y compris entre deux fichiers du même annotateur.
- Kappa : table de contingence 2x2 ; `None` si vecteurs vides ou accord attendu égal à 1 (une seule classe commune) ; longueurs différentes = `ValueError`.
- `rapprocher` compare à l'`answer_id` complet (run, config, condition, tier, phase, Question) : une autre phase ou un autre tier est ignoré et signalé, une fois par identifiant.
- `scoring` n'importe ni `report` ni `runner` (AD-1) ; `stats` n'importe rien du projet (AD-22).

## Tâches et critères

- [x] Annotations indexées par (annotateur, `answer_id`, `criterion`), verdict booléen, deux annotateurs : `test_chargement_deux_annotateurs`.
- [x] Critère hors liste, verdict hors `yes`/`no`, doublon : `ConfigError` au chemin : `test_erreurs_au_chemin`, `test_verdict_yes_no_non_guillemete_et_autre_type`.
- [x] `answer_id` absent d'`answers.jsonl` signalé et ignoré, identifiant complet : `test_rapprochement_ignore_et_signale`, `test_answers_jsonl_illisible`.
- [x] Table 20/5/10/15 donne 0,4 à 1e-12 : `test_table_connue`.
- [x] Vecteurs identiques = 1 ; une seule classe = `None` ; longueurs différentes = `ValueError` : `test_vecteurs_identiques`, `test_classe_unique_indefini`, `test_longueurs_differentes`.

## Auto Run Result

- Statut : review. Voir le rapport de l'agent pour les comptes de tests, pyright et contrôle rapide.
- Reports : calcul juge-humain, instabilité, kappa inter-annotateurs, `calibration.json`, commande `wl calibrer` et exclusion : story 5.2. `answer_ids_de_answers_jsonl` ne lit que la clé `answer_id` ; le chemin de `answers.jsonl` de l'Exécution est à fournir par la commande.
