---
story: "8.9"
title: "Paquet d'annotation et kappas par Juge au Rapport"
status: review
---

# Story 8.9 : Paquet d'annotation et kappas par Juge au Rapport

Exigences : FR-38, FR-40, SM-5 ; AD-14, AD-20. Dépend de 5.1 (chargeur d'annotations), 5.2 (`calibration.json`) et 8.3 (`completed_with_errors`). Partie code seulement : le paquet réel se génère après la story 8.8.

## Réalisé

- `src/wavelibrarian/report/paquet.py` : `exporter_paquet` écrit `<dossier>/<annotateur>.yaml` au format de `contracts.md` §4.6. Chaque ligne (une par Réponse et par Critère de `criteres_juges`, donc sans `correctness` pour une réponse courte) porte `answer_id`, `criterion`, `verdict: ""`, `note: ""`, plus `question`, `answer` et `cited_anchors` (clés ignorées par le chargeur de 5.1).
- Seules les Réponses `ok` sont tirées ; l'Exécution doit être `completed` ou `completed_with_errors` (sinon `ConfigError`, code 2).
- Tirage : liste triée des `answer_id` éligibles, `random.Random(graine_de_tirage(graine)).sample(...)`, avec `graine_de_tirage(g) = int(sha16("annotation", str(g)), 16)` (même dérivation que `louvain_seed`, AD-20). Graine par défaut : celle de l'Expérience. Stable à graine égale (test d'égalité octet à octet).
- Part double : `round_half_up(nombre_retenu × part)` Réponses vont à tous les annotateurs, les autres sont réparties à tour de rôle. Un seul annotateur : aucune double annotation. Exemple recalculé : 30 × 0,2 = 6 ; 5 × 0,4 = 2 (test : 2 communes, 3 autres réparties 2 + 1, soit des fichiers de 3 et 4 Réponses).
- `cli.py` : `wl annotations exporter <run_id> --vers <dossier> [--annotateurs anael] [--nombre 30] [--graine N] [--part-double 0.2]`. Codes : 0 ; 1 erreur d'écriture ; 2 Exécution introuvable ou non terminée, `--nombre` < 1, `--part-double` hors [0, 1], annotateurs en doublon ou au nom invalide. Moins de Réponses `ok` que demandé : tout est pris, avertissement sur stderr. Ajoutée à `contracts.md` §8.
- `report/generer.py` : section « Calibration des Juges » après « Juges ». Elle lit `calibration.json` du dossier de l'Exécution (sinon `judges.excluded_from`) : par Juge et par Critère, kappa juge-humain, instabilité, nombre d'items, exclusion (avec sa raison) ; puis une table du kappa inter-annotateurs, ou « absent (aucune double annotation) ». Sans fichier : « Calibration absente ». Rien n'est recalculé. Mention ajoutée à `contracts.md` §4.6.
- `tests/unit/report/test_story_8_9.py` (8 tests, Faux LLM, sans réseau) : format, graine, aller-retour 5.1, part double et kappa inter-annotateurs, nombre excessif, `completed_with_errors` accepté et `running` refusé, codes de sortie, section du Rapport.

## Génération du paquet réel (après la story 8.8, Ollama non requis)

```
wl annotations exporter <run_id_de_8.8> --vers annotations/ --annotateurs anael --nombre 30
```

Le run mini-cpu du split dev compte 19 Questions × 4 Configurations, soit au plus 76 Réponses `ok` : 30 Réponses sont atteignables. Ajouter un second annotateur (`--annotateurs anael,<nom> --part-double 0.2`) pour obtenir le kappa inter-annotateurs. Remplir `verdict` (`yes` ou `no`), puis `wl calibrer` (story 8.10).

## Acceptance Criteria

1. Une Exécution terminée donne un fichier par annotateur au format §4.6, prérempli (Question, Réponse, Ancrages cités, Critères à annoter), verdicts vides ; nombre, graine et part double réglables ; tirage stable à graine égale.
2. Un paquet rempli puis rechargé (5.1) passe la validation sans retouche de structure.
3. Le Rapport affiche, depuis `calibration.json`, par Juge et par Critère, kappa juge-humain, instabilité, nombre d'items, exclusion, et le kappa inter-annotateurs.

## Reports

- Un verdict vide (`""`) échoue au chargeur de 5.1 (`yes` / `no` seuls) : le paquet n'est valide qu'une fois rempli, comme l'AC 2 le dit. Aucun changement du chargeur.
- Les Ancrages cités sont donnés par identifiant, sans le texte du Passage : à ajouter si Anaël le demande.
- Le tirage n'est pas stratifié (Configuration, Type de question) : à décider avec Anaël après le premier paquet réel.
