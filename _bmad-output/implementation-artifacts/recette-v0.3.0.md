# Guide de recette du lot v0.3.0 (epic 9)

Durée : 20 à 30 min. Aucune dépense obligatoire ; un seul contrôle facultatif coûte ~0,70 USD (étape 6). Commandes depuis la racine du dépôt, `main` à jour. `WL_HOME` désigne `C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0`.

## 1. Suite et outillage

```
uv sync --extra energy
uv run pytest -q --tb=short
uv run ruff check . ; uv run pyright
```

Attendu : 1406 passed (9 deselected), ruff et pyright sans erreur. Les commandes réelles demandent `--extra energy` (`uv run --extra energy wl …`), sinon `wl` s'arrête au démarrage, avant tout appel.

## 2. Scores jugés par Opus (9.5, 9.6, 9.10)

Ouvrir `WL_HOME/runs/20261026-093758-1afc6b/report/report.md`.

Attendu :
- l'en-tête dit « Rejugement de l'Exécution `20261018-115941-a2a512` », avec q-044 écartée ;
- la section « Juges » dit « Juge unique calibré : `claude-opus-5-5` », avec les kappas 1,00 / 0,72 / 0,76 ;
- les « Scores » portent sur 18 Questions, la fidélité en « (n …, … na) » ;
- les coûts de génération sont marqués « copiés de » ;
- `judging` coûte environ 0,38 €.

Les chiffres et la comparaison avec les Juges locaux de la 8.8 sont dans `verifications-reelles-2026-10-26-v0.3.0.md` (b).

## 3. Calibration d'Opus (9.1, 9.2, 9.3, 9.9)

- Lire `corpora/minicorpus/calibration/opus.json` : `claude-opus-5-5` non exclu, `na_agreements` 5 en faithfulness.
- Relancer la commande de la série (a) **sans option** : elle doit refuser en code 2, avant tout appel, parce que le fichier de verdicts existe. Ajouter `--reprendre` donne « rien à reprendre », sans appel ni dépense.

## 4. Page et paquet d'annotation (9.4)

- Ouvrir `corpora/minicorpus/annotations-a-faire/annotateur2.html` (hors ligne). Attendu :
  - aucun verdict de Juge ;
  - aucun surlignage ;
  - la réponse attendue apparaît seulement dans correctness et completeness ;
  - le bloc fidélité porte la consigne stricte ;
  - trois boutons Oui, Non et Sans objet.
- Remplir 2 ou 3 lignes, exporter, puis importer sur une copie :
  `uv run wl annotations importer <copie de annotateur2.yaml> verdicts-annotateur2.json`. Seules les lignes `verdict` et `note` changent.
- `wl annotations exporter --help` montre `--depuis` et le tirage stratifié. Sur le run réel, le paquet fait -56 % de caractères par Réponse, sans aucun Passage tronqué.

## 5. Énergie et Cache (9.7, 9.8)

- `experiments/lazy-seuil-cpu.yaml` : Decider `granite4.2:3b`, `llm_cache: {isoler_configurations: true}`, Juge Opus.
- `contracts.md` §6 donne la règle d'énergie : `measured` si toutes les parts sont lues par un compteur, `mixed` si une part est mesurée et une autre estimée, `estimated` sinon. Sous Windows, une phase CPU vaut donc désormais `mixed`, puisque la RAM est estimée.

## 6. Facultatif, coût ~0,70 USD

Double annotation (9.12) : suivre `corpora/minicorpus/annotations-a-faire/LISEZMOI.md` quand un second annotateur a rempli la page. Attendu : le kappa inter-annotateurs figure dans `calibration-inter.json` et au Rapport.

## Points à trancher en recette

1. **Désaccords « sans objet »** en fidélité. Sur q-017 et q-033 (rag-naif et raptor), Opus répond `na` pour une Réponse qui se borne à répéter un mot de la question ou un identifiant de source (« S4 »). Tu les avais notées « non ». Faut-il garder `na`, ou les réannoter `na` ? Le kappa de fidélité d'Opus vaut 0,76 hors `na`.
2. **Règle d'énergie** (9.8). J'ai réécrit l'AC 3 : `measured` seulement si toutes les parts sont mesurées. Ta définition de `mixed` (A8) l'impliquait, mais la phrase d'origine disait « `measured` si le CPU l'est aussi ».
3. **Plafond de `calibration-opus.yaml`** : 5 USD au lieu de 4 USD (A2). Le coût mesuré a été de 3,32 USD.
4. **Juge unique**. La validation exige un kappa sur les 3 Critères, même si toutes les Questions sont courtes, parce qu'elle ne lit pas les Questions. Avec plusieurs passes, la majorité se calcule sur toutes les voix, comme avant.
5. **Seuil de LazyGraphRAG** (9.11, faite à 14:27 après ton feu vert). Avec granite, les notes du Decider sont presque toutes à 0 ou au-dessus de 0,7 : les seuils 0,1, 0,3 et 0,5 retiennent les mêmes Passages, à un près, et les scores ne se distinguent pas (McNemar p = 1,00). Je recommande de garder 0,1 (non modifié). L'écart de latence (41 s contre 9 s) vient du cache de préfixe d'Ollama, pas du seuil. Détail : `verifications-reelles-2026-10-26-v0.3.0.md` (c).
6. **Exécutions v0.2.0**. Leur Rapport compte encore la fidélité des Réponses vides comme oui. Seul `wl rejuger` recalcule les `na`.

## Résultat attendu de la recette

Si tout est conforme : release v0.3.0. Il faut alors mettre le numéro de version dans `pyproject.toml`, poser le tag annoté, publier la release GitHub et repasser le topic de `status-dev` à `status-test`. Rien de cela n'est fait avant ton accord.

Dépense API du lot : 4,07 USD sur 10, dont 3,32 pour la calibration, 0,43 pour le rejugement et 0,32 pour le balayage du seuil.
