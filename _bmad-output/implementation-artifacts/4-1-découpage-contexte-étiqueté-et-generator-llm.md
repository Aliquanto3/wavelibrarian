---
story: "4.1"
title: Découpage, contexte étiqueté et Generator LLM
status: done
---

# Story 4.1 : Découpage, contexte étiqueté et Generator LLM

## Code Map

- `src/wavelibrarian/components/chunkers/fixed_tokens.py` : `FixedTokenChunker` (`("chunker", "fixed_tokens")`, `size: 300`, `overlap: 50`).
- `src/wavelibrarian/components/context/labeled.py` : `LabeledContextBuilder` (`("context_builder", "labeled")`).
- `src/wavelibrarian/components/context/arch_answer.py` (réexporté par `components/context/__init__.py`) : `build_arch_answer`.
- `src/wavelibrarian/components/generators/llm.py` : `LLMGenerator` (`("generator", "llm")`, `model` en `answer_producer`, `max_tokens`).
- Tests : `tests/unit/components/test_story_4_1.py` (Faux LLM, profil `test`).

## Design Notes

- Le tokenizer du contexte n'expose que `count` : le chunker découpe en mots (jamais coupés), pesés chacun par `ctx.tokenizer.count`, et remplit une fenêtre jusqu'à `size`. Le recouvrement recule d'au moins `overlap` tokens, toujours d'un mot de moins que la fenêtre (progression garantie). `overlap >= size` est refusé (`ConfigError`). Un Passage porte, dans l'ordre, les Ancrages de tous les Blocks dont il contient un mot.
- `key()` = `fixed_tokens:size=<n>:overlap=<m>` ; `passage_id = sha16(doc_id, key(), ordinal)`.
- `labeled` : bloc `[Sn] (<anchor_ids séparés par ", ">) <texte>`, blocs joints par une ligne vide.
- Generator : `inputs = {question, blocks: {étiquette: texte sans préfixe}}` (forme lue par le Faux LLM), `history` transmis en messages précédant la question, contexte vide = « (aucun passage) » et l'abstention vient du modèle. Étiquettes `S1`, `[S1]` acceptées ; une étiquette absente de `labels` est retirée et comptée une fois (distincte) dans `invalid_citations`. Modèle par défaut : `generator_models[0]`.
- `build_arch_answer(context, result, retrieved, method, *, tokenizer, max_context_tokens=8000)` : le comptage de tokens exige un tokenizer, ajouté en paramètre nommé (écart à la signature à quatre arguments du critère). Au-delà du seuil, un bloc est gardé si l'un de ses Ancrages est cité (deux blocs partageant un Ancrage cité restent tous deux : sur-inclusion assumée, le port `GenerationResult` ne porte pas les étiquettes). `context_anchor_ids` = union dédoublonnée de `Context.labels`.

## Tâches et critères

- [x] Chunker : `level 0`, `doc_id`, `anchor_ids` non vides limités au Document, `passage_id` : `test_chunker_enregistre_et_passages_du_minicorpus`.
- [x] Passage à cheval sur deux sections = deux Ancrages ; `key()` change avec `size`/`overlap` : `test_passage_a_cheval_sur_deux_sections_porte_les_deux_ancrages`, `test_key_change_avec_size_et_overlap`, `test_chunker_taille_et_recouvrement`, `test_chunker_refuse_un_recouvrement_trop_grand`.
- [x] ContextBuilder `labeled` : `text`, `blocks`, `labels`, `passage_ids` : `test_labeled_construit_les_blocs_et_les_tables`.
- [x] Generator : citations `S1`/`S9` -> Ancrages de `S1`, `invalid_citations == 1`, `inputs` `question` et `blocks` : `test_citation_invalide_retiree_et_comptee`.
- [x] Contexte vide : abstention distincte du texte : `test_contexte_vide_le_faux_llm_s_abstient`.
- [x] Historique transmis en messages : `test_historique_transmis_en_messages`.
- [x] `build_arch_answer` sous et au-delà de 8 000 tokens, `context_anchor_ids` : `test_arch_answer_reprend_les_blocs_sous_le_seuil`, `test_arch_answer_tronque_aux_blocs_cites_au_dela_du_seuil`.
- [x] Enregistrement et modèle par défaut : `test_generator_enregistre_et_modele_par_defaut`, `test_generation_nominale_cite_s1`.

## Auto Run Result

- Statut : review. 550 tests verts (suite complète), pyright 0 erreur, ruff propre, contrôle rapide sans erreur.
- Reports de l'epic 4 traités : aucun ne relève de cette story.
- Reports : le seuil de 8 000 tokens est compté par le tokenizer fourni par l'Architecture appelante (celui du contexte) ; `retrieval_method` est passé tel quel.
- Report 4.2 : `build_arch_answer` exige `tokenizer=` (argument nommé, écart à la signature à quatre arguments du critère). Chaque Baseline de la 4.2 doit passer le tokenizer du contexte (`ctx.tokenizer`, ou celui du modèle du Generator quand `tokenizer_for` existera) ; vérifier par un test qu'un Contexte de plus de 8 000 tokens est bien tronqué depuis une Architecture.

## Revue

- low, second avis 1 : `_ETIQUETTE` acceptait `[S1` et `S1]` — corrigé : seules `[S1]` et `S1` (après `strip`) sont reconnues, `s1` et `S01` restent invalides et comptées.
- low, second avis 2 : aucun test de la forme `[S1]` — corrigé : `test_formes_d_etiquette`.
- low, second avis 3 : contexte vide sans garde — rejeté : `contracts.md` §5 confie l'abstention au modèle (Faux LLM : `blocks` vide → `abstain: true`) et le critère dit « le Faux LLM s'abstient » ; aucune abstention sans appel n'est imposée.
- low, second avis 4 : test d'abstention trop lié au Faux LLM — corrigé : le test vérifie les `inputs` envoyés (`blocks == {}`, « (aucun passage) »), et `test_abstention_lue_sur_l_indicateur_pas_sur_le_texte` prouve que `abstained` vient du champ `abstain`, pas du texte.
- low, second avis 5 : le test du registre ne vérifiait plus `fixed_tokens` — corrigé : assertion ajoutée.
- low, second avis 6 : `tokenizer` nommé obligatoire dans `build_arch_answer` — gardé (le seuil de 8 000 tokens exige un comptage), écart consigné, report 4.2 ci-dessus.
- low, second avis 7 : le recouvrement est un minimum (au moins `overlap` tokens, à mot entier) et `key()` n'inclut pas le tokenizer — consigné : la clé d'index par défaut ajoute le nom du tokenizer (epic 4), donc deux tokenizers ne partagent pas un cache ; seuls les `passage_id` coïncideraient entre deux index distincts.
- low, second avis 8 : `invalid_citations` compte les étiquettes distinctes — consigné : le contrat dit « retirée et comptée » sans préciser ; une étiquette invalide répétée compte une fois, choix documenté dans les Design Notes.
- low, second avis 9 : `anchor_ids` non vide non imposé au formatage — consigné : l'invariant relève de `Passage` (contrat §1) et des chunkers ; `labeled` produit `[Sn] () texte` si on lui passe un Passage sans Ancrage.
- low, revue : le chunker joint les mots par une espace, le titre d'une section se colle à son corps dans `Passage.text` (vu sur le Mini-corpus) — consigné, sans effet sur les Ancrages ni sur les critères.
- Vérifié sur le Mini-corpus avec les paramètres par défaut (300/50, tokenizer `approx`) : 24 Passages, aucun au-delà de 300 tokens, `passage_id` uniques, Passages multi-Ancrages présents, génération nominale avec le Faux LLM.
