---
story: "1.2"
title: Types du domaine et ports publiés
status: review
---

# Story 1.2 : Types du domaine et ports publiés

## Code Map

- `src/wavelibrarian/core/types.py` : types de `contracts.md` §1 (pydantic `frozen=True, extra="forbid"`), `ParsedCorpus.resolve` / `anchor_text`, `CorpusProfile.tokens_for`, `ModelRefMeta` / `ModelRef`, Literals.
- `src/wavelibrarian/ports/components.py` : `KINDS` (14 `kind`), `ComponentSpec`, Protocols des Composants, `SearchIndex`, `Context`, `GenerationResult`, `JudgeInput`.
- `src/wavelibrarian/ports/architecture.py` : `ArchitectureBase`, `ArchCapabilities`, `Applicability`, `CorpusChange`.
- `src/wavelibrarian/ports/gateway.py` : `LLMRole`, `Message`, `LLMRequest`, `LLMResult`, `ModelGateway`.
- `src/wavelibrarian/ports/measure.py` : `Tokenizer`, `Tracer`, `EnergyMeter`, `EnergyEstimator`.
- `src/wavelibrarian/ports/context.py` : Protocol `RunContext`.
- `tests/unit/core/test_types.py`, `tests/unit/ports/test_ports.py`.

## Design Notes

- `ModelCatalog` et `ProfileSettings` vivent dans `config`, couche supérieure à `ports` : `RunContext.catalog` et `.profile` sont typés `Any`, et `CorpusProfile.tokens_for` reçoit un Protocol minimal (`get(model_id)` avec `tokenizer` et `token_factor`). Les remplacer par les vrais types casserait le contrat `layers`.
- `ModelRefMeta` expose `role_default` et `answer_producer` ; `ModelRef = Annotated[str | None, ModelRefMeta]` suit le contrat littéralement (la classe sert de marqueur, l'instance se met dans l'`Annotated` du champ).
- `Embedder`, `VectorStore` et `LexicalIndex` sont `runtime_checkable` : `SearchIndex` (pydantic, `arbitrary_types_allowed`) les valide par `isinstance`.
- `ArchitectureBase.index_key` : `Params` résolus moins `query_params`, clé `parser` reprise des Params, nom du tokenizer. `answer_with_context` renvoie `retrieval_method="provided"`.
- `resolve` : page prioritaire, sinon titres (slugifiés par `core.ids.slug`) ; ancrage absent ou ni page ni titres : `None`. `anchor_text` d'un ancrage inconnu : chaîne vide.
- `Answer` ne porte pas de `Decimal` dans le contrat ; la sérialisation JSON des montants est testée sur `LLMResult`.
- `networkx` n'est importé que sous `TYPE_CHECKING` ; `numpy` est une dépendance directe.

## Tâches et critères

- [x] Tous les types de §1 avec noms et défauts du contrat : `test_tous_les_types_existent`, `test_defauts`.
- [x] `frozen=True, extra="forbid"` partout, champ inconnu et affectation refusés : `test_modeles_geles_et_stricts`, `test_champ_inconnu_et_affectation_refuses`.
- [x] `resolve` et `anchor_text` (AD-5, absent = `None`, ordre des Blocks) : `test_resolve_markdown_et_pdf`, `test_resolve_absent`, `test_anchor_text_concatene_dans_l_ordre`.
- [x] Montants en chaînes en JSON, relecture égale : `test_decimal_serialise_en_chaine_et_relecture`, `test_answer_aller_retour_json`.
- [x] Paquet `ports/` : noms exposés par `components`, `architecture`, `gateway`, `measure`, `context` : `test_ports_exposes_les_noms`, `test_quinze_roles_llm`, `test_kinds_ferme`.
- [x] `answer_with_context` et `update` par défaut : `test_answer_with_context_par_defaut`, `test_update_reindexe_dans_new_directory` ; `check` et `index_key` : `test_check_et_index_key_par_defaut`.
- [x] `core` et `ports` sans entrée-sortie, `lint-imports` passe : `tests/unit/test_garde_fous.py::test_lint_imports_passe` et contrôle rapide.
- [x] `CorpusProfile.tokens_for` : `test_tokens_for`.

## Auto Run Result

- Statut : prêt pour revue.
- `uv run pytest -q --tb=short` : 32 passés, 2 désélectionnés ; `uv run ruff check .` et `uv run pyright` sans erreur ; contrôle rapide sans erreur.
- Aucun appel réseau, ni Ollama, ni GPU (`CUDA_VISIBLE_DEVICES=-1`, threads à 4).
- Report : typage précis de `RunContext.catalog` / `.profile` quand `config` existera (story 1.4) si un Protocol commun est jugé utile dans `ports`.
