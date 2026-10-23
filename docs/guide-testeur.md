# WaveLibrarian — guide de test

WaveLibrarian compare des architectures de recherche documentaire IA (sans contexte, contexte long, BM25, RAG naïf, RAG hybride, GraphRAG, PageIndex, LightRAG…) sur la qualité des réponses, le coût, la latence et l'énergie. Tout passe par la ligne de commande `wl`. Une Expérience (fichier YAML) produit une Exécution, et l'Exécution produit un Rapport.

Version testée : `main` (lot v0.2.0 en cours ; dernière release v0.1.0).

## 1. Installation (5 min)

Prérequis : Git, Python ≥ 3.12, [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/Aliquanto3/wavelibrarian.git
cd wavelibrarian
uv sync
uv run wl --help
```

À vérifier : l'installation se termine sans erreur, et l'aide liste les commandes `registre`, `run`, `rapport`, `calibrer`, `installer`, `questions`, `corpus` et `annotations`.

## 2. Parcours de test (hors réseau, gratuit)

Sur ce parcours, le profil `test` remplace le LLM par un Faux LLM et l'embedder par un embedder factice. Rien ne part sur le réseau et rien n'est facturé.

| # | Action | Ce qu'on attend |
|---|--------|-----------------|
| 1 | `uv run wl registre` | Liste des Composants et Architectures avec leurs paramètres, lisible |
| 2 | `uv run wl questions --help` puis `uv run wl corpus --help` | Les sous-commandes sont compréhensibles sans lire le code |
| 3 | `uv run wl run experiments/mini-test.yaml` | Validation, préflight, puis exécution sur le Mini-corpus fictif (20 documents). Compter 5 à 10 min (8 min 44 mesurées le 23/10 sur un poste chargé). |
| 4 | Ouvrir `.wl/runs/<run_id>/report/report.md` (+ CSV `costs`, `pairs`, `pareto`, `retrieval`) | Scores, coûts, énergie, latence et comparaisons appariées. Les coûts fictifs doivent être distingués du coût réel. |
| 5 | Interrompre un run (Ctrl+C), puis `uv run wl run experiments/mini-test.yaml --reprendre <run_id>` | La reprise repart de l'état enregistré au lieu de tout recommencer |
| 6 | `uv run wl rapport .wl/runs/<run_id>` | Régénère le Rapport à partir des seuls fichiers de l'Exécution |
| 7 | Casser volontairement une Expérience (copie de `mini-test.yaml` avec une architecture inconnue, un champ manquant ou un chemin faux) | Erreur claire avant l'exécution, sans trace Python illisible |
| 8 | `uv run pytest -q` (facultatif, long) | Suite de tests verte |

## 3. Hors périmètre de ce test

- `experiments/mini-cpu.yaml` et `lazy-seuil-cpu.yaml` : ils demandent Ollama et des modèles locaux. Comptez plus de 9 Go de RAM pour les Juges, et des runs de 10 à 60 min.
- `experiments/mini-real-haiku.yaml` : il appelle l'API Anthropic, avec une vraie clé et de vrais coûts.
- `wl calibrer` et `wl annotations` : la calibration réelle des Juges attend les annotations humaines.

## 4. Limites connues (inutile de les signaler)

- Le code de sortie de `wl run --tolerer-erreurs`, quand toutes les Questions sont en erreur, est en cours de correction.
- Sous Windows, la console peut mal afficher les accents de l'aide (`Exp�rience`). C'est un problème d'encodage de la console. Si ça gêne, utilisez Windows Terminal ou lancez `chcp 65001` avant.
- Les résultats sur le Faux LLM ne disent rien de la qualité réelle des architectures. Ils ne valident que la chaîne de bout en bout.

## 5. Retours attendus

Pour chaque retour : **commande lancée, résultat attendu, résultat obtenu**, avec l'OS et, si possible, la sortie console copiée.

Les points sur lesquels un avis nous intéresse le plus :
1. **Prise en main** : peut-on lancer un run sans aide ? Qu'est-ce qui manque dans l'aide ou le README ?
2. **Messages d'erreur** : sont-ils clairs et disent-ils quoi faire ?
3. **Rapport** : est-il lisible ? Les comparaisons entre architectures sont-elles compréhensibles ? Manque-t-il un indicateur ?
4. **Robustesse** : comportement sur interruption, reprise, fichiers manquants ou YAML invalide.
5. **Performance** : durée du run `mini-test` et charge du poste.

Envoyez les retours en issue GitHub sur le dépôt, ou en vrac par message à Anaël.
