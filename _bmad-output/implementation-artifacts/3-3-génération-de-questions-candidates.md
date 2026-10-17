---
story: "3.3"
title: Génération de Questions candidates
status: done
---

# Story 3.3 : Génération de Questions candidates

## Code Map

- `src/wavelibrarian/evalset/generate.py` : `parse_repartition`, `echantillon_ancrages(ctx, corpus, n)`, `generer(ctx, corpus, existant, repartition, modele) -> Generation` (fichier complété, Questions ajoutées, rejets, surplus, manques, coût, indicateur de cache). N'écrit rien : l'appelant sauvegarde.
- `src/wavelibrarian/cli.py` : `wl questions generer <corpus.yaml> --repartition … [--modele] [--questions] [--cible] [--profil] [--graine]` ; `_contexte_hors_execution` (Contexte hors Exécution, remplaçable en test).
- `src/wavelibrarian/runner/context.py` : `Context.from_profile` accepte `budget` (plafonds d'une commande hors Exécution).
- Tests : `tests/unit/evalset/test_generate.py` (Faux LLM, profil `test`).

## Design Notes

- Un seul appel `question_gen` par génération (`inputs` : `anchors` = `[{anchor_id, text}]`, `types` = répartition). L'échantillon compte autant d'Ancrages que de Questions demandées, tirés par `ctx.rng("questions", "ancrages", corpus_id)` parmi les Ancrages au texte non vide triés : même graine, même échantillon ; même requête, donc Cache de réponses.
- Le Poste `evalset` est fixé par `generer` lui-même (`ctx.scope`), la passerelle du Contexte refusant sinon l'appel. Traces dans `WL_HOME/hors-execution/<run_id>/`.
- Tri de la sortie : Type inconnu, texte vide, Ancrage hors Corpus (ou qui ne se résout pas sur le même `anchor_id`), aucun Ancrage hors `unanswerable` : « rejetées à la génération ». Une `unanswerable` perd les Ancrages cités par le modèle (elle n'en porte pas). Au-delà de la répartition d'un Type : « écartées en surplus » ; Types non atteints : « manquantes ». Le Faux LLM ignore `types` (une `factual` par Ancrage) : seules les `factual` demandées sont retenues, les autres Types sont signalés manquants.
- Ancrages écrits `{doc, page}` ou `{doc, headings}` (AD-5). `id` : `q-NNN`, après le plus grand numéro existant et jamais un `id` déjà présent (rejetées comprises). `lang` : langue du Document du premier Ancrage.
- Plafond atteint : `BudgetExceeded` avant tout appel, code 3, fichier non réécrit (aucune écriture partielle). Un jeu gelé est refusé (code 2), comme un `corpus_id` différent. `question_gen_model` (ou `--modele`) est contrôlé au Catalogue avant tout appel (code 2) : report RUN-STATUS traité pour `generer`.
- Nouveau fichier : `questions.yaml` à côté de `corpus.yaml`, `target_count` = `--cible` ou le total demandé. Plafond par défaut de la commande : celui de `Budget()` (5 $ Anthropic par Exécution) ; aucun plafond par option, le contrat §8 n'en prévoit pas.
- `save` réécrit le fichier dans l'ordre de clés du contrat : les Questions existantes sont conservées sans modification de contenu (commentaires YAML non conservés, report 3.1).

## Tâches et critères

- [x] `wl questions generer` ajoute des Questions `generated`, `origin: {kind: model, name}`, `id` neuf, `split: null` ; existantes conservées : `test_questions_ajoutees_generated_et_existantes_conservees`, `test_nouveau_fichier_cree_a_cote_du_corpus`, `test_faux_llm_par_defaut_respecte_la_repartition`, `test_modele_explicite_trace_dans_origin`.
- [x] `anchor_id` absent écarté et compté ; Ancrages écrits `{doc, page}` / `{doc, headings}` : `test_anchor_id_absent_du_corpus_ecarte`, `test_ancrage_page_ecrit_en_doc_page`.
- [x] Rôle `question_gen`, `inputs` `anchors` et `types`, span `wl.post=evalset`, seconde génération servie par le Cache à coût nul : `test_role_inputs_et_poste_evalset_puis_cache`, `test_generer_fixe_lui_meme_le_poste`.
- [x] Plafond insuffisant : code 3, rien d'écrit, Questions validées intactes : `test_plafond_insuffisant_code_3_sans_ecriture`.
- [x] Même graine, même échantillon d'Ancrages : `test_meme_graine_meme_echantillon`.
- [x] Report RUN-STATUS : `question_gen_model` contrôlé au Catalogue ; Poste ouvert avant tout appel hors Exécution : `test_modele_inconnu_du_catalogue_code_2_sans_appel`, `test_generer_fixe_lui_meme_le_poste`.
- [x] Refus : répartition invalide, jeu gelé, Corpus différent : `test_repartition_invalide`, `test_repartition_invalide_par_la_commande`, `test_jeu_gele_et_corpus_different_refuses`.

## Auto Run Result

- Statut : review. 21 tests ciblés verts ; suite complète 446 verts ; pyright 0 erreur ; ruff propre ; contrôle rapide sans erreur.
- Reports : (1) `closed_book_models` à contrôler au Catalogue dans `closed-book` (story 3.5) ; (2) pas d'option de plafond sur la commande (contrat §8) : le plafond est celui par défaut de `Budget()`, à relier à une configuration si Anaël le demande ; (3) la qualité du tri de types (`multi_hop` exige-t-il deux Ancrages ?) n'est pas imposée, le contrat ne le dit pas ; (4) l'échantillon d'Ancrages est uniforme, sans équilibre par Document.

## Revue

Rebasée sur `main` (a5cfc2e, Mini-corpus de la 2.5). Commande lancée deux fois sur `corpora/minicorpus` en profil `test` : 3 `factual` ajoutées, `{doc, headings}` corrects, second appel servi par le Cache à coût nul ; les 88 Ancrages du Mini-corpus se résolvent tous par `_ref`.

- medium, second avis 1 : corrigé. La seconde génération ajoutait des doublons exacts (constaté sur le Mini-corpus). Une Question au même texte (casse et espaces normalisés) et aux mêmes Ancrages qu'une Question du fichier ou de la même sortie est rejetée avec le motif « doublon de q-NNN » (`test_doublons_ecartes_dans_la_sortie_et_face_au_fichier`).
- low, second avis 2 : corrigé. Un `anchor_id` du Corpus absent de l'échantillon présenté est rejeté (« Ancrage hors de l'échantillon présenté ») ; un id hors Corpus garde le motif de l'AC 2 (`test_ancrage_reel_hors_echantillon_ecarte`).
- low, second avis 3 : reporté. Un `multi_hop` à un seul Ancrage est accepté, car le contrat n'impose pas de minimum (déjà en report n° 3).
- low, second avis 4 : corrigé. Le coût s'affiche en virgule fixe (`f"{cost:f}"`), et non plus en `1E-7`.
- low, second avis 5 : corrigé. `--cible 0` (ou une valeur négative) sort avec le code 2 (`test_cible_nulle_refusee`). `--cible` reste sans effet sur un fichier existant, dont le `target_count` est conservé.
- low, second avis 6 : rejeté. Le contrat (« stable, jamais réutilisé ») ne prévoit aucun registre des id retirés. L'id suit le plus grand numéro présent : seul le retrait manuel du dernier id permet de le réémettre. Pour l'empêcher, il faudrait un registre au format du fichier, à décider en story 3.x si le besoin se confirme.
- low, second avis 8 : consigné. Avec le Faux LLM, l'AC 1 ne produit que des `factual` (multi_hop et unanswerable sont signalés manquants) : le cas complet est prouvé par une sortie scénarisée, ce qui est conforme au contrat du faux.
- low, second avis 10 : consigné. Le Plafond ne borne que les providers payants (contrat §8). Une génération sur un modèle local n'a de borne que `max_tokens`.
- Report : vérifier sur `claude-haiku-5-5` réel (`question_gen_model`) la qualité de la répartition par Type et le taux de rejets, ce qui exige une clé API et un appel payant.
