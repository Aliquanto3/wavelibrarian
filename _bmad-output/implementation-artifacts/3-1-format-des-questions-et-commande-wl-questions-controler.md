---
story: "3.1"
title: Format des Questions et commande `wl questions controler`
status: review
---

# Story 3.1 : Format des Questions et commande `wl questions controler`

## Code Map

- `src/wavelibrarian/evalset/io.py` : `QuestionsFile`, `Freeze`, `load(chemin)`, `save(chemin, doc)`.
- `src/wavelibrarian/evalset/check.py` : `controler(doc, corpus, corpus_apres=None) -> Controle` (comptes, écart, `Signalement` bloquants ou non).
- `src/wavelibrarian/scoring/answer.py` : `is_short_form` (FR-36), à étendre par la story 3.4 (`exact_match`).
- `src/wavelibrarian/cli.py` : sous-application `wl questions`, commande `controler` (ajout limité ; `pyproject.toml` inchangé).
- Tests : `tests/unit/evalset/test_questions.py`, `tests/unit/scoring/test_answer.py`.

## Design Notes

- `load` valide par pydantic strict (`valider`) : `ConfigError` au chemin `questions[12].type` ; un `id` en double lève `questions[j].id` (j = second enregistrement), message qui nomme le premier.
- `save` : écriture atomique PyYAML, `sort_keys=False`, ordre des Questions conservé, clés dans l'ordre du contrat §4.5 ; `page: null` omis des Ancrages. Les commentaires YAML et un ordre de clés propre à l'auteur ne sont pas conservés (voir Reports).
- Bloquant (code 2) seulement pour les Questions `validated` ou `corrected` : Ancrage introuvable, `unanswerable` avec Ancrages, autre Type sans Ancrage, `scenario_target` mal formé. Pour `generated` et `rejected` : signalé sans échec. Incohérence `answer_form: short` (FR-36) : toujours un simple signalement (la Réponse de référence vide n'est pas jugée).
- `scenario_target.state == "after"` : résolu dans `corpus_apres` ; sans lui, « non vérifiable » signalé, sans échec. Les autres Questions (état `before` ou aucune cible) : Corpus de base.
- Écart à `target_count` = `target_count` moins le nombre de Questions `validated` et `corrected` (seules utilisables).
- `--scenario` : la story 2.6 n'est pas livrée ; `cli.py` importe `wavelibrarian.corpus.scenario.corpus_apres(parsed, chemin)` à l'exécution, et sort en code 2 avec un message clair tant que le module manque (voir Reports).
- Un `corpus_id` du fichier différent de celui du Corpus donne le code 2.
- Contradiction relevée : l'AC dit « signalée » pour `unanswerable` avec Ancrages sans préciser le code de sortie ; lecture retenue : bloquant seulement si la Question est utilisable, comme pour l'Ancrage introuvable (epic 3 : « aucun Ancrage faux ne passe »).

## Tâches et critères

- [x] Chargement : `corpus_id`, `target_count`, `freeze`, Questions dans l'ordre ; écriture puis relecture identiques : `test_chargement_ordre_et_aller_retour`, `test_freeze_aller_retour`.
- [x] `type` inconnu : `questions[12].type` ; `id` en double : `questions[j].id` : `test_type_inconnu_et_id_en_double`, `test_champ_inconnu_et_racine_invalide`.
- [x] `unanswerable` avec Ancrages, autre Type sans Ancrage : signalés avec l'`id` : `test_structure_unanswerable_et_sans_ancrage`.
- [x] Page 9 d'un PDF de 3 pages : comptes par statut et Type, écart, Question et Ancrage listés, code 2 : `test_ancrage_introuvable_page_9`, `test_commande_controler`.
- [x] `generated` ou `rejected` à l'Ancrage introuvable : signalé sans échec : `test_generated_et_rejected_ne_font_pas_echouer`, `test_commande_controler`.
- [x] `--scenario` : Ancrages `after` résolus dans `corpus_after`, autres dans la base ; sans scénario, non vérifiable sans échec : `test_scenario_target`, `test_scenario_target_mal_forme`, `test_commande_erreurs` (module 2.6 absent ou fichier absent : code 2).
- [x] `answer_form: short` incohérent (plus de 5 mots, ni nombre ni date) : `test_reponse_courte_incoherente`, `test_forme_courte`, `test_forme_longue`.

## Auto Run Result

- Statut : review. 23 tests ciblés verts ; suite complète 380 verts ; pyright 0 erreur ; contrôle rapide sans erreur.
- Reports : (1) story 2.6 doit fournir `wavelibrarian.corpus.scenario.corpus_apres(parsed, scenario_path) -> ParsedCorpus`, ou adapter `_corpus_apres` dans `cli.py` ; la branche réelle de `--scenario` n'est testée qu'avec des `ParsedCorpus` construits à la main ; (2) contrôle de `closed_book_models` et `question_gen_model` au Catalogue (RUN-STATUS) : stories 3.3 et 3.5, commandes `generer` et `closed-book` ; (3) conservation des commentaires YAML et de l'ordre de clés d'auteur à `save` (PyYAML) : à traiter si `geler` (3.6) réécrit un fichier annoté ; (4) `exact_match` et le reste de `scoring/answer.py` : story 3.4 ; (5) un PDF dans le Corpus exige le Parser `pdf_text` (story 2.3).
