---
story: "4.9"
title: Métriques de recherche, Critères automatiques et Panel de juges
status: review
---

# Story 4.9 : Métriques de recherche, Critères automatiques et Panel de juges

## Code Map

- `src/wavelibrarian/scoring/retrieval.py` (nouveau) : `retrieval_metrics(retrieved, reference_anchor_ids, method, k=5)` rend `RetrievalScores` (`recall`, `mrr`, `ndcg`, `method`) ; `est_pertinent` (recouvrement des `anchor_ids`). Fonctions pures.
- `src/wavelibrarian/scoring/answer.py` : `citation_correctness`, `abstention_correctness`, `JUGE_AUTO` (`exact_match` existait depuis la 3.4).
- `src/wavelibrarian/scoring/panel.py` (nouveau) : `verdicts_automatiques`, `criteres_juges`, `juger_reponse` (un appel par Juge et par passe, clés absentes seulement), `ecrire_panel`, `majorite` (égalité = `no` + `tie`), `PanelVerdict` (ligne de `panel.jsonl`), `construire_juges`. Écrit par des `Sink` fournis par le runner.
- `src/wavelibrarian/runner/execute.py` : `panels_de` (Panel de chaque Configuration par `form_panel`, `judges.excluded_from` appliqué, `ConfigError` avant tout appel) ; `_Runner.juger` (après toutes les Réponses, `ctx.scope(post="judging", question_id=…)`, `JudgeInput` avec les textes des Ancrages de référence et les `context_texts` du Generator) ; `RunOutcome.unjudged`.
- `src/wavelibrarian/runner/rundir.py` : `read_verdicts`, `read_panel` (la dernière ligne d'une clé fait foi).
- Tests : `tests/unit/scoring/test_retrieval.py`, `test_panel.py`, `test_answer.py` (fin du fichier), `tests/unit/runner/test_story_4_9.py`. Les tests 4.4, 4.5 et 4.8 filtrent désormais le poste `judging` (le jugement ajoute des appels et des spans).

## Design Notes

- Métriques : rappel@k = part des Ancrages de référence recouverts par les k premiers Passages ; MRR sur la liste entière ; nDCG@k binaire, idéal = `min(k, nb d'Ancrages de référence)` Passages pertinents en tête, plafonné à 1. Un Passage unique qui recouvre deux Ancrages ne peut donc pas atteindre 1 (0,613) : lecture fidèle de « pertinent si `anchor_ids` recoupe les Ancrages ». `none` et une Question sans Ancrage (`unanswerable`) ne produisent aucune métrique ; la méthode est toujours reportée. Le runner n'écrit pas encore ces métriques : le Rapport (4.11) les calcule depuis `answers.jsonl` et le Jeu, avec `retrieval_metrics`.
- Jugement après toutes les Réponses, jamais pendant : seules les Réponses `ok` sont notées (`error`, `inapplicable`, `budget_exceeded` : ni Critère automatique ni Juge). Si les Réponses s'arrêtent au plafond, le jugement est sauté ; la reprise (`--reprendre`) pose les Questions restantes puis juge. Un `BudgetExceeded` pendant le jugement donne le manifeste `budget_exceeded` (code 3) ; les verdicts écrits restent.
- Critères automatiques (`judge_model: "auto"`, `pass_id: 0`) : `citation_correctness`, `abstention_correctness`, et `correctness` par `exact_match` pour `answer_form: short`. Ils figurent aussi dans `panel.jsonl` avec `judges: []`, pour que le Rapport lise un seul fichier par (answer_id, criterion).
- Un Juge note tous ses Critères jugés en un seul appel par passe (`judges.passes`). La majorité compte toutes les voix (Juges x passes) ; égalité = `verdict: false`, `tie: true`. Une ligne de `panel.jsonl` n'est écrite que si chaque Juge du Panel a voté à chaque passe ; un Juge en échec (hors `BudgetExceeded`) laisse la clé absente, journalisée, comptée dans `RunOutcome.unjudged`, redemandée à la reprise.
- Reprise : `verdicts.jsonl` et `panel.jsonl` sont relus ; seuls les (answer_id, judge_model, criterion, pass_id) absents sont demandés, et un Juge n'est pas appelé si toutes ses clés sont là. Les appels refaits sortent du Cache de réponses.
- Corpus des Ancrages : celui de la phase de la Réponse (Corpus après Scénario pour `after_update`). Un Ancrage qui n'existe pas dans ce Corpus (créé plus tard par le Scénario, ou supprimé) n'entre ni dans `reference_texts` ni dans les Ancrages de référence de `citation_correctness`.
- Famille : le Panel exclut déjà la Famille du Generator (`form_panel`). Le runner passe toujours le modèle de chaque Juge, donc le défaut `judge_pool[0]` de `LLMJudge` n'est jamais utilisé en Exécution.

## Tâches et critères

- [x] AC 1 : rappel@5, MRR (0,5) et nDCG@5 à la main ; pertinence par recouvrement quel que soit le Découpage ; `provided`, `cited` reportées, `none` sans métrique. Tests : `test_retrieval.py::test_valeurs_calculees_a_la_main`, `test_pertinence_par_recouvrement_quel_que_soit_le_decoupage`, `test_methodes_reportees_et_none_sans_metrique`.
- [x] AC 2 : `citation_correctness` (dont `unanswerable`), `abstention_correctness`, `correctness` exact_match en réponse courte avec `judge_model: "auto"`. Tests : `test_answer.py::test_citation_correctness`, `test_abstention_correctness` ; `test_panel.py::test_reponse_courte_correctness_exact_match_et_juges_sur_les_deux_autres`, `test_critere_automatique_unanswerable` ; `test_story_4_9.py::test_panel_un_appel_par_reponse_et_par_juge_verdicts_et_panel`.
- [x] AC 3 : Panel `[fake-llm-b, fake-llm-c]` pour `fake-llm-a`, un appel par Réponse et par Juge au poste `judging`, `JudgeInput` avec `context_texts`, un Verdict par clé, `panel.jsonl` majoritaire avec Juges admissibles, égalité = `no` + `tie`, Juges exclus non appelés. Tests : `test_story_4_9.py::test_panel_un_appel_par_reponse_et_par_juge_verdicts_et_panel`, `test_juge_recoit_les_textes_des_ancrages_et_le_contexte_du_generator`, `test_juges_exclus_par_la_calibration_ne_sont_pas_appeles` ; `test_panel.py::test_majorite_et_egalite`, `test_panel_de_deux_juges_en_desaccord_egalite_donne_non_et_tie`, `test_trois_juges_majorite_un_appel_chacun_tous_les_criteres`, `test_passes_multiples_une_voix_par_passe`.
- [x] AC 4 : aucun Juge pour `error`, `inapplicable`, `budget_exceeded`. Tests : `test_story_4_9.py::test_erreur_non_jugee`, `test_inapplicable_non_jugee`, `test_budget_exceeded_non_juge`.
- [x] AC 5 : reprise après arrêt pendant le jugement, seules les clés absentes. Tests : `test_story_4_9.py::test_reprise_apres_arret_pendant_le_jugement_ne_demande_que_les_cles_absentes` ; `test_panel.py::test_reprise_ne_demande_que_les_cles_absentes_et_n_ecrit_pas_deux_fois`.

## Auto Run Result

- Statut : review. Vérifications et décompte des tests : voir le rapport de l'orchestrateur.
- Reports traités : `JudgeInput` avec les textes des Ancrages et les `context_texts`, `ctx.scope(post="judging")` (3.4) ; reprise de `verdicts.jsonl` et `panel.jsonl` (4.8) ; Juges exclus de la calibration non appelés (1.6).
- Reports non traités : exclusion des Questions contaminées (FR-12) : elle relève du Rapport (contracts §7, « rapportées à part » exige qu'elles soient jugées), donc story 4.11 ; défaut `judge_pool[0]` de `LLMJudge` filtré par Famille : sans effet en Exécution (le runner fixe le modèle), à reprendre si une commande appelle un Juge sans Panel ; contrôle de tout le réservoir de Juges au préflight (1.12) ; écriture de `retrieval.csv` et des métriques par Question : 4.11.
- Pour 4.11 : lire `panel.jsonl` (un verdict par (answer_id, criterion), `tie` à compter) et `verdicts.jsonl` avec `read_panel` et `read_verdicts` ; tolérer une dernière ligne tronquée (comme `answers.jsonl`) ; compter le poste `judging` à part du coût d'une Configuration.
- Risque : l'Exécution complète ajoute 2 appels de Juge par Réponse `ok` ; en réel, le plafond doit les couvrir (le jugement passe après les Réponses, donc un plafond serré donne `budget_exceeded` avec des Réponses non jugées, reprise possible).
