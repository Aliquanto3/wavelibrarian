---
story: "9.5"
title: "Juge unique calibré et Opus Juge principal des Expériences livrées"
status: review
---

# Story 9.5 : Juge unique calibré et Opus Juge principal des Expériences livrées

Exigences : FR-37, FR-33 ; AD-14 (amendé) ; `contracts.md` §4.4. Arbitrages A1, A2 (proposition du 2026-10-26). Partie code seulement : `corpora/minicorpus/calibration/opus.json` vient de la story réelle 9.9, donc la bascule des deux Expériences livrées est reportée (section « Bascule après 9.9 »).

## Réalisé

- **Juge unique** (`config/panel.py`) : `form_panel(..., calibration, kappa_threshold)` ; `panel_size: 1` passe par `_juge_unique`. Sans `judges.excluded_from` : `ConfigError` (code 2, chemin `judges.panel_size`). Sinon le premier modèle du réservoir d'une autre Famille que les `answer_producers` est retenu (règle de famille inchangée) ; aucun candidat : message « demander un Juge d'une autre Famille » (chemin `judges.pool`). `verifier_juge_unique` lit la calibration : le Juge doit y figurer, non exclu, avec un kappa ≥ `judges.kappa_threshold` (celui de l'Expérience, pas celui du fichier) sur `correctness`, `completeness` et `faithfulness` ; un kappa absent ou `null` compte comme sous le seuil. Les messages nomment le Juge et le Critère. `panel_size` ≥ 2 : code et messages inchangés (test `test_panel_de_deux_inchange_avec_calibration`).
- **Appelants** (`config/validate.py`, `runner/execute.py` `panels_de`) : passent `excluded_from` et `kappa_threshold`. Le refus tombe donc à `wl validate` et au lancement (code 2).
- **Verdict du Panel** (`scoring/panel.py`) : non modifié, `majorite` avec une seule voix rend déjà le verdict du Juge (`na` compris, sans égalité) ; verrouillé par `test_juge_unique_verdict_du_panel_est_celui_du_juge_na_compris`.
- **Rapport** (`report/generer.py`) : section « Juges », si `panel_size` vaut 1 et un seul Juge a voté : « Juge unique calibré : `<juge>` … sans règle de majorité ni égalité. Kappas juge-humain : … », kappas lus dans `calibration.json` de l'Exécution, sinon `judges.excluded_from`. Si tous les Juges admissibles ont `provider: fake` et qu'un `answer_producer` est réel : « **Qualité non interprétable : Juges factices.** ». `_donnees_calibration` factorise le choix de la source avec la section « Calibration des Juges ».
- **`experiments/mini-real-haiku.yaml`** : Juges factices gardés ; commentaire AD-14 (Opus ne juge pas un Generator Claude). `calibration-claude.yaml`, `mini-test.yaml`, `mini-cpu.yaml`, `lazy-seuil-cpu.yaml` non modifiés.
- **Tests** : `tests/unit/config/test_validate.py` (Juge unique admis au seuil exact ; sans calibration ; kappa 0,59 ; Critère absent ; kappa `null` ; Juge exclu ; Juge absent ; seuil de l'Expérience ; Generator `claude` + pool `[claude-opus-5-5]` ; Panel de 2 inchangé), `tests/unit/scoring/test_panel.py`, `tests/unit/report/test_story_9_5.py` (Exécution complète en profil `test` avec une calibration factice dans `tmp_path` : mention et kappas ; absence de mention avec 2 Juges ; avertissement « Juges factices » avec Generator réel).

## Bascule après 9.9

À appliquer par l'orchestrateur une fois `corpora/minicorpus/calibration/opus.json` commité (le chemin est relatif au fichier d'Expérience, résolu par `_chemin_absolu` depuis `experiments/`) :

```yaml
# experiments/mini-cpu.yaml  (et lazy-seuil-cpu.yaml, même bloc judges)
 judges:
-  pool: ["granite4.2:3b", "qwen3.5:4b"]  # Familles distinctes du Generator minicpm (AD-14)
-  panel_size: 2
+  pool: [claude-opus-5-5]  # Juge unique calibré (AD-14 amendé) ; Famille distincte de minicpm
+  panel_size: 1
+  excluded_from: ../corpora/minicorpus/calibration/opus.json
 budget:
-  per_run: {anthropic: {amount: "0.00", currency: USD}}
+  per_run: {anthropic: {amount: "3.00", currency: USD}}   # mini-cpu ; lazy-seuil-cpu : "2.00"
```

Vérifier ensuite `uv run pytest -q --tb=short tests/e2e` (Expériences livrées) et `uv run wl validate experiments/mini-cpu.yaml`. Mettre à jour les commentaires d'en-tête (plus de Juges locaux : le préambule « sans aucun appel d'API » de `mini-cpu.yaml` devient faux). `opus.json` doit contenir `claude-opus-5-5` non exclu, kappa ≥ 0,6 sur les trois Critères, sinon `wl validate` refuse (code 2).

## Reports

- Un Juge unique avec `judges.passes` ≥ 2 peut encore produire une égalité entre passes (règle de `majorite` inchangée) ; défaut `passes: 1`.
- `contracts.md` §4.4 et AD-14 non réécrits dans cette story (déjà amendés par la proposition du 2026-10-26).
- Le Rapport suppose un Juge unique par Exécution (union des Panels) ; plusieurs Juges uniques différents selon les Configurations n'affichent pas la mention.
- Plafond Anthropic de 3,00 / 2,00 USD : à valider contre le coût mesuré de la 9.9.

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/config tests/unit/scoring/test_panel.py tests/unit/report/test_story_9_5.py tests/unit/runner/test_story_4_9.py tests/e2e/test_experiences_livrees.py
```
