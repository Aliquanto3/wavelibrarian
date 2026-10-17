---
story: "2.6"
title: Application d'un Scénario de mise à jour à un Corpus
status: review
---

# Story 2.6 : Application d'un Scénario de mise à jour à un Corpus

## Code Map

- `src/wavelibrarian/corpus/scenario.py` : schéma (`Scenario`, `Operation`), `charger(chemin, parsed)`, `appliquer(parsed, charge)` -> `(CorpusChange, corpus_after)`, `appliquer_fichier`, `corpus_apres(parsed, chemin)` (report de 3.1).
- `src/wavelibrarian/corpus/ingest.py` : `empreinte(documents)` extrait de `ingest` (même calcul du `fingerprint`, partagé avec le Scénario).
- `src/wavelibrarian/cli.py` : `_corpus_apres` appelle directement `corpus.scenario.corpus_apres` (plus d'import différé ni de repli).
- `tests/unit/corpus/test_scenario.py` : tests de la story.

## Design Notes

- `charger` valide contre le Corpus en simulant les opérations dans l'ordre : `add` sur un `target` présent, `modify` ou `delete` sur un `target` absent (au regard de l'état courant, donc après un `delete` précédent), `source` introuvable ou d'un autre format que le `target`, identifiants en double, `corpus_id` différent : `ConfigError` au chemin `operations[i]` (ou `corpus_id`).
- `source` et `target` sont lus tels quels dans le contrat ; la `source` est parsée en mémoire par le Parser `auto` du format, sans cache de parsing ni écriture : `docs/` et `scenario/` restent intacts (test d'empreintes).
- Un Document modifié garde `source_path`, `lang` et `meta` (ancrages réancrés par le Parser sur `target`) ; un Document ajouté prend la langue majoritaire du Corpus (le `ParsedCorpus` ne porte pas la langue déclarée) et des métadonnées vides.
- `CorpusChange` est le changement net entre `parsed` et `corpus_after`, trié par `source_path` (un ajout suivi de sa suppression ne laisse rien). Un contenu qui reproduit celui d'un autre Document est refusé (`doc_id` identiques, ancrages ambigus).
- `corpus_after` est reconstruit, jamais muté : le `ParsedCorpus` d'origine est inchangé. Déterminisme : aucune horloge, aucun aléa.

## Tâches et critères

- [x] Opérations lues dans l'ordre, `source` résolu par rapport au Scénario, `target` = `source_path` : `test_chargement_ordre_et_cibles`.
- [x] `modify` ou `delete` sur `target` absent, `source` introuvable : `ConfigError` à `operations[i]` : `test_erreurs_au_chemin_de_l_operation`.
- [x] `CorpusChange` (`added`, `removed` en `doc_id`, `modified` en couples) et `corpus_after` : `test_application_au_minicorpus`.
- [x] Document supprimé absent, modifié au même `source_path` avec nouveau `doc_id`, ajouté présent : `test_application_au_minicorpus`.
- [x] `fingerprint` différent, original inchangé : `test_application_au_minicorpus`.
- [x] Deux applications identiques (`CorpusChange`, `fingerprint`) : `test_deterministe_et_docs_intacts`.
- [x] Aucun fichier de `docs/` modifié : `test_deterministe_et_docs_intacts`.
- [x] Report 2.6 (`corpus_apres(parsed, chemin)`, `wl questions controler --scenario` de bout en bout sur le Mini-corpus) : `test_commande_controler_scenario_de_bout_en_bout`.
- [x] Garde-fous ajoutés : `test_corpus_id_et_identifiants`, `test_changement_net_ajout_puis_suppression`, `test_contenu_identique_a_un_document_existant_refuse`.

## Auto Run Result

Voir le rapport de l'agent (suite complète, pyright et contrôle rapide).
