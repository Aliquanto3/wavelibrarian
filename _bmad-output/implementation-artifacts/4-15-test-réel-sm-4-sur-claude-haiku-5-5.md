---
story: "4.15"
title: "Test réel SM-4 sur Claude Haiku 5.5"
status: ready-for-dev
---

# Story 4.15 : Test réel SM-4 sur Claude Haiku 5.5

Exigences : SM-4, FR-29, FR-30, FR-33, NFR-2, NFR-3 ; AD-9, AD-16. Dépend de 4.8 (plafond, registre), 4.12 (coûts du Rapport) et 4.14 (`mini-real-haiku.yaml`, `cli.py`, `tests/e2e`).

## Préparé hors exécution (pendant 4.14)

Aucun appel réseau n'a eu lieu. Livré : le squelette du test et son Expérience, plus un test sans réseau.

- `tests/real/test_sm4.py` : test `real_api` (convention de l'epic : `tests/real/`). Désélectionné par défaut (`addopts` de `pyproject.toml`), sauté sans `ANTHROPIC_API_KEY` dans l'environnement (`skipif` sur `os.environ`, le `.env` n'est pas lu par le garde). `tests/conftest.py` lui ajoute `enable_socket`.
- `tests/real/experiment_sm4.yaml` : Expérience minimale propre au test (profil `test`, `max_questions: 5`, Mini-corpus, une Configuration `naive_rag` avec Generator `claude-haiku-5-5`, embedder `fake`, Juges `[fake-llm-b, fake-llm-c]`, plafond `per_run` anthropic 5,00 USD, plafond mensuel 50 USD). Elle ne dépend pas de `mini-test.yaml` ni de `mini-real-haiku.yaml`.
- `tests/unit/test_story_4_15.py` : l'Expérience est valide sans réseau, 5 Questions, plafond 5,00 USD, Juges factices.

## Plafond de 5 $ : deux garde-fous

1. Mécanisme du produit : `budget.per_run.anthropic = 5.00 USD` dans l'Expérience. Le Registre (AD-9) réserve avant chaque appel et refuse au plafond ; l'Exécution sort alors en `budget_exceeded` (code 3), et le test échoue.
2. Garde du test : avant de lancer, il relit l'Expérience et exige un plafond Anthropic en USD d'au plus 5,00. Il exige aussi que la somme des spans soit sous 5 USD.

## Acceptance Criteria

1. Sans `ANTHROPIC_API_KEY`, le test est sauté ; `uv run pytest` (suite par défaut) ne le sélectionne jamais.
2. Avec la clé, `wl run` sur l'Expérience du test sort en code 0 (jamais 3), sous le plafond.
3. Pour chaque span `gen_ai.provider.name == anthropic` non servi par le Cache de réponses, `Decimal(wl.cost) == catalog.cost(model, Usage(tokens des attributs))`, exactement.
4. La somme des spans payants égale, à 0,005 USD près, la dépense réglée du Registre (`ledger.sqlite`, `provider='anthropic'`, `status='settled'`) pour ce `run_id`.
5. La somme de `cost_eur_real` de `report/costs.csv` égale, à 0,005 EUR près, la somme des spans convertie au taux `costs.fx` du dossier d'état.
6. Ni la clé ni `x-api-key` (insensible à la casse) dans aucun fichier de `runs/<run_id>/`.

## Tâches

- [x] Squelette `tests/real/test_sm4.py` et `tests/real/experiment_sm4.yaml` ; test sans réseau.
- [ ] Après 4.14 : lancer le test réel (commande ci-dessous), consigner le coût réel dans RUN-STATUS.
- [ ] Après 4.14 : traiter la section « À faire après 4.14 ».

## Commande exacte de lancement

```
# ANTHROPIC_API_KEY dans l'environnement (ou .env pour le produit ; le garde du test lit l'environnement)
uv run pytest -q --tb=short -m real_api tests/real/test_sm4.py
```

Contrôles sans réseau : `uv run pytest -q --tb=short tests/real tests/unit/test_story_4_15.py` (1 sauté ou désélectionné, 1 réussi) ; `uv run pytest -q --collect-only -m real_api`.

## Coût estimé

5 Questions, un seul appel Generator chacune (`naive_rag`, k = 5, passages de 300 tokens : environ 2 000 à 3 000 tokens d'entrée, au plus 512 de sortie), Haiku 5.5 à 0,10 / 0,50 USD par Mtok : environ 0,002 à 0,01 USD. Juges et embedder factices (coût nul). Le plafond de 5 $ laisse un facteur de marge supérieur à 500.

## Dépendances envers 4.14

- `mini-real-haiku.yaml` (5 Questions, plafond 5 $, Juges factices) et `mini-cpu.yaml` : l'AC de l'epic vise `mini-real-haiku.yaml`. Ce test utilise sa propre Expérience tant que 4.14 n'a pas livré ; une fois livrée, vérifier qu'elles restent équivalentes (ou faire pointer le test dessus).
- `cli.py` (`wl run` puis Rapport) et `report/` ne changent pas dans cette story ; 4.14 ne doit pas renommer `costs.csv`/`cost_eur_real` ni les attributs de trace utilisés ici.
- Ne pas lancer le test réel pendant que 4.14 tourne (consigne du run).

## À faire après 4.14 (rien n'est codé ici)

Vérifications réelles reportées sur cette story, hors zones modifiables pendant 4.14. Chacune est un petit appel borné, à budgéter dans les 5 $ ; à lancer au plus tard une fois, manuellement, après 4.14.

- `temperature` via `extra_body` et outil de sortie imposé (`emit_output`) acceptés par l'API (1.11).
- Un délai dépassé après envoi règle à l'estimation au lieu de libérer (vrai appel interrompu) ; `response.impacts` EcoLogits (`llm_impacts`, ecologits 0.11.3) (1.11).
- `wl questions generer` sur Haiku 5.5 réel : répartition des Types, Ancrages hors échantillon rejetés (3.3). Touche `cli.py` / `evalset` : à tester par une commande, sans modifier le code.
- Plafond couvrant les appels des Juges (2 par Réponse ok) sur une vraie Exécution (4.9) : exige des Juges réels ou un Faux LLM facturé, donc une Expérience non couverte par celle-ci.
- CAG : Corpus > 512 tokens, écriture de cache puis lecture dès la première Question ; Corpus plus court, tokens en cache nuls sans erreur (6.5). Demande une Configuration `cag` dans une Expérience réelle.
- Majorant de 400 tokens de la réserve de schéma de GraphRAG contre `count_tokens` d'Anthropic (7.5, 7.6).
- Kappas au Rapport (5.x / 4.11) : à relire sur une Exécution réelle si une calibration est ajoutée.
- Si l'un de ces points exige de modifier `experiments/`, `tests/e2e/`, `tests/conformance/`, `cli.py`, `report/` ou `runner/`, le faire dans un commit séparé après 4.14.

## Reports

- Ces vérifications n'entrent pas dans l'AC SM-4 : elles ne bloquent pas la clôture de la story.
