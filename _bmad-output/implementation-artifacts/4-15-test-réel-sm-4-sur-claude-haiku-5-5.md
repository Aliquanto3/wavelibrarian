---
story: "4.15"
title: "Test réel SM-4 sur Claude Haiku 5.5"
status: review
---

# Story 4.15 : Test réel SM-4 sur Claude Haiku 5.5

Exigences : SM-4, FR-29, FR-30, FR-33, NFR-2, NFR-3 ; AD-9, AD-16. Dépend de 4.8 (plafond, registre), 4.12 (coûts du Rapport) et 4.14 (`mini-real-haiku.yaml`, `cli.py`, `tests/e2e`).

## Réalisé

- `tests/real/test_sm4.py` : 4 tests `real_api` (désélectionnés par défaut, sautés sans `ANTHROPIC_API_KEY` dans l'environnement ; `tests/conftest.py` leur ajoute `enable_socket`). Le produit lit la clé dans `.env` du dossier courant puis l'environnement ; le garde du test lit l'environnement seul.
- Alignement sur l'AC de l'epic : le test lance `experiments/mini-real-haiku.yaml` (4.14), `experiment_sm4.yaml` est supprimée (pas de doublon). `tests/unit/test_story_4_15.py` valide sans réseau les deux Expériences.
- `tests/real/experiment_sm4_juges.yaml` : 2 Questions, Generator factice et Juge Haiku 5.5 réel (la Famille du Generator écarte son propre Juge, donc le Generator est factice) : le plafond et le Registre couvrent les appels des Juges.
- Deux appels directs : outil `emit_output` imposé accepté, et majorant du schéma comparé à `count_tokens`.

## Constats du test réel et corrections

- `temperature` : l'API refuse le paramètre pour Haiku 5.5 (HTTP 400 « deprecated for this model »), y compris via `extra_body`. Après revue : capacité `accepts_temperature` du Catalogue (`false` pour Haiku 5.5) ; la passerelle met alors `temperature=None` (clé de cache comprise, span `wl.temperature_omitted`) et `AnthropicProvider` ne l'envoie que si elle n'est pas `None` (AD-20 « si le fournisseur l'accepte »).
- Majorant de schéma : `count_tokens` mesure 518 tokens de surcoût (outil imposé + schéma de 49 tokens) contre un majorant de 400 + schéma : insuffisant. `schema_prompt_overhead` et `SURCOUT_SCHEMA` passent à 600 (marge de 155 sur la mesure).
- Rapport (AC « Rapport ») : `costs.csv` totalise tous les spans facturés, y compris les Juges factices dont le Catalogue donne un prix non nul. Le test compare donc la somme de tous les spans, convertis au taux de leur devise, et non celle des seuls spans Anthropic ; le Registre est comparé aux spans Anthropic.
- Le profil `cpu` de `mini-real-haiku` exige `uv sync --extra energy` (EcoLogits, CodeCarbon).

## Résultat réel (2026-10-18)

`mini-real-haiku` : 21 appels Anthropic payants (les autres, servis par le Cache de réponses, exclus), coût tracé 0,0059295 USD = Catalogue (égalité exacte) = Registre (écart 0). Expérience des Juges : 2 appels, 0,0009929 USD, écart Registre nul. Dépense totale de la session de mise au point : environ 0,03 USD pour 5 lancers du fichier, loin du plafond de 5 USD.

## Acceptance Criteria

1. Sans `ANTHROPIC_API_KEY`, le test est sauté ; `uv run pytest` (suite par défaut) ne le sélectionne jamais.
2. Avec la clé, `wl run` sur l'Expérience du test sort en code 0 (jamais 3), sous le plafond.
3. Pour chaque span `gen_ai.provider.name == anthropic` non servi par le Cache de réponses, `Decimal(wl.cost) == catalog.cost(model, Usage(tokens des attributs))`, exactement.
4. La somme des spans payants égale, à 0,005 USD près, la dépense réglée du Registre (`ledger.sqlite`, `provider='anthropic'`, `status='settled'`) pour ce `run_id`.
5. La somme de `cost_eur_real` de `report/costs.csv` égale, à 0,005 EUR près, la somme des spans convertie au taux `costs.fx` du dossier d'état.
6. Ni la clé ni `x-api-key` (insensible à la casse) dans aucun fichier de `runs/<run_id>/`.

## Tâches

- [x] Squelette `tests/real/test_sm4.py` ; test sans réseau.
- [x] Lancer le test réel et consigner le coût (ci-dessus ; RUN-STATUS non touché ici).
- [x] Traiter les points de « Vérifications réelles » qui relèvent de la story (ci-dessous).

## Commande exacte de lancement

```
# ANTHROPIC_API_KEY dans l'environnement ; uv sync --extra energy requis (profil cpu)
OMP_NUM_THREADS=4 uv run pytest -q --tb=short -m real_api tests/real/test_sm4.py
```

## Vérifications réelles : traitées et reports

Traitées : `temperature` (refusée, corrigé), `emit_output` imposé (accepté), majorant de 400 contre `count_tokens` (porté à 600), plafond couvrant les Juges (Juge Haiku réel).

Reports, hors de l'AC SM-4 :
- Kappas au Rapport : l'AC ne les demande pas et aucune calibration n'existe (epic 5) ; à relire quand une calibration réelle est ajoutée.
- Délai dépassé après envoi (appel interrompu réel) : exige de provoquer un timeout réel ; non bloquant.
- `response.impacts` EcoLogits : l'énergie des spans Anthropic reste estimée ; sans appel dédié au tracer patché.
- `wl questions generer` sur Haiku 5.5 réel (3.3) : commande à lancer à part, touche `cli.py` / `evalset`.
- CAG avec Corpus > 512 tokens (6.5) : le Mini-corpus est plus court (écriture de cache non exercée) ; demande un Corpus plus long.

## Revue

Revue unique (Opus 5.5), branche rebasée sur `main` (`d1aa862`) : aucun conflit, section « Deuxième série » de `verifications-reelles-2026-10-18.md` intacte.

- medium, second avis 1 — corrigé : `temperature` était retirée pour tout modèle Anthropic, sans trace et avec une clé de cache hachant `0.0`. Ajout de `ModelEntry.accepts_temperature` (défaut `true`, `false` pour `claude-haiku-5-5`), `LLMRequest.temperature: float | None` ; la passerelle met `None` si le modèle la refuse (clé de cache effective, attribut de span `wl.temperature_omitted`), Anthropic et Ollama n'envoient le champ que s'il n'est pas `None`. Tests : `test_temperature_retiree_si_le_modele_la_refuse`, `test_anthropic_sans_temperature_si_none` ; contracts.md mis à jour. Le manifeste ne porte aucun paramètre LLM : rien à y ajouter.
- medium, second avis 2 — corrigé : `test_sm4_temperature_et_outil_impose_acceptes` vérifie maintenant la capacité déclarée (HTTP 400 attendu avec `temperature` si `accepts_temperature: false`, puis appel accepté sans elle). Non relancé (interdit) : voir report.
- medium, second avis 3 — corrigé : rebase sur `d1aa862`, sans conflit.
- low, second avis 4 — reporté : `costs.csv` (`cost_eur_real`) additionne les prix fictifs des Juges `fake-llm-*` (voulu par contracts.md §4.2) sans les distinguer de la dépense réelle ; dans `mini-real-haiku` le total du Rapport n'est donc pas de l'argent réellement payé. À traiter au Rapport (colonne ou note « factice ») dans une story du Rapport.
- low, second avis 5 — corrigé : docstrings du test réel (majorant 600, SDK 1.15).
- low, second avis 6 — corrigé : `test_majorant_de_schema_unique` lie `SURCOUT_SCHEMA` à `AnthropicProvider.schema_prompt_overhead` (les Composants ne peuvent pas importer les providers).
- low, second avis 7 — corrigé : le majorant du test réel arrondit par `ceil(Decimal(n) * facteur)`, comme `MeteredGateway._estimation`.

Report à revérifier en réel (clé requise, environ 0,001 USD) : `uv run pytest -q --tb=short -m real_api tests/real/test_sm4.py::test_sm4_temperature_et_outil_impose_acceptes` doit passer (400 avec `temperature`, succès sans) ; puis `test_sm4_cout_trace_egal_cout_recalcule` pour confirmer qu'aucun appel Haiku de la passerelle ne porte `temperature` (la clé de cache des Réponses Haiku déjà en cache change : elles seront repayées une fois).
