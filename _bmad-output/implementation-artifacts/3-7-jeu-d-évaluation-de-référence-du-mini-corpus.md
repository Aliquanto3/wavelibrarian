---
story: "3.7"
title: Jeu d'évaluation de référence du Mini-corpus
status: done
---

# Story 3.7 : Jeu d'évaluation de référence du Mini-corpus

## Code Map

- `corpora/minicorpus/questions.yaml` : 47 Questions `validated`, gelées (graine 42, ratio 0,4), `target_count: 40`.
- `tests/conftest.py` : constante `CONFORMANCE_QUESTION_ID = "q-001"`.
- `tests/unit/evalset/test_minicorpus_questions.py` : tests de la story (importe la constante par `from conftest import ...`, le dossier `tests/` n'étant pas un paquet).
- Aucun code de `src/` n'est modifié.

## Design Notes

- Écriture : Questions et Réponses de référence rédigées à la main à partir des Documents du Mini-corpus, sans appel LLM ; le fichier a été produit par `evalset.io.save` (ordre de clés du contrat §4.5), puis gelé par `wl questions geler --dev-ratio 0.4 --graine 42`. Le Gel est déterministe et n'appelle aucun modèle : le profil `test` n'a donc pas été nécessaire. Le Filtre closed-book n'est pas demandé par les critères et n'a pas été lancé (`contaminated_by: []` partout) ; avec le Faux LLM il ne contaminerait de toute façon rien.
- Répartition : factual 21, multi_hop 7, temporal 7, comparison 5, global 3, unanswerable 2, knowledge_trap 2. Partie dev / test : factual 8/13, multi_hop 3/4, comparison 2/3, temporal 3/4, global 1/2, unanswerable 1/1, knowledge_trap 1/1 (19 dev, 28 test).
- Types particuliers : 3 suivis (historique d'un tour), 5 interlingues (Question française sur Documents anglais, et l'inverse ; un test vérifie que la langue de la Question diffère de celle de chaque Document ancré), 4 `scenario_target` (`op-1` et deux `op-2` à l'état `after`, `op-3` à l'état `before` sur la note supprimée), 2 `unanswerable` sans Ancrage (fait absent : capitaine du Petit Sarnoux ; tarif Keld – Brumeval), 2 `knowledge_trap` (quarantaine de onze jours au lieu de quarante ; courant qui s'inverse tous les quarante-deux jours et non plusieurs fois par jour).
- Réponses courtes : 18 Questions `factual` sur 21 en `short`, dont quatre citent une page de PDF (`convention-douane.pdf` pages 1 et 2, `tarifs-passeurs.pdf`, `lettre-torvane.pdf`).
- Ancrages : `doc` en `source_path` nu (`phare-de-keld.md`), `headings` incluant le titre de niveau 1 (le `heading_path` du Parser le contient). Les Questions de comparaison sur la charte pointent les deux versions coexistantes (`charte-conseil-v1.md`, `charte-conseil-v2.md`), cas temporel de 2.5.
- Question de conformité `q-001` (« Depuis quand Bram Oskelle est-il en poste ? », Ancrage « Le gardien » du phare de Keld) : 7 mots de la Question sur 8 figurent dans l'Ancrage (87,5 %), donc `grade_relevance` du Faux LLM la note 0,875 (> 0,5) ; les mots rares « Bram » et « Oskelle » la rendent retrouvable par BM25, le faux embedder et `select_nodes`.
- Contrôle : sans `--scenario`, les trois Questions `after` sont signalées « non vérifiables » sans échec ; avec, tout est résolu dans `corpus_after` et aucun signalement ne reste.
- Écart aux contrats : l'exemple de `contracts.md` §4.5 écrit `docs/…` dans `doc` ; on suit la décision de 2.5 (revue) : chemin relatif à `path`. Aucune contradiction d'AC.

## Tâches et critères

- [x] `wl questions controler` avec `--scenario` sort en 0, au moins 40 Questions `validated`, `origin` `claude-code-dev-agent`, `target_count: 40` : `test_controle_complet_avec_scenario`, `test_commande_controler_avec_scenario`, `test_effectif_origine_et_cible`.
- [x] Tous les Types sauf `visual` et `numeric_aggregation`, deux `follow_up` avec historique, deux `cross_lingual`, trois `scenario_target` valides : `test_types_suivis_interlingues_et_scenario`, `test_interlingue_langue_de_la_question_differente_du_document`.
- [x] Une `unanswerable` sur fait absent, une `knowledge_trap` : `test_unanswerable_sans_ancrage_et_piege_ancre`.
- [x] Au moins cinq `factual` en `short`, une citant une page de PDF : `test_questions_factuelles_courtes_et_page_de_pdf`.
- [x] Question de conformité (`CONFORMANCE_QUESTION_ID`, `factual`, un Ancrage, au moins 80 % de mots communs, `grade_relevance` > 0,5) : `test_question_de_conformite`.
- [x] `verify_frozen` : Gel graine 42, ratio 0,4, empreinte valide : `test_jeu_gele_graine_42_ratio_04`, `test_regel_identique_ne_change_aucune_partie`.
- [x] Non-régression : une Question modifiée dans une copie temporaire est refusée : `test_modifier_une_question_dans_une_copie_est_refuse`.

## Auto Run Result

Livré, `status: review`. 11 tests ciblés verts ; suite complète, pyright et contrôle rapide verts (voir rapport). Reports : (1) `tests/conformance/` (story 4.14) importera `CONFORMANCE_QUESTION_ID` par `from conftest import …` ; (2) le Filtre closed-book réel (modèles réels) n'a pas été lancé sur le Jeu, faute de modèle autorisé pendant le run ; à faire avant tout test avec de vrais modèles ; (3) toute modification du fichier après Gel casse l'empreinte : corriger une Question impose un re-Gel avec `--forcer` si une partie change.

## Revue

Revue Opus du 2026-10-18, après rebase sur `main` (caef354). Toutes les Questions sont reposées en phase `after_update` (story 4.7) : une Question sans `scenario_target` doit donc rester juste dans `corpus_after`.

- medium, second avis 1, corrigé : `q-008` (hauteur de la grande marée du dixième jour) devenait fausse après `op-2` ; remplacée par une Question sur un Document non modifié (hauteur du phare de Keld, « Trente-quatre mètres »). `q-022` gardée : le feu à éclats est allumé dans les deux versions du bulletin et la Réponse vient du phare ; le tonnage (40 ou 30 selon la version) est retiré de la Réponse de référence.
- medium, revue, corrigé : `q-018` (« navire du directeur de la Compagnie ») devenait fausse après `op-1`, la chronique de 1415 nommant Ilsa Marenne directrice ; reformulée sur « la personne qui a pris la direction en l'an 1409 » (Tamsin Orrelle, Cormoran Gris), vraie avant comme après.
- medium, revue, corrigé : `q-039` ancrait le bulletin (`Consignes`, modifié par `op-2`) et sa Réponse (40 tonneaux) contredisait le bulletin de 1415 ; Ancrage du bulletin retiré, Réponse fondée sur l'atlas et les tarifs des passeurs.
- medium, second avis 2, corrigé : `q-021` se résolvait avec le seul rapport du chantier ; réécrite pour exiger la lettre (Tamsin Orrelle) et le rapport (quatre mille deniers).
- low, second avis 3, rejeté : la définition du cadrage (« documents périmés ou versions contradictoires ») est tenue par `q-029`, `q-030`, `q-036`, `q-046` ; `q-031` à `q-033` sont des temporelles faibles (dates, édition fautive de l'almanach) ; les reclasser changerait la répartition stratifiée sans gain.
- low, second avis 4, rejeté : `q-001` reprend son Ancrage à dessein, c'est la Question de conformité (87,5 % de mots communs, exigés par l'AC et par la story 4.14).
- low, second avis 5, corrigé : ajout de `test_reponses_factuelles_courtes_presentes_dans_leurs_ancrages` et de `test_questions_hors_scenario_sans_document_modifie_ou_supprime` (liste `stables` explicite pour `q-022`). Le test de répartition reste un contrôle de cohérence avec `nb_dev`, pas un oracle indépendant.
- low, second avis 6, consigné : `from conftest import` repose sur l'import de `tests/conftest.py` par pytest en mode `prepend` (dossier `tests/` sans `__init__.py`) ; il casserait avec `--import-mode=importlib`. La story 4.14 devra en tenir compte.
- Re-Gel : `wl questions geler --dev-ratio 0.4 --graine 42` sans `--forcer` (aucune partie ne change), nouvelle empreinte `76fa20b7…`. Un ajout `op-1` qui change un fait existant n'est pas détectable mécaniquement : à relire à chaque nouveau Scénario.
