---
story: "4.14"
title: "Suite de conformité, Expériences livrées et test de bout en bout SM-3"
status: review
---

# Story 4.14 : Suite de conformité, Expériences livrées et test de bout en bout SM-3

## Code Map

- `experiments/mini-test.yaml` (nouveau) : profil `test`, split `test`, Scénario du Mini-corpus, `tier: 20`, Conditions `[standard, perfect_context]`. Il contient 17 Configurations pour les 15 Architectures du registre : `graphrag` en deux entrées (`search: local` et `search: global`) et `hybrid_rag` en deux entrées (rrf, puis `reranker: fake`). Les Architectures à embeddings utilisent `embedder: fake`.
- `experiments/mini-cpu.yaml` (nouveau) : profil `cpu`, sans API. Le Generator et les modèles de résumé et de sélection sont `minicpm5:1b-q4_k_m`, les Juges `[granite4.2:3b, qwen3.5:4b]` (d'autres Familles que minicpm), avec `max_questions: 2`. Configurations : `bm25_only`, `naive_rag`, `raptor` et `pageindex`.
- `experiments/mini-real-haiku.yaml` (nouveau) : Generator `claude-haiku-5-5`, `max_questions: 5`, plafond de 5,00 USD. Juges `[fake-llm-b, fake-llm-c]`, embedder `fake` épinglé sur `fake-embedder`, sans quoi le profil `cpu` le résoudrait en `multilingual-e5-small`. Configurations : les trois Baselines, `naive_rag` et `cag`.
- `tests/conformance/test_architectures.py` (nouveau) : paramétré sur `registry.names("architecture")` × les Configurations de `mini-test.yaml`. Une Architecture qui n'a pas de Configuration y produit un cas en échec.
- `tests/e2e/test_sm3.py` (nouveau) : lance `wl run experiments/mini-test.yaml` (environ 60 s), puis vérifie le Rapport, le coût, l'export du front et `reuse_index`.
- `tests/e2e/test_experiences_livrees.py` (nouveau) : chaque `experiments/*.yaml` est validé sans réseau, avec des contrôles propres à `mini-cpu` et à `mini-real-haiku`.

## Design Notes

- Conformité, par cas : l'indexation passe par `IndexCache.build`, comme le runner. Les cas vérifiés :
  - une Réponse non abstenue citée sur `CONFORMANCE_QUESTION_ID`, sauf pour `retrieval_method: none` ;
  - toute Citation est un Ancrage du Corpus ;
  - des Réponses identiques avec et sans cache d'index, et la même clé ;
  - l'abstention sur un contexte vide ;
  - en contexte parfait, des Citations prises parmi les Ancrages de référence ;
  - `index_key` change quand on modifie `generator.params.max_tokens`, un Param hors `query_params`. Il reste stable quand on incrémente un `query_params` entier.

  La mise à jour applique le Scénario par `update` (`post="update"`). On vérifie ensuite que `note-obsolete.md` n'apparaît ni dans `retrieved`, ni dans `context_anchor_ids`, ni dans les Citations. Cette vérification porte sur q-001 et sur les Questions ancrées dans ce Document.
- `ctx.parser` est résolu par `nom_parser_resolu(parsers_par_format(...))`, parce que `index_key` refuse `auto`. `CONFORMANCE_QUESTION_ID` s'importe par `from conftest import` : les tests sont en mode `prepend`, ce qui suppose de ne pas passer à `--import-mode=importlib`.
- « Six fichiers CSV » de l'AC : `contracts.md` §6 ne liste que cinq CSV (`scores`, `pairs`, `pareto`, `costs`, `retrieval`). Le test exige ces cinq CSV, non vides, plus `report.md`.
- Coût, contrôlé dans les deux sens : la somme des `wl.cost` des spans égale la somme réglée au registre `ledger.sqlite` de l'Exécution. `costs.csv`, sans la possession, égale cette somme multipliée par `fx.rates_to_eur.USD`, au centime près.
- `rag-correctif` utilise des Passages de 64 tokens. Avec le faux embedder (sac de mots haché sur la dimension du Catalogue), des Passages de 300 tokens rendent la recherche dense presque aléatoire sur q-001. Le Decider (seuil de 0,5) s'abstient alors à juste titre. L'Architecture n'est pas en cause et rien n'est masqué : le motif est écrit en commentaire dans le YAML.

## Conformité par Architecture (Faux LLM)

Les 15 Architectures passent les deux tests de conformité et le SM-3. Elles répondent sans erreur dans les deux Conditions et les deux phases : `no_context`, `long_context`, `bm25_only`, `naive_rag`, `hybrid_rag` (rrf et rerank), `hyde`, `corrective_rag` (Passages de 64 tokens, voir plus haut), `cag`, `raptor`, `pageindex`, `llm_wiki`, `agentic`, `graphrag` (local et global), `lazy_graphrag` et `lightrag`. Il n'y a aucun `xfail`.

## Vérification réelle (2026-10-18, partielle)

`OMP_NUM_THREADS=4 WL_HOME=<scratch> uv run wl run experiments/mini-cpu.yaml` a rendu le code 0, au statut `completed` (6 min 30). Ollama est devenu injoignable à 07:49:48, quand le banc a été repris par Anaël.

- Ce qui a été vérifié avant la coupure :
  - `bm25` : 2 Réponses `ok` ;
  - `rag-naif` : 1 Réponse `ok`, et 1 `NonConformantOutput`, parce que `minicpm5:1b` ne suit pas le schéma `GenerateOutput` ;
  - RAPTOR sur `minicpm5:1b` : 5 résumés, avec au plus 2 398 tokens d'entrée pour une fenêtre de 32 768. Le journal ne signale ni troncature ni groupe hors fenêtre.
- Ce qui n'a pas été vérifié, faute d'Ollama :
  - l'indexation PageIndex (`ProviderError`) ;
  - les Juges (8 Critères sans verdict).

## Reports

Traités :
- Configuration et conformité pour chaque Architecture des epics 6 et 7 (6.1 à 6.5, 7.1 à 7.4, 7.6 à 7.8), dont `graphrag` local et global, `lazy_graphrag` et `lightrag`.
- `update` passé par `IndexCache.build(post="update")` pour chaque Architecture (4.7, 7.2).
- Expériences à Paliers : le test des Expériences livrées exige `max_questions` dès qu'une Expérience pose un `tier` sur le split `dev` (4.6).
- Coût du Rapport égal au coût tracé (4.12).
- `pareto.csv` porte le front `qualite-cout` à coût fake presque nul ; le front exporté, relancé par `wl run`, rend le code 0 ; `reuse_index` est refusé sur un autre `WL_HOME`, avec le code 2 (4.13).
- `CONFORMANCE_QUESTION_ID` importé par `from conftest import` (3.7).

Partiels :
- RAPTOR sur `minicpm5` : la fenêtre est vérifiée en réel. PageIndex n'est pas vérifié en réel (Ollama coupé), et le dépôt ne contient pas de long PDF sous licence ouverte. Commande à relancer quand Ollama sera libre : `OMP_NUM_THREADS=4 WL_HOME=<dossier neuf> uv run wl run experiments/mini-cpu.yaml`, après `uv sync --extra local --extra energy` et `wl installer --profil cpu`.
- `wl run` sur le profil `cpu` : code 0, mais les Juges et PageIndex ne sont pas jugés.

Laissés, avec leur motif :
- Tests `real_*` du marqueur `AUCUN_POINT_UTILE` (graphrag global, 7.6), et calibrage de `relevance_threshold` avec la notation par lots (lazy_graphrag, 7.7) : ils demandent un vrai modèle, or Ollama est interdit pendant la story et l'API relève de la 4.15.
- Calibrage réel par `wl calibrer` (5.2) : il n'y a pas d'annotations, et Ollama est interdit. À faire avec Anaël.
- `index_gb` du Coût de possession (4.12) : la taille de l'index n'entre pas au manifeste ; c'est hors périmètre.
- `minicpm5:1b` non conforme au schéma `GenerateOutput` sur une Question sur deux : à voir en 4.15 ou au choix des modèles du profil `cpu`. On peut envisager un Generator plus gros ou des relances.
- SM-4 (`mini-real-haiku.yaml` réel, `real_api`) : story 4.15.
