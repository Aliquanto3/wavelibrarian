---
story: "5.2"
title: Commande `wl calibrer` et exclusion des Juges
status: review
---

# Story 5.2 : Commande `wl calibrer` et exclusion des Juges

## Code Map

- `src/wavelibrarian/cli.py` : commande `wl calibrer <experience.yaml> --annotations <dossier> --run <run_id> [--sortie <calibration.json>]`. Codes : 0, 1, 2 (Expérience invalide, Exécution inconnue, dossier sans annotation valide, aucune annotation sur une Réponse de l'Exécution), 3 (Plafond), 4 (préflight du réservoir de Juges et de `calibration_judge`, ou fournisseur injoignable).
- `src/wavelibrarian/runner/calibrer.py` : orchestration (`calibrer`), qui construit le Contexte hors Exécution (`execution=False`, traces dans `WL_HOME/hors-execution/<id>/`), appelle le Juge `llm` au Poste `judging`, écrit `calibration_verdicts.jsonl` (dans le dossier de l'Exécution) et `calibration.json` ; `avertissements_closed_book`.
- `src/wavelibrarian/scoring/calibration.py` : calcul pur `fiches_du_juge` (kappa passe 0 contre chaque annotateur, instabilité, items), `kappa_inter_annotateurs`, `doublement_annotees`, `decider_exclusion`.
- `src/wavelibrarian/report/generer.py` : la ligne « Juges exclus par la calibration » ajoute la date du fichier (`created_at`, sinon date de modification).
- Tests : `tests/unit/scoring/test_calibration_calcul.py`, `tests/unit/runner/test_story_5_2.py`.

## Design Notes

- Réservoir admissible : `judges.pool` (sinon celui du profil), entier, sans le plafond `panel_size`. Pour une Réponse, un Juge est admissible si sa Famille diffère de celles des `answer_producers` de sa Configuration (AD-14). Un Juge sans aucune Réponse admissible est signalé et non calibré.
- Un appel par (Juge, Réponse, passe) note les seuls Critères jugeables ET annotés pour cette Réponse (`correctness` exclu d'une réponse courte). `pass_id` de 0 à `calibration_passes - 1` ; la passe 0 peut venir du Cache, les suivantes le contournent (passerelle, story 3.4).
- Kappa juge-humain : verdict de la passe 0 contre chaque annotation (une paire par annotateur) ; `n_items` compte ces paires. Instabilité : part des Réponses annotées, notées à au moins deux passes, dont les verdicts diffèrent. Un Juge en échec sur une passe est consigné en avertissement, sans arrêter la commande.
- Exclusion : au moins un kappa défini sous `kappa_threshold` ; `reason` en français ; un kappa `None` n'exclut pas mais est signalé (sortie et champ `warnings`).
- `calibration_judge` : ne note que les Réponses doublement annotées, résultats sous `calibration_judge` (`model`, `criteria`), jamais exclu. Il peut aussi être dans `pool` : il y est alors calibré normalement.
- Format `calibration.json` : `run_id`, `experiment_id`, `created_at`, `kappa_threshold`, `passes`, `annotators`, `judges.<modèle>` (`excluded` booléen strict, `reason`, `warnings`, `criteria.<critère>` : `kappa`, `instability`, `n_items`), `inter_annotator` (liste de couples d'annotateurs, kappa et nombre de Réponses par Critère), `calibration_judge` si déclaré. Relu tel quel par `excluded_judges` (story 1.6).
- Textes de référence : Corpus de la Configuration (parser du `corpus.yaml`), Corpus du Scénario pour la phase `after_update` ; pas de sous-corpus de Palier (les Ancrages de référence y sont par construction). `context_texts` de la Réponse vont à `faithfulness`.
- Avertissement closed-book : pour chaque Juge exclu qui est le `closed_book_judge` (réservoir du profil) d'un modèle testé (`closed_book_models` du profil ou `contaminated_by` du Jeu), et si le Jeu a des Questions libres, la commande demande de relancer `wl questions closed-book`.
- Coût : somme des `wl.cost` des spans `judging` de la commande, par devise. Rien n'est écrit si le Plafond est atteint (code 3).

## Tâches et critères

- [x] `pass_id` 0 à 4, cinq passes par Juge et Réponse annotée, spans `judging`, `verdicts.jsonl` inchangé : `test_cinq_passes_par_juge_et_reponse_annotee_hors_cache`.
- [x] `calibration.json` (kappa, instabilité, items, `excluded`, kappa inter-annotateurs) : `test_calibration_json_kappa_instabilite_items_et_inter_annotateurs`, `test_kappa_juge_humain_instabilite_et_items_a_la_main` (oracle à la main : kappa 1/3, instabilité 0,25).
- [x] Exclusion affichée en français ; kappa indéfini non exclu et signalé : `test_juge_exclu_affiche_en_francais`, `test_kappa_indefini_n_exclut_pas_mais_est_signale`, `test_exclusion_sous_le_seuil_et_kappa_indefini_signale`.
- [x] `calibration_judge` à part, doublement annotées seulement : `test_juge_de_calibration_ne_note_que_les_doublement_annotees`.
- [x] `excluded_from` écarte le Juge du Panel, le Rapport cite l'exclusion et la date ; avertissement closed-book : `test_excluded_from_ecarte_le_juge_du_panel_et_le_rapport_le_mentionne`, `test_avertit_de_relancer_closed_book_si_le_juge_exclu_y_a_servi`.
- [x] Code 2 : dossier sans annotation, `run_id` inconnu, annotations hors Exécution : `test_code_2_run_inconnu_dossier_vide_et_annotations_hors_execution`.

## Auto Run Result

- Statut : review. Faux LLM seul ; aucun test `real_*`, aucun appel Ollama.
- Reports vers 4.14 (conformité, vérifications réelles) : exécuter `wl calibrer` sur Ollama local avec de vrais Juges (cache de passes, instabilité réelle d'un modèle 4B, durée et mémoire GPU) ; vérifier la notation par lots et le seuil de 0,6 sur de vraies annotations.
- Reports vers 4.15 : affichage au Rapport des kappas et instabilités par Juge (ici seule l'exclusion et la date sont citées) ; choisir si la calibration d'un Palier ou d'une phase `after_update` doit avoir son propre Corpus de référence.
- Hors périmètre, consigné : une Expérience qui change de `judges.pool` après la calibration garde un `calibration.json` pour d'autres Juges (ignorés) ; un Juge absent du fichier n'est pas exclu.
