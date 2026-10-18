---
story: "8.9"
title: "Paquet d'annotation et kappas par Juge au Rapport"
status: review
---

# Story 8.9 : Paquet d'annotation et kappas par Juge au Rapport

Exigences : FR-38, FR-40, SM-5 ; AD-14, AD-20. Dépend de 5.1 (chargeur d'annotations), 5.2 (`calibration.json`) et 8.3 (`completed_with_errors`). Partie code seulement : le paquet réel se génère après la story 8.8.

## Réalisé

- `src/wavelibrarian/report/paquet.py` : `exporter_paquet` écrit `<dossier>/<annotateur>.yaml` au format de `contracts.md` §4.6. Chaque ligne (une par Réponse et par Critère de `criteres_juges`, donc sans `correctness` pour une réponse courte) porte `answer_id`, `criterion`, `verdict: ""`, `note: ""`, plus `question`, `reference_answer`, `answer` et `cited_anchors`, et, sur la première ligne de chaque Réponse, `reference_passages` et `context_passages` (clés ignorées par le chargeur de 5.1, ajoutées en revue).
- Seules les Réponses `ok` sont tirées ; l'Exécution doit être `completed` ou `completed_with_errors` (sinon `ConfigError`, code 2).
- Tirage : liste triée des `answer_id` éligibles, `random.Random(graine_de_tirage(graine)).sample(...)`, avec `graine_de_tirage(g) = int(sha16("annotation", str(g)), 16)` (même dérivation que `louvain_seed`, AD-20). Graine par défaut : celle de l'Expérience. Stable à graine égale (test d'égalité octet à octet).
- Part double : `round_half_up(nombre_retenu × part)` Réponses vont à tous les annotateurs, les autres sont réparties à tour de rôle. Un seul annotateur : aucune double annotation. Exemple recalculé : 30 × 0,2 = 6 ; 5 × 0,4 = 2 (test : 2 communes, 3 autres réparties 2 + 1, soit des fichiers de 3 et 4 Réponses).
- `cli.py` : `wl annotations exporter <run_id> --vers <dossier> [--annotateurs anael] [--nombre 30] [--graine N] [--part-double 0.2]`. Codes : 0 ; 1 erreur d'écriture ; 2 Exécution introuvable ou non terminée, `--nombre` < 1, `--part-double` hors [0, 1], annotateurs en doublon ou au nom invalide. Moins de Réponses `ok` que demandé : tout est pris, avertissement sur stderr. Ajoutée à `contracts.md` §8.
- `report/generer.py` : section « Calibration des Juges » après « Juges ». Elle lit `calibration.json` du dossier de l'Exécution (sinon `judges.excluded_from`) : par Juge et par Critère, kappa juge-humain, instabilité, nombre d'items, exclusion (avec sa raison) ; puis une table du kappa inter-annotateurs, ou « absent (aucune double annotation) ». Sans fichier : « Calibration absente ». Rien n'est recalculé. Mention ajoutée à `contracts.md` §4.6.
- `tests/unit/report/test_story_8_9.py` (8 tests à l'implémentation, 15 après revue, Faux LLM, sans réseau) : format, graine, aller-retour 5.1, part double et kappa inter-annotateurs, nombre excessif, `completed_with_errors` accepté et `running` refusé, codes de sortie, section du Rapport.

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
- Le texte des Passages est donné tel que les Juges le reçoivent (Passages fournis au Generator, Ancrages de référence) ; les Ancrages cités restent donnés par identifiant. Le paquet réel (après 8.8) est à relire par Anaël pour la taille des fichiers : un contexte proche de 8 000 tokens par Réponse donne des fichiers longs.
- Le tirage n'est pas stratifié (Configuration, Type de question) : à décider avec Anaël après le premier paquet réel.

## Revue

Revue unique (Opus) avec la liste du second avis (Haiku).

| # | Sévérité | Source | Constat | Décision |
|---|---|---|---|---|
| 1 | high | second avis | Relancer l'export sur un dossier rempli écrase les verdicts saisis (`write_text` inconditionnel). | Corrigé : tout `*.yaml` / `*.yml` présent dans `--vers` fait refuser l'export (code 2, message qui nomme les fichiers et `--ecraser`) ; option `--ecraser` ajoutée à `contracts.md` §8. Tests `test_dossier_deja_rempli_refuse_sans_ecraser` et bout en bout. |
| 2 | medium | second avis | `Anael` et `anael` (même fichier sous NTFS) et les noms réservés Windows (`CON`, `NUL`, `COM1`…) acceptés. | Corrigé : doublons comparés sans casse, noms réservés refusés (code 2). Test paramétré. |
| 3 | medium | second avis | Le paquet ne donne pas le texte des Passages ni la réponse de référence : `faithfulness` et `correctness` ne s'annotent pas avec le seul paquet. | Corrigé : le chargeur de 5.1 ignore les clés inconnues, d'où des clés de contexte : `reference_answer` sur chaque ligne ; `reference_passages` (texte des Ancrages de référence, Corpus relu comme pour le Rapport, empreinte comparée) et `context_passages` (`context_texts` de la Réponse) sur la première ligne de chaque Réponse. C'est exactement le `JudgeInput` du panel. Textes multilignes en bloc `|`. `ResolveurCorpus.textes` ajouté. |
| 4 | low | second avis | Pas de contrôle que la Configuration et le Corpus de la Réponse existent. | Rejeté : le paquet n'utilise pas la Configuration ; une Réponse dont la Question manque au Jeu est déjà écartée ; un Corpus absent ou modifié laisse `reference_passages` vide et l'alerte du résolveur est affichée sur stderr. |
| 5 | low | second avis | L'aller-retour ne teste que `charger_dossier`. | Corrigé : `test_bout_en_bout_export_calibrer_rapport` (CLI d'export, remplissage, `wl calibrer` au Faux LLM, Rapport : lignes des Juges et kappa inter-annotateurs). |
| 6 | low | second avis | Des YAML d'un export précédent restent dans `--vers` et sont chargés par `wl calibrer`. | Corrigé avec le n° 1 : refus sans `--ecraser` ; avec `--ecraser`, les YAML d'autres annotateurs sont signalés sur stderr. |
| 7 | low | second avis | `calibration.json` lu sans contrôle de `run_id`. | Corrigé en partie : la section nomme l'Exécution source quand elle diffère (cas normal de `judges.excluded_from`, calibration d'une Exécution antérieure) ; pas de refus, ce serait le cas nominal. |
| 8 | low | revue | Vérifié : clés du `calibration.json` réel (`runner/calibrer.py`) identiques à celles que lit la section ; tirage, part double et codes de sortie conformes aux AC. | Sans correctif. |

## Paquet réel

- Run source : `20261018-115941-a2a512` (story 8.8, `mini-cpu`, 19 Questions du split dev × 4 Configurations, 76 Réponses `ok`, statut `completed_with_errors` après la reprise : 7 Critères sans verdict de panel, sans effet sur le tirage).
- Fichier : `corpora/minicorpus/annotations/anael.yaml` (annotateur `anael`, 304 Ko).
- Contenu : 40 Réponses (92 lignes Réponse × Critère), 0 doublement annotée, verdicts vides. Sortie de la commande : « Paquet de 40 Réponse(s) dont 0 doublement annotée(s), 1 fichier(s) dans corpora\minicorpus\annotations ». Avertissement : 1 Question (q-044) a un Ancrage de référence non résolu sur le Corpus de la phase `base` (document créé par le Scénario).
- Commande exacte (donnée par l'orchestrateur) : `uv run wl annotations exporter 20261018-115941-a2a512 --vers corpora/minicorpus/annotations --annotateurs anael --nombre 40`, avec `WL_HOME=C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0`. Graine par défaut (celle de l'Expérience).
- Point d'attention : le paquet contient 4 lignes de q-044 (rag-naif et raptor, `completeness` et `faithfulness`), dont l'Ancrage de référence (`chronique-1415.md`) est absent en phase `base`. Le paquet n'a pas été modifié ; Anaël peut annoter ces lignes en le sachant ou les retirer avant `wl calibrer`.
- Reste à Anaël : remplir `verdict` (`yes` ou `no`), puis `wl calibrer` (story 8.10). Pas de second annotateur, donc pas de kappa inter-annotateurs.
