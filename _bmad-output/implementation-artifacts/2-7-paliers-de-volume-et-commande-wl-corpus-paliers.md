---
story: "2.7"
title: Paliers de volume et commande `wl corpus paliers`
status: done
---

# Story 2.7 : Paliers de volume et commande `wl corpus paliers`

## Code Map

- `src/wavelibrarian/corpus/tiers.py` : `tirer_chemins(chemins, tiers, required_paths)` -> `{taille: source_path triés}`, `sous_corpus(parsed, chemins)`, `tirer(parsed, tiers, required_paths)` -> `{taille: ParsedCorpus}`.
- `src/wavelibrarian/cli.py` : commande `wl corpus paliers <corpus.yaml>` (seul ajout).
- `tests/unit/corpus/test_tiers.py` : tests de la story.

## Design Notes

- Emboîtement par construction : les Documents non requis (ordre de départ trié par `source_path`) sont mélangés une fois par `random.Random(int(sha16(seed, "tiers"), 16))` (même schéma que `Context.rng`, AD-20, sans dépendre du Context) ; le Palier k prend les `required_paths` plus le préfixe de `k - len(requis)` Documents.
- Erreurs `ConfigError` : `tiers.sizes[i]` si la taille dépasse le Corpus ; `tiers.sizes[0]` si les requis dépassent la plus petite taille ; `required_paths` si un requis n'est pas dans le Corpus.
- `sous_corpus` : `fingerprint` recalculée par `ingest.empreinte` ; le Palier égal au Corpus entier a donc la `fingerprint` du Corpus.
- La CLI ingère le Corpus (option `--parser`, cache de parsing) et tire sur les Documents ingérés, comme `tirer(parsed)` : un Document illisible n'entre dans aucun Palier. Elle ne connaît pas les `required_paths` (fournis par le runner, epic 4) et tire donc sans requis. Sans clé `tiers` : message, code 0.

## Tâches et critères

- [x] Emboîtement 5 ⊂ 10 ⊂ 20 et trois requis dans chaque Palier : `test_emboitement_et_requis`.
- [x] Même graine, mêmes Paliers ; autre graine, tirage différent : `test_graine_reproductible_et_variable`.
- [x] Requis plus nombreux que la plus petite taille : `test_requis_plus_nombreux_que_la_plus_petite_taille`.
- [x] Taille supérieure au Corpus, chemin `tiers.sizes[i]` : `test_taille_superieure_au_corpus`, `test_commande_taille_trop_grande`.
- [x] Sous-corpus `ParsedCorpus` avec sa propre `fingerprint` : `test_sous_corpus_et_empreinte`.
- [x] CLI : tailles et `source_path` en français, code 0 : `test_commande_paliers` ; sans `tiers` : `test_commande_sans_tiers`.
- [x] Garde-fou : requis hors Corpus : `test_requis_inconnu`.

## Auto Run Result

Voir le rapport de l'agent (suite complète, pyright et contrôle rapide).

## Revue

- medium, second avis 2 : corrigé. La CLI tirait sur les Documents déclarés alors que l'ingestion écarte les illisibles ; un seul Document écarté change tout le mélange, donc les Paliers affichés différaient de `tirer(parsed)`. La commande ingère désormais (comme `wl corpus profiler`) ; `test_commande_document_illisible_hors_paliers` échoue sans le correctif.
- medium, second avis 1 : reporté (epic 4, runner). L'AC de la commande ne demande pas de `required_paths`, et `tirer(parsed, tiers, required_paths)` les gère déjà. À vérifier : le runner déduit cette liste des Ancrages des Questions et la passe à `tirer`.
- low, second avis 3 : rejeté. `random.Random(int(sha16(str(seed), "tiers"), 16))` reprend exactement `Context.rng` (`runner/context.py`), que AD-20 autorise.
- low, second avis 4 : corrigé. Le test de graine vérifie aussi l'indépendance à l'ordre d'entrée, un tirage figé (graine 42) et quatre Paliers 5 distincts pour quatre graines.
