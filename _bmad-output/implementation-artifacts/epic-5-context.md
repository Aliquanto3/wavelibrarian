# Epic 5 Context: Calibrer les juges sur des annotations humaines

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Permettre à Anaël de vérifier que les Juges du Panel s'accordent avec un humain et restent stables. Il annote des Réponses dans un fichier YAML par annotateur, lance `wl calibrer`, et obtient pour chaque Juge et chaque Critère le kappa juge-humain, le kappa entre annotateurs et le taux d'instabilité sur au moins 5 passes. Les Juges sous le seuil (0,6) sont exclus des Rapports suivants, qui le mentionnent.

## Stories

- Story 5.1: Annotations humaines et kappa de Cohen
- Story 5.2: Commande `wl calibrer` et exclusion des Juges

## Requirements & Constraints

- Annotations : un fichier YAML par annotateur ; verdict booléen par (annotateur, `answer_id`, Critère). Critères permis : `correctness`, `completeness`, `faithfulness`, verdicts `yes`/`no`. Critère ou verdict inconnu, ou doublon, donne une `ConfigError` au chemin pointé (`annotations[3].criterion`). Un `answer_id` absent de `answers.jsonl` de l'Exécution est signalé et ignoré ; c'est l'identifiant complet de la Réponse (tier et phase compris).
- Kappa de Cohen binaire : exact à 1e-12 sur table de contingence connue ; vecteurs identiques = 1 ; accord parfait sur une seule classe (indéfini) = `None` sans exception ; longueurs différentes = `ValueError`.
- Calibration : chaque Juge admissible du réservoir note chaque Réponse annotée au moins 5 fois (`pass_id` 0 à 4), les passes 1 à 4 jamais servies par le Cache de réponses. Spans au Poste `judging`. Les verdicts vont dans un fichier de calibration de l'Exécution ; `verdicts.jsonl` n'est pas modifié.
- Kappa juge-humain : verdict de la passe 0 contre l'annotation, chaque annotateur compté séparément. Instabilité : part des Réponses dont les verdicts diffèrent entre passes. Kappa entre annotateurs : par Critère, sur les Réponses doublement annotées.
- Exclusion : kappa sous `kappa_threshold` (0,6 par défaut) = `excluded: true` avec raison, affichée en français. Un kappa `None` n'exclut pas mais est signalé.
- `calibration_judge` optionnel : ne note que les Réponses doublement annotées, résultats à part.
- Une nouvelle Expérience avec `judges.excluded_from: <calibration.json>` écarte le Juge exclu du Panel ; le Rapport mentionne l'exclusion avec la date du fichier. Si ce Juge a servi au Filtre closed-book, `wl calibrer` avertit de relancer `wl questions closed-book`.
- Dossier sans annotation valide ou `run_id` inconnu : code de sortie 2, message en français.

Contraintes du run autonome :
- Aucun réseau ni API dans les tests : Faux LLM (`fake-llm-a/b/c`), profil `test`.
- Pas d'Ollama avant le go d'Anaël (seuls `/api/version`, `/api/ps`, `/api/tags` tolérés), pas de GPU.
- Pas d'extra lourd (`local`, `docling`), pas de téléchargement de plus de 1 Go ; `OMP_NUM_THREADS=4`, RAM ≤ 6 Go, pas de pytest parallèle.

## Technical Decisions

- Modules : `scoring/calibration.py` (chargement, rapprochement, calcul), `stats/kappa.py` (fonction pure, AD-22), commande `wl calibrer <experience.yaml> --annotations <dossier> --run <run_id>` dans `cli.py` (messages en français, `click`/`typer` d'usage encore en anglais, voir reports).
- Le Panel se forme dans `config/panel.py` (AD-14) : les `panel_size` premiers modèles du réservoir `judges.pool` hors Famille des `answer_producer` et hors exclus par `calibration.json` ; moins de 2 = refus à la validation. Le Juge est `components/judges/llm.py` (story 3.4), qui note tous les Critères en un seul appel et refait une passe hors cache par `pass_id`.
- Réglages `judges` : `calibration_passes: 5`, `kappa_threshold: 0.6`, `calibration_judge`, `excluded_from`. `wl calibrer` impose au moins `calibration_passes`.
- Format `calibration.json` retenu en story 1.6, validé strictement : par Juge, `excluded` booléen strict et `criteria` (par Critère : kappa, instabilité, nombre d'items), plus le kappa inter-annotateurs. Réutiliser le modèle de validation existant plutôt qu'en créer un second.
- Coût : toute commande hors Exécution ouvre `ctx.scope(post="judging")` avant tout appel LLM (la passerelle refuse sinon) ; traces dans `WL_HOME/hors-execution/<run_id>/`. Passerelle, Plafond et Cache de réponses s'appliquent (`pass_id` contourne le cache).
- `JudgeInput` se construit avec les textes des Ancrages et les `context_texts` réellement fournis au Generator (`faithfulness`).
- Couches (AD-1) : `scoring` ne dépend pas de `report` ni de `runner`.

## Cross-Story Dependencies

- 5.1 (chargement, kappa) précède 5.2 (commande, exclusion, `calibration.json`).
- Dépend de l'epic 4 pour une Exécution terminée (`answers.jsonl`, Panel, runner) et de l'epic 3 pour le Juge LLM et le Filtre closed-book (`closed_book_judge` : choisir avec filtre de Famille, AD-14).
- La story 5.2 s'appuie sur la validation de l'epic 1 (story 1.6) pour `excluded_from` et le contrôle de `calibration_judge` (préflight, story 1.12).

## Reports hérités

- Écrire `calibration.json` au format §4.6 retenu en 1.6 (par Juge, `excluded` booléen strict, `criteria`).
- Le préflight contrôle tout le réservoir de Juges et `calibration_judge` (1.12).
- Panel (epic 4) : construire `JudgeInput` avec Ancrages et `context_texts`, ouvrir `ctx.scope(post="judging")` (3.4).
- 3.5 : refuser une justification vide si le contrat l'exige (`CriterionVerdict`) ; Juge par défaut avec filtre de Famille (AD-14) au lieu de `judge_pool[0]`.
- Commandes hors Exécution : afficher le coût du Juge (somme du registre au Poste `judging`) ; `ctx.scope` obligatoire ; libération manuelle d'une réservation `hors_execution` orpheline possible (3.2, 3.5).
- Transverse CLI : erreurs d'usage click/typer en anglais (3.1).
- Runner : garder le contexte vivant (`with`) pendant toute l'Exécution, sinon `run.lock` est libéré ; `RunContext` concret (3.2).
- Le Rapport exclut des scores principaux les Questions contaminées (3.6) ; il doit afficher les Juges exclus (epic 4, contrats §7).
