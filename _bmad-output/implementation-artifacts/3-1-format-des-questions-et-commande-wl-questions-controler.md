---
story: "3.1"
title: Format des Questions et commande `wl questions controler`
status: done
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

## Revue

Revue Opus en une passe, après rebase sur `main` (story 2.3). Vérifié de bout en bout avec `wl questions controler` sur un Corpus réel (Markdown à titres en double et PDF de 3 pages généré par fpdf2).

- medium, second avis 1 : corrigé. Un Ancrage `{doc, page, headings}` passait sur sa seule page (`resolve` ignore `headings`). Le contrat ne montre que des formes exclusives : `check.py` signale « Ancrage ambigu », bloquant pour une Question utilisable. Test `test_page_et_headings_exclusifs_et_unanswerable_apres`.
- medium, second avis 2 : corrigé. Dans `ParsedCorpus.resolve`, « Note 2 » sans titre de ce nom résolvait le doublon `note-2` de « Note » : un faux Ancrage passait. Le repli par slug n'est plus essayé que si chaque titre est déjà un slug. La correspondance exacte reste prioritaire et `note-2` résout encore le doublon. Tests `test_commande_pdf_reel_et_titres_en_double` et `test_resolve_absent`, et `tests/unit/corpus` reste vert. Un titre écrit avec une autre casse (« Histoire Ancienne » pour « Histoire ancienne ») est désormais introuvable, donc signalé.
- medium, second avis 3 : corrigé. Les messages pydantic sortaient en anglais, alors que le contrat (en-tête) les veut en français. `config_error` traduit maintenant les types courants : missing, extra_forbidden, types scalaires, literal, bornes et longueurs. Le correctif est transverse (Expériences, Corpus, Catalogue). Test `test_message_d_erreur_en_francais`.
- medium, second avis 4 : rejeté. Lue avec sa Design Note, l'AC demande que `save` puis `load` redonnent le même contenu, l'ordre des Questions et des clés étant stable, celui du contrat §4.5. Elle n'exige pas de conserver un ordre de clés propre à l'auteur. Un fichier dans l'ordre du contrat ressort identique (testé). Le report (3) reste valable pour la 3.6.
- low, second avis 5 : reporté. Une seule erreur pydantic remonte : `load` lève une `ConfigError` unique, comme le veut l'AC. L'agrégation pourra venir avec `geler` si le besoin apparaît.
- low, second avis 6 : corrigé. Le message de `--scenario` ne cite plus « story 2.6 ».
- low, second avis 7 : corrigé. Une `unanswerable` avec `scenario_target: after` et sans Ancrage n'est plus signalée « non vérifiable ».
- low, second avis 8 : consigné. La contradiction de l'AC (« signalée » pour `unanswerable` avec Ancrages ou autre Type sans Ancrage, sans code de sortie) a été tranchée ainsi : bloquant si la Question est `validated` ou `corrected`. **À arbitrer par Anaël.**
- low, second avis 9 : reporté. Les erreurs d'usage de click et typer (« Missing option », « No such command ») restent en anglais. Le correctif est transverse à toute la CLI : traduction des messages de click, ou gestionnaire d'erreurs d'usage.
- low, second avis 10 : rejeté. Une date en toutes lettres (« 12 mars 1412 ») tient en 5 mots et passe déjà en `short`. Le cas restant (date de plus de 5 mots) est marginal et ne produit qu'un simple signalement.
- low, second avis 11 : corrigé. Tests ajoutés avec chaque correctif, dont un test CLI sur un vrai PDF : la page 9 donne le code 2, la page 3 passe.
- low, revue : reporté. `--scenario` n'a pas de chemin réel tant que la story 2.6 n'est pas livrée. À vérifier en 2.6 : `wavelibrarian.corpus.scenario.corpus_apres(parsed, chemin)` existe, puis `wl questions controler ... --scenario` résout une Question `state: after` dont le Document est ajouté par `op-1`.
