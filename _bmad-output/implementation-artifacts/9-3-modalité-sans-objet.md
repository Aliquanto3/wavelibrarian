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

- Page d'annotation et import (`scripts/page_annotation.py`, `importer_verdicts.py`) : bouton « sans objet » laissé à la story 9.4.
- Fichiers de calibration 9.1 (verdicts booléens) : relus, mais refusés par `--reprendre` (empreinte changée) ; recalibrer (9.9).

- Exécutions antérieures à la v0.3.0 (dont la série v0.2.0) : leur `panel.jsonl` garde la fidélité jugée (souvent `yes`) des Réponses vides et des abstentions ; `wl rapport` la relit telle quelle, sans réécriture des Exécutions anciennes. Pour corriger le Rapport v0.2.0 : `wl rejuger <run_id> <experience.yaml>` (story 9.6), qui recalcule `na` (consigné dans `contracts.md` §7).
- Cache de réponses : le prompt système et le schéma du Juge changent, donc la clé de Cache (`system` et `output_schema` y entrent) : aucun verdict mis en Cache avant la 9.3 n'est relu, il est redemandé (coût d'un premier rejugement). Le Filtre closed-book, qui passe par le même Juge, perd aussi ses entrées de Cache.

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/scoring tests/unit/components/test_llm_judge.py tests/unit/runner/test_story_9_3.py tests/unit/runner/test_story_4_9.py tests/unit/runner/test_story_5_2.py tests/unit/report
```

## Revue

### Passe 1 (2026-10-26, SHA revu 920da8f)

Base : `main` 9191109, branche à jour (pas de rebase nécessaire).

- Important · low · second avis 1 · corrigé : sans Corpus de phase, `_non_juges` comptait `faithfulness` d'une abstention comme non jugée ; `criteres_juges(q, a)` dans `runner/execute.py`, test `test_sans_corpus_de_phase_…` (échoue sans le correctif).
- Important · low · second avis 2 · corrigé : ligne `judge` du tableau des rôles de `contracts.md` §2.2 corrompue (fragment dupliqué, `|` non échappés qui cassaient le tableau).
- Nit · medium · second avis 3 · consigné (règle inchangée, décision de l'orchestrateur) : `majorite` compte une voix par Juge et par passe ; avec `passes` > 1, un Juge à deux `na` sur trois passes donne `na`. Règle écrite dans `contracts.md` §5 (`panel.jsonl`) ; tests `test_juge_unique_une_passe_verdict_du_juge_na_compris` et `test_plusieurs_passes_chaque_passe_est_une_voix`.
- Nit · medium · second avis 5 · reporté (consigné) : Exécutions antérieures non corrigées sans `wl rejuger` ; Reports ci-dessus et `contracts.md` §7.
- Nit · low · second avis 10 · corrigé : tests ajoutés pour le Corpus absent (point 1) et pour un paquet d'annotation exporté puis rempli de `na` nus, rechargé par `charger_dossier` (`test_story_8_9.py`). Cache : vérifié dans `llm/cache.py` (`system` et schéma dans la clé), consigné dans les Reports.
- Nit · low · second avis 11 · corrigé : section « Calibration des Juges » du Rapport, colonne « na (accords / désaccords) » (juge-humain et inter-annotateurs, `n/a` pour un `calibration.json` antérieur), phrase d'intro sur `Items` ; test dans `test_story_9_3.py`, attendus de `test_story_8_9.py` réalignés.
- Second avis 4, 6 à 9 : RAS, confirmé.
- Complexité : 0 constat (`_nombre_na` en O(1) par Réponse, aucun parcours complet par événement).
