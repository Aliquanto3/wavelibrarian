---
story: "6.5"
title: CAG
status: review
---

# Story 6.5 : CAG

## Code Map

- `src/wavelibrarian/architectures/cag.py` : `Cag(LongContext)` enregistrée `("architecture", "cag")`, capacités `requires_prompt_cache` et `full_corpus_in_prompt`, `retrieval_method: cited`.
- `src/wavelibrarian/components/generators/llm.py` : `LLMGenerator.preload(context)` (appel `complete`, rôle `generate`, étape `cag.preload`, `cache_system`, `max_tokens: 16`) ; le system est construit par la même fonction que pour `generate`, donc le préfixe est identique.
- Tests : `tests/unit/architectures/test_story_6_5.py` (Faux LLM, profil `test`).

## Design Notes

- `Cag` hérite de `LongContext` sans la modifier : `Params` (cache_system forcé à vrai), `index` (un Passage par Ancrage, `passages.jsonl`), `check` (fenêtre = entrée + `max_tokens`, palier ×1,5 pour `reference`), `answer`. Seul `load` change : il charge puis appelle `generator.preload(contexte)`.
- Le runner appelle toujours `load` (sous le Poste `indexing`, AD-8) : index construit ou servi par le cache préchargent donc de la même façon. Corpus vide : aucun appel.
- Le préchargement est un appel `complete` en texte libre, sans schéma : sa sortie est ignorée et ne peut pas être refusée comme non conforme.
- Refus d'un Generator sans `prompt_cache` : déjà porté par `requires_prompt_cache` dans `_verifier_capacites` (1.6), aucun code nouveau.
- `min_cacheable_tokens` : aucun test d'Architecture ne peut le faire respecter par le Faux LLM ; le test utilise un faux provider qui ne lit rien sous 512 mots. L'appel réussit, les tokens en cache sont nuls.
- Le préchargement passe par le Cache de réponses de la passerelle : sur un rejeu à l'identique, il est servi sans appel fournisseur (`wl.llm_cache_hit: true`), comme tout appel rejoué (FR-34).
- Pas de Configuration `cag` dans `experiments/mini-test.yaml` ni de suite de conformité : absents du dépôt (4.14).

## Tâches et critères

- [x] `index` écrit un bloc par Ancrage, `load` précharge tout le Corpus avec `cache_system: true` au Poste `indexing` : `test_index_ecrit_un_bloc_par_ancrage_et_load_precharge_au_poste_indexing`, `test_enregistrement_et_capacites`.
- [x] Index construit ou servi par le cache : même préchargement : `test_index_construit_ou_servi_par_le_cache_prechargent_de_la_meme_facon`.
- [x] Seconde Question : `wl.usage.cache_read_tokens` non nul, tracé à part, `retrieval_method: cited` : `test_seconde_question_lit_le_cache_trace_a_part_et_reponse_cited`.
- [x] Generator `prompt_cache: false` refusé à la validation : `test_generator_sans_prompt_cache_refuse_a_la_validation`.
- [x] `check` inapplicable (fenêtre, palier de `claude-haiku-5-5`), aucun appel : `test_inapplicable_au_dela_de_la_fenetre_et_du_palier_sans_appel`.
- [x] Corpus sous `min_cacheable_tokens` : succès, tokens en cache nuls : `test_corpus_sous_min_cacheable_tokens_reussit_sans_cache`.
- [x] Cas limites : `cache_system: false` refusé, Corpus vide sans appel : `test_cache_system_faux_refuse_et_corpus_vide_sans_prechargement`.

## Auto Run Result

- Statut : review. Vérifications finales dans le rapport.
- Reports : Configuration `cag` dans `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` (4.14) ; `Cag` dépend de `long_context.py` (4.6 en revue en parallèle) : à revérifier à l'intégration.
- Le Cache de réponses peut servir le préchargement sans réchauffer le cache du fournisseur lors d'un rejeu ; une option de contournement exigerait de toucher la passerelle (hors périmètre).
