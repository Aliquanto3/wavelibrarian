---
story: "5.1"
title: Annotations humaines et kappa de Cohen
status: done
---

# Story 5.1 : Annotations humaines et kappa de Cohen

## Code Map

- `src/wavelibrarian/stats/kappa.py` : `cohen_kappa(a, b) -> float | None` (fonction pure, sans dépendance).
- `src/wavelibrarian/scoring/calibration.py` : `charger_fichier`, `charger_dossier -> Annotations` (verdicts indexés par (annotateur, `answer_id`, `criterion`)), `answer_ids_de_answers_jsonl`, `rapprocher -> Rapprochement(annotations, ignorees)`.
- Tests : `tests/unit/stats/test_kappa.py`, `tests/unit/scoring/test_calibration.py`.

## Design Notes

- Erreurs en `ConfigError` au chemin pointé : `annotations[3].criterion`, `.verdict`, `.answer_id`, doublon à `annotations[3]`. Un dossier sans `*.yaml`, ou un fichier sans `annotator`, est aussi une `ConfigError` (la story 5.2 en fera le code de sortie 2).
- Verdict : le contrat §4.6 écrit `verdict: yes` sans guillemets, que PyYAML (YAML 1.1) lit comme un booléen. Le chargeur (`SafeLoader` sans résolveur booléen implicite) garde les scalaires en chaînes : seuls `yes` et `no`, nus ou entre guillemets, sont permis ; `on`, `Yes`, `true`, `1` sont refusés. Les clés dupliquées dans un mapping sont refusées.
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

## Revue

Revue Opus du 2026-10-18, après rebase sur `main` (story 4.3).

- medium, second avis 1 : `UnicodeDecodeError` non attrapée (annotations et `answers.jsonl`), exception brute. Corrigé : `ConfigError` au chemin du fichier (« non encodé en UTF-8 »), test `test_fichier_non_utf8`.
- medium, second avis 4 : `annotations: []` partout accepté. Corrigé ici (le chargeur est le point naturel du contrôle) : `charger_dossier` lève `ConfigError` sans aucune annotation ; un fichier vide levait déjà (« mapping attendu »). Reporté à la 5.2 : code de sortie 2 sur toute `ConfigError` du chargeur, et aussi quand `rapprocher` ne garde aucune annotation (toutes absentes de l'Exécution).
- low, second avis 2 : `on`, `off`, `Yes`, `true` nus acceptés comme booléens. Corrigé : chargeur sans booléens implicites, tests paramétrés.
- low, second avis 3 : erreurs de ligne sans nom de fichier. Corrigé : le message cite le fichier, le chemin reste `annotations[i].…` (AC).
- low, second avis 5 : `*.yml` ignoré. Corrigé, test `test_extension_yml_acceptee`.
- low, second avis 6 : clés dupliquées acceptées (la dernière gagnait). Corrigé : `ConstructorError` convertie en `ConfigError`.
- low, second avis 8 et 9 : tests manquants. Corrigé : évaluateur constant face à un mixte (0), classes constantes opposées (0), un seul item (`None`), verdicts refusés.
- low, second avis 10 : jointure inter-annotateurs (Réponses doublement annotées). Reporté à la 5.2, hors AC de la 5.1.
- low, revue : clés inconnues d'une ligne (autres que `answer_id`, `criterion`, `verdict`, `note`) ignorées sans erreur. Consigné, conforme au contrat qui ne les interdit pas.
- info, revue : oracle du kappa vérifié (0,4 calculé à la main, pas recalculé par la formule du code).
