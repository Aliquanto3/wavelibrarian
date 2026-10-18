---
story: "4.11"
title: "Rapport : scores, recherche et comparaisons appariées"
status: review
---

# Story 4.11 : Rapport : scores, recherche et comparaisons appariées

## Code Map

- `src/wavelibrarian/report/lecture.py` (nouveau) : lecteurs des fichiers de l'Exécution (`charger` -> `Execution`) ; `lire_reponses` (la dernière ligne d'une clé fait foi), `lire_panel`, `lire_resolue`, `lire_jeu`. `report` n'importe pas `runner` (AD-1) : ces lecteurs refont ceux de `runner/rundir.py`.
- `src/wavelibrarian/report/scores.py` (nouveau) : `evaluer(ex, resoudre) -> Resultats` (comptes par statut, `scores`, `contaminees`, `recherche`, `paires`) ; `qualite` (définition unique de la Qualité, AD-22).
- `src/wavelibrarian/report/ancrages.py` (nouveau) : `resolveur_de` résout les Ancrages de référence sur le Corpus de la phase (Corpus après Scénario pour `after_update`), paresseusement.
- `src/wavelibrarian/report/generer.py` (nouveau) : `generer_rapport(run_dir, wl_home=)` écrit `report/report.md`, `scores.csv`, `retrieval.csv`, `pairs.csv` ; `section_fidelite` (7.3) y est branchée.
- `src/wavelibrarian/core/jsonl.py` (nouveau) : `lire_jsonl` (ignore une ligne non JSON, journalisée) et `terminer_ligne` (ajoute `\n` si le fichier ne se termine pas par un saut de ligne). Utilisés par `runner/rundir.py` (`read_answers`, `read_verdicts`, `read_panel`, `JsonlWriter`), `runner/resume.py` (`cles_tracees`) et `measure/tracing.py` (`JsonlSpanExporter`, à la reprise).
- `src/wavelibrarian/cli.py` : `wl run` génère le Rapport après l'Exécution, y compris sur un arrêt au plafond avant le code 3 ; nouvelle commande `wl rapport <run_id>`.
- Tests : `tests/unit/report/test_story_4_11.py`.

## Design Notes

- Groupement : toutes les grandeurs par (config_id, condition, tier, phase). Seules les Réponses `ok` sont notées ; `error`, `inapplicable` et `budget_exceeded` sont comptées (section « Réponses non notées »), jamais jugées. `non jugées` : Réponse `ok` sans verdict de Panel pour l'un des cinq Critères (cas `unjudged` du manifeste).
- `scores.csv` : une ligne par groupe, Type de question (plus `all`) et Critère ; la Qualité y figure sous `criterion = quality` (définie par §7, ce n'est pas un des cinq Critères). `value` est un taux, jamais un score global. IC : `bootstrap_ci` avec `experiment.stats` (2 000, 95 %).
- Graines (AD-20) : `graine_derivee(seed, config_id, condition, tier, phase, type, critère)` pour chaque IC ; `graine_derivee(seed, a, b, condition, tier, phase, métrique)` pour une paire. Le Rapport régénéré est identique octet pour octet (`test_rapport_regenere_identique_wl_rapport`).
- Contaminées (FR-12) : exclues de `scores.csv`, `retrieval.csv`, `pairs.csv` et du tableau des scores ; leur Qualité figure dans la section « Questions contaminées ». Le runner les juge déjà (il ne connaît pas la contamination).
- Contexte parfait (FR-17) : lignes propres dans les CSV (colonne `condition`) et section « Contexte parfait » séparée. La recherche n'est mesurée qu'en Condition standard : en contexte parfait le runner fournit les Ancrages de référence (`provided`, rappel 1 par construction, y compris pour `no_context`, qui n'a pas de recherche). Cela exclut `no_context` de `retrieval.csv`.
- Recherche : rappel@5, MRR et nDCG@5 par Réponse (`retrieval_metrics`, 4.9) puis moyenne par Type, IC bootstrap, colonne `method` reprise d'`Answer.retrieval_method`. Une Question sans Ancrage de référence (`unanswerable`) n'a pas de métrique.
- Paires : pour chaque couple de Configurations d'un même (condition, tier, phase), McNemar exact (`mcnemar.compare`) sur la Qualité et les cinq Critères, bootstrap apparié (`compare_continu`) sur les trois métriques de recherche. `compare` qui renvoie `None` (aucune Question commune) donne une ligne à `n_common` 0, sans `diff` ni `p_value` : le Rapport n'en tire aucune « Qualité égale » (le point mort est en 4.12). Une métrique absente des deux côtés n'a pas de ligne.
- Multiplicité : aucune correction (absente de §7). Le Rapport l'écrit sous le tableau des comparaisons, avec le nombre de comparaisons.
- Lecteurs tolérants (report de 4.8) : une ligne qui n'est pas un objet JSON est ignorée et journalisée. `JsonlWriter` et `JsonlSpanExporter` terminent le fichier par `\n` avant d'y ajouter : la ligne tronquée reste seule sur sa ligne. Le contrat §5 ne dit rien de plus ; seule une troncature produit une telle ligne (écriture d'un bloc, vidée sur disque).
- Fichiers lus : `experiment.resolved.yaml`, `experiment.sha256`, `manifest.json`, `corpus_profile.json`, `applicability.json`, `answers.jsonl`, `panel.jsonl`, `wiki_fidelity.json`, plus le Jeu (`experience.questions`, pour le Type, la contamination et les Ancrages de référence ; §7 et 4.9 le prévoient) et le Corpus (cache de parsing de `WL_HOME`) pour résoudre les Ancrages. `verdicts.jsonl` et `traces.jsonl` ne servent pas à cette story (coûts, latence : 4.12).
- Écarts de lecture, signalés : (1) AC `pairs.csv` donne sept colonnes, mais une paire ne se compare qu'à l'intérieur d'un groupe (§7) ; `condition`, `tier`, `phase` sont ajoutées après les sept colonnes. (2) `retrieval.csv` ajoute `n` avant `method`. (3) `scores.csv` porte une ligne `question_type = all` par Critère, pour le tableau de tête.
- Hors périmètre : coûts, énergie, latence, point mort (4.12) ; Fraîcheur, Paliers, `pareto.csv`, tableau de tête, `--exporter-front` (4.13).

## Tâches et critères

- [x] AC 1 : `report.md` : Expérience (lien et empreinte), profil, partie, `models_frozen_at`, modèles, Profil de corpus, Panel admissible, Juges exclus, égalités : `test_wl_run_ecrit_le_rapport_complet_avec_l_entete` ; régénération par `wl rapport` : `test_rapport_regenere_identique_wl_rapport`.
- [x] AC 1 (suite) : grandeurs des seuls fichiers de l'Exécution, par (config_id, condition, tier, phase) : `test_scores_csv_colonnes_et_valeurs_recalculees`.
- [x] AC 2 : colonnes de `scores.csv`, IC de l'Expérience, aucune colonne globale, Qualité (`unanswerable` par `abstention_correctness`) : `test_scores_csv_colonnes_et_valeurs_recalculees`, `test_qualite_unanswerable_suit_abstention_correctness`, `test_aucun_score_global_dans_les_colonnes`.
- [x] AC 3 : contaminées exclues et section à part ; contexte parfait en section étiquetée : `test_questions_contaminees_exclues_des_scores_principaux`, `test_contexte_parfait_a_sa_propre_section_etiquetee`.
- [x] AC 4 : `retrieval.csv` (rappel, MRR, nDCG, `method`, sans `no_context`) : `test_retrieval_csv_sans_no_context_avec_methode_et_valeurs_a_la_main` ; `pairs.csv` (McNemar contre `scipy.stats.binomtest`, bootstrap apparié, `n_common`) : `test_pairs_csv_mcnemar_exact_et_bootstrap_apparie`.
- [x] AC 5 : inapplicables listées avec leur raison : `test_inapplicables_listees_avec_leur_raison`.
- [x] AC 6 : Rapport partiel généré par `cli.py` avant le code 3, signalé en tête, `budget_exceeded` jamais noté : `test_plafond_atteint_rapport_partiel_en_tete_puis_code_3`.
- [x] Reports 4.8 : lecteurs tolérants, `\n` avant ajout : `test_lecteurs_tolerent_une_derniere_ligne_tronquee_et_l_ajout_la_termine`, `test_terminer_ligne_et_ligne_invalide_au_milieu`, `test_exporteur_de_traces_termine_la_ligne_tronquee_a_la_reprise`.
- [x] Reports 4.9 : `unjudged` affiché : `test_critere_sans_verdict_est_affiche_non_juge`.
- [x] Reports 4.10 : `graine_derivee` (même test que le premier AC 2), `None` de `compare` : `test_paire_sans_question_commune_n_a_pas_de_p_valeur`, multiplicité : `test_rapport_signale_l_absence_de_correction_de_multiplicite`.
- [x] Report 7.3 : `section_fidelite` branchée : `test_fidelite_du_wiki_branchee_dans_le_rapport`.

## Auto Run Result

- Statut : review. Comptes de tests, pyright, lint-imports et contrôle rapide dans le rapport de l'agent.
- Reports traités : lecteurs tolérants et `\n` avant ajout (4.8) ; `read_answers`/dernière ligne et `budget_exceeded` jamais noté (4.8) ; `retrieval.csv` (4.9) ; `unjudged` affiché (4.9) ; `pairs.csv`, `graine_derivee`, `None` de `compare`, multiplicité (4.10) ; contaminées (FR-12) ; `section_fidelite` (7.3).
- Reports non traités : Citation « hors du Corpus » jugée sur le sous-corpus du Palier (4.9) : renvoyé à 4.13, qui tire les Paliers ; `citation_correctness` est écrite par le runner sur le Corpus entier et n'entre pas dans la Qualité. Spans `wl.resumed` ignorés pour les appels et la latence (4.8) : 4.12 (aucun span n'est lu ici). Fraîcheur et exclusion des `inapplicable` du dénominateur : 4.13. Fidélité du wiki : la section existe, le juge par défaut suit `profil.judge_pool` (7.3), rien à ajouter ici.
- Risque : `generer_rapport` ré-ingère le Corpus (cache de parsing) pour résoudre les Ancrages de référence ; un Corpus modifié depuis l'Exécution donnerait d'autres `anchor_id` (l'Exécution reprise le refuse, pas `wl rapport`).

## Revue
- high, second avis 1 : corrigé. Le Corpus relu (et le Corpus après Scénario) est comparé à `inputs.corpus_fingerprint` / `scenario_fingerprint` du manifeste, avec le parser de la première Configuration comme le runner ; écart : recherche non mesurée pour la phase et alerte dans la section Recherche ; `inputs` absent : alerte « non comparé ». Second volet rejeté : `doc_id` est `sha256(octets)[:16]`, l'empreinte couvre donc le contenu. `test_corpus_modifie_depuis_l_execution_recherche_non_mesuree_et_signalee`.
- high, second avis 2 : corrigé. `lire_jsonl` décode ligne par ligne ; une troncature dans un caractère multioctet n'invalide que sa ligne. `test_lire_jsonl_tolere_une_troncature_au_milieu_d_un_caractere_multioctet`.
- medium, second avis 3 : corrigé. `_ecrire_rapport` attrape toute exception : le code 3 du plafond est conservé. `test_echec_du_rapport_ne_masque_pas_le_code_de_l_execution`.
- medium, second avis 4 : corrigé. `ResolveurCorpus` compte les Questions aux Ancrages non résolus (par parser et phase) et le Rapport l'affiche, ainsi qu'un Corpus indisponible. `test_ancrage_non_resolu_compte_et_signale`.
- low, second avis 5 : tranché, gardé. Run `completed` dont le Rapport échoue : code 1 (le Rapport fait partie de `wl run`) ; couvert par le test du point 3.
- low, second avis 6 : corrigé. L'assertion vérifie une valeur `non jugées` > 0 dans la table.
- low, second avis 7 : corrigé. `test_paire_continue_avec_questions_communes` : bootstrap apparié avec `n_common` > 0, `diff` comparé à la moyenne des écarts par Question.
- low, second avis 8 : corrigé. `JsonlSpanExporter.export` termine la ligne après une écriture ratée. `test_exporteur_de_traces_termine_la_ligne_apres_une_ecriture_partielle`.
- low, second avis 9 : rejeté. En contexte parfait, les Ancrages de référence sont fournis (`provided`) : rappel 1 par construction, rien à mesurer.
