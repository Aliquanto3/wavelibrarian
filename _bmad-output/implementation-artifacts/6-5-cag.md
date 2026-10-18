---
story: "6.5"
title: CAG
status: done
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
- Le préchargement ne passe jamais par le Cache de réponses (`gateway.complete(..., use_cache=False)`) : il doit réchauffer le cache de prompt du fournisseur, et son écriture reste au Poste `indexing`. Un rejeu d'une Expérience CAG (reprise comprise) repaie donc le préchargement ; sa réponse remplace l'entrée du Cache de réponses.
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
- Le préchargement contourne le Cache de réponses (revue) : un rejeu le repaie.

## Revue

- high, orchestrateur (n° 1), corrigé : le Cache de réponses servait le préchargement lors d'un rejeu ou d'un hit d'index (`wl.llm_cache_hit: true`), sans réchauffer le cache du fournisseur et en faisant disparaître l'écriture du Poste `indexing`. `MeteredGateway.complete` (et le Protocol, et la passerelle sous Poste du runner) prend `use_cache: bool = True` ; `preload` passe `use_cache=False`. Tests : hit d'index et rejeu entre deux Exécutions qui partagent `WL_HOME` atteignent le fournisseur (échouent si l'on retire `use_cache=False`). contracts.md mis à jour.
- medium, second avis (n° 2), corrigé : les deux Questions étaient identiques, la seconde était un rejeu du Cache de réponses. Deux Questions distinctes, `wl.llm_cache_hit` faux sur les deux, `cache_read_tokens` non nul dès la première grâce au préchargement.
- medium, second avis (n° 3), rejeté : le respect de `min_cacheable_tokens` est un comportement du fournisseur, aucun code du dépôt ne le décide ; le double le simule pour vérifier que l'appel réussit et que des lectures nulles remontent telles quelles, ce que demande le critère. Un cas « au-dessus de 512 » ne testerait que le double. La vérification réelle part en report (ci-dessous).
- low, second avis (n° 4), corrigé : `test_rejeu_d_une_experience_repaie_le_prechargement_au_poste_indexing` vérifie `wl.usage.cache_write_tokens > 0` au Poste `indexing` (faux provider qui facture l'écriture), et une Question qui lit sans écrire.
- low, second avis (n° 5), corrigé : `pytest.raises(ConfigError, ...)`.
- low, second avis (n° 10), consigné : `check` estime le Corpus brut (`tokens_for`), sans le system ni les étiquettes ; même écart que `long_context` (4.6), quelques dizaines de tokens par Ancrage. Seule une marge serrée près de la fenêtre ou du palier peut passer `check` puis dépasser de peu la fenêtre ou le palier chez le fournisseur. Accepté en l'état.
- low, second avis (n° 11), consigné : un Generator sans `preload` n'est refusé qu'à la construction (`ConfigError`), pas à la validation statique ; seul `llm` existe aujourd'hui. Report vers la validation statique si un second Generator apparaît.
- low, revue, consigné : le refus de `cache_system: false` sous `cag` cite « `long_context` » (validateur hérité). Cosmétique.

### Reports

- Rapport (coût de possession) : avec `use_cache=False`, chaque Exécution CAG repaie l'écriture du cache de prompt au Poste `indexing`, y compris sur un hit d'index et à la reprise ; la story Rapport doit présenter ce coût comme récurrent par Exécution, non amorti comme un index.
- Fournisseur réel (Anthropic, sans réseau ici) : vérifier sur `claude-haiku-5-5` qu'un préchargement d'un Corpus de plus de 512 tokens donne `cache_write_tokens > 0`, que la première Question lit le cache dans le TTL, et qu'un Corpus plus court donne des tokens en cache nuls sans erreur.
- Conformité 4.14 : Configuration `cag` dans `experiments/mini-test.yaml`, `tests/conformance/test_architectures.py`, `tests/e2e/test_sm3.py`.
