---
story: "9.3"
title: "Modalité « sans objet »"
status: review
---

# Story 9.3 : Modalité « sans objet »

Exigences : FR-36, FR-37, FR-38, FR-40 ; AD-14 ; `contracts.md` §1, §3, §4.6, §5, §7. Arbitrage A4 (proposition du 2026-10-26). Constat : 5 Réponses vides de PageIndex jugées fidèles par convention (série v0.2.0).

## Réalisé

- **Type** (`core/types.py`) : `VerdictValue = Literal["yes", "no", "na"]`, `NA`, `oui_non()` (`na` → `None`), `VerdictLu` (relit un booléen ancien en `yes` / `no`). `Verdict.verdict` et `PanelVerdict.verdict` passent en `VerdictLu` : les `verdicts.jsonl` et `panel.jsonl` antérieurs restent lisibles par `wl rapport` (test bout en bout). Le port `Judge.judge` rend `(VerdictValue, justification)`.
- **Juge** (`llm/roles.py`, `components/judges/llm.py`) : `FaithfulnessVerdict` (énumération `yes|no|na`) pour `faithfulness`, `CriterionVerdict` (`yes|no`) pour les autres : un `na` ailleurs échoue à la validation, donc nouvel essai puis `NonConformantOutput`. `JudgeOutput` (sortie générique du rôle) refuse aussi `na` hors `faithfulness`. Prompt : « réponds na si la réponse n'affirme rien de vérifiable (na n'est permis que pour faithfulness) ». **Le prompt et le schéma changent : les clés de Cache des Juges et l'empreinte des requêtes de `wl calibrer` changent** (un fichier `_verdicts.jsonl` de la 9.1 sera refusé par `--reprendre` ; l'empreinte des annotations change aussi, verdicts en chaînes).
- **Calcul automatique** (`scoring/answer.py` `faithfulness_sans_objet`, `scoring/panel.py`) : Réponse vide (ou faite de blancs) ou abstention → `faithfulness` = `na`, `judge_model: "auto"` ; `criteres_juges(question, answer)` retire `faithfulness` de la requête du Juge. Un Juge (autre implémentation) qui rend `na` hors `faithfulness` : clé laissée absente, avertissement.
- **Panel** : `na` si plus de la moitié des voix (Juges et passes) disent `na`, sinon majorité des `yes`/`no`, égalité → `no` + `tie` (inchangé).
- **Calibration** (`scoring/calibration.py`, `runner/calibrer.py`) : `VERDICTS = ("yes", "no", "na")`, `na` valide pour les trois Critères. Kappa (juge-humain et inter-annotateurs) sur les seuls items `yes`/`no` des deux côtés (`n_items`) ; `na_agreements` et `na_disagreements` ajoutés par Juge et Critère dans `calibration.json`. Instabilité : `na` ↔ `yes|no` compte. Pour une Réponse vide ou une abstention annotée en `faithfulness`, `wl calibrer` inscrit `na` pour chaque Juge et chaque passe sans l'interroger sur ce Critère. Verdicts écrits en chaînes dans `_verdicts.jsonl` (booléens relus).
- **Rapport** (`report/scores.py`, `generer.py`, `fraicheur.py`) : taux de oui hors `na` ; `LigneScore.n_na` et colonne `n_na` de `scores.csv` ; cellule « (n X, Y na) », ou « n/a (Y na) » sans `yes` ni `no` ; phrase d'intro. McNemar : les paires avec un `na` sont exclues (consigné dans la section « Comparaisons appariées » et dans §7).
- **Annotations** : `anael.yaml`, 5 `faithfulness` pageindex (q-014, q-016, q-025, q-040, q-042) de `yes` à `na`, note préfixée « Sans objet (story 9.3) … ». Réponses vérifiées vides (`text: ""`, `abstained: true`) dans `answers.jsonl` du run `20261018-115941-a2a512` (lecture seule).
- Autres : `evalset/closed_book.py` (le verdict `correctness` du Juge est comparé à `"yes"`), en-tête du paquet d'annotation (`yes, no ou na`), `contracts.md` §1, §3, §4.6, §5, §7.
- Tests : `tests/unit/runner/test_story_9_3.py` (bout en bout : abstention → `na` auto sans Juge, Panel `na`, Rapport `n/a (3 na)`, `(n 2, 1 na)`, `n_common` 0, anciens fichiers booléens, calibration avec accords `na`), plus ajouts dans `test_panel.py`, `test_calibration.py`, `test_calibration_calcul.py`, `test_llm_judge.py` ; tests 4.9, 4.11, 4.13, 5.2, 9.1 réalignés (verdicts en chaînes).

## Reports

- Section « Calibration des Juges » du Rapport : n'affiche pas encore `na_agreements` / `na_disagreements` (présents dans `calibration.json`).
- Page d'annotation et import (`scripts/page_annotation.py`, `importer_verdicts.py`) : bouton « sans objet » laissé à la story 9.4.
- `runner/execute.py` non modifié : sans Corpus de phase, `_non_juges` compte encore `faithfulness` d'une abstention parmi les Critères non jugés (cas marginal).
- Fichiers de calibration 9.1 (verdicts booléens) : relus, mais refusés par `--reprendre` (empreinte changée) ; recalibrer (9.9).

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/scoring tests/unit/components/test_llm_judge.py tests/unit/runner/test_story_9_3.py tests/unit/runner/test_story_4_9.py tests/unit/runner/test_story_5_2.py tests/unit/report
```
