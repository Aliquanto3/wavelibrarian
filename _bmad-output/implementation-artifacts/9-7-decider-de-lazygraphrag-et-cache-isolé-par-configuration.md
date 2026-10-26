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
- Les Exécutions antérieures voient leur empreinte changer (champ `llm_cache` ajouté à la forme résolue), comme pour `max_error_rate` en 8.3 : une reprise d'une Exécution d'avant 9.7 est refusée.

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/llm/test_story_9_7.py tests/e2e/test_experiences_livrees.py
```
