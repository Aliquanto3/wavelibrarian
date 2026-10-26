---
story: "9.7"
title: "Decider de LazyGraphRAG et Cache isolé par Configuration"
status: review
---

# Story 9.7 : Decider de LazyGraphRAG et Cache isolé par Configuration

Exigences : FR-27, FR-34 ; AD-3, AD-4. Constat 8.8 (c) : 64 notes `[0.0, ...]` du Decider `minicpm5:1b`, avec l'exemple `{"scores": [0.0, 0.0]}` dans le prompt ; arbitrage B2 de la 8.8.

## Réalisé

- `components/deciders/llm.py` : l'exemple de format du prompt système est `{"scores": [<score du passage 1>, <score du passage 2>, ...]}`, sans valeur numérique ; le reste du texte est inchangé. **Effet attendu** : le prompt change, donc les clés de Cache du Decider `llm` (tout rôle `grade_relevance`) changent ; les anciennes entrées ne sont plus lues (normal, un rejeu se repaie).
- `config/experiment.py` : champ d'Expérience `llm_cache: {isoler_configurations: bool}` (`LlmCacheSettings`, booléen strict, défaut `false`), présent dans `Experiment` et `ResolvedExperiment` (défaut côté résolu pour relire une Exécution antérieure) ; `resolve.py` le recopie. Champ ordinaire : il entre dans l'empreinte `experiment.sha256`, et une reprise ne peut pas le changer (ce n'est pas un plafond). Ajouté à `contracts.md` §4.4.
- `llm/cache.py` : `cache_key(..., scope=None)` ; avec un `scope`, `config_id` entre dans le contenu haché. Sans `scope`, clé strictement inchangée.
- `llm/gateway.py` : `MeteredGateway(cache_scope=callable)` appelé à chaque requête (la Configuration change en cours d'Exécution) ; `runner/wiring.py` le relaie ; `runner/context.py` : `Context(isoler_configurations=...)` (posé par `from_experiment`) fournit `lambda: self.config_id or None`. Deux Configurations qui font le même appel ont donc deux clés : chacune appelle le fournisseur et mesure sa latence (`from_cache=False`), au lieu de rejouer celle de la première ; un rejeu dans la même Configuration reste servi par le Cache.
- `experiments/lazy-seuil-cpu.yaml` : Decider `granite4.2:3b` (le Generator reste `minicpm5:1b-q4_k_m`), `llm_cache: {isoler_configurations: true}`, seuils 0,1 / 0,3 / 0,5. Juges inchangés (story 9.5).
- Tests `tests/unit/llm/test_story_9_7.py` (7, sans réseau) : texte du prompt figé et exemple sans score ; clés littérales d'avant la story identiques sans `scope` ; clés distinctes avec `scope` ; passerelle réelle (Faux LLM) : avec isolation deux Configurations appellent chacune, sans isolation la seconde est rejouée ; champ strict et défaut `false` ; `lazy-seuil-cpu.yaml` valide sans réseau, empreinte sensible à l'option.

## Reports

- Relancer le balayage `lazy-seuil-cpu` réel (Ollama requis, `granite4.2:3b`) : hors périmètre, à décider par Anaël.
- Les Juges de `lazy-seuil-cpu.yaml` (Panel dont `granite4.2:3b`, désormais aussi Decider) : voir la story 9.5.
- ~~Les Exécutions antérieures voient leur empreinte changer~~ : corrigé en revue (constat 1), `llm_cache` à sa valeur par défaut est omis de la forme résolue et de l'empreinte.

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/llm/test_story_9_7.py tests/e2e/test_experiences_livrees.py
```

## Revue

### Passe 1 (2026-10-26, SHA revu 2c7529d)

Branche à jour sur `main` (95ef5be). Liste du second avis (Haiku) reprise point par point ; correctifs vérifiés par mutation (chaque nouveau test échoue sans son correctif).

| # | Étiquette · gravité | Source | Décision | Constat |
|---|---|---|---|---|
| 1 | Important · medium | second avis | corrigé | `llm_cache` entrait dans `model_dump`, donc dans l'empreinte de toute Expérience : `mini-test.yaml` passait de `b5d018bc…` (v0.2.0) à `126831a7…`, et `--reprendre` refusait toute Exécution antérieure. `resolved_dict` omet `llm_cache` à sa valeur par défaut (empreinte et `experiment.resolved.yaml`) ; empreintes de `mini-test` et `mini-cpu` vérifiées identiques au code de `main`. Test : `test_empreinte_d_une_experience_pre_9_7_inchangee`. |
| 2 | Nit · low | second avis | rejeté | `run_id` dérivé de `model_dump` : il change, mais il est horodaté et neuf à chaque Exécution ; aucun effet sur la reprise (qui reçoit le `run_id`). |
| 3 | Important · low | second avis, tranché par l'orchestrateur | corrigé | `cache_scope` lisait `ctx.config_id` à tout appel : les Juges (`juger`, calibration) étaient isolés par Configuration et repayés N fois. La portée vaut la Configuration au Poste `query` seulement (`Context._portee_cache`) ; `judging`, `indexing` et `update` gardent la clé commune. Test : `test_isolation_cablee_depuis_le_yaml_et_limitee_au_poste_query`. Le Filtre closed-book passe par `Context.hors_execution` (jamais isolé). |
| 4 | Nit · low | second avis | rejeté | `ctx.config_id` non remis à zéro en fin de `juger` : sans effet sur le Cache depuis le constat 3 (portée liée au Poste), et le Tracer a besoin du `config_id` des spans de jugement. |
| 5 | Nit · low | second avis | corrigé (avec 3) | Index : les appels de construction (`indexing`, `update`) n'étaient plus partagés hors du cache d'index (`index_key`) ; ils gardent maintenant la clé commune. Le cache d'index ne dépend pas de `isoler_configurations` : pas de reconstruction forcée. |
| 6 | Nit · low | second avis | rejeté | Test de `latency_s` : la latence vient de l'appel au fournisseur, et les tests prouvent l'appel (`from_cache=False`, compteur d'appels) ; le Faux LLM déclare 0, un test de valeur ne prouverait rien de plus. |
| 7 | Nit · low | second avis | corrigé | Tests ajoutés : YAML → `validate_file` → `Context.from_experiment` → passerelle, clé des Juges et de l'indexation, empreinte pré-9.7. |
| 8 | Nit · low | second avis | corrigé | `contracts.md` (§4.4, `llm_cache`) : portée (`query` seulement) et omission de la clé par défaut dans l'empreinte. Les compositions de clé l. 395 et 523 décrivent des champs de la requête : inchangées. |
| 9 | Nit · low | second avis | rejeté, consigné | Le prompt du Decider n'est pas dans l'empreinte : comme tous les prompts de Composants depuis v0.1.0 ; un rejeu d'une Expérience v0.2.0 repaie et peut différer (déjà noté dans « Réalisé »). |
| 10 | — | second avis | fait | `tests/unit/runner` (175), `tests/unit/report` (75), `tests/unit/config` + `tests/unit/llm` (258), tests du Decider (97), `tests/e2e/test_experiences_livrees.py` (7) : verts. |

Complexité : 0 constat (la portée est un accès O(1) par appel).
