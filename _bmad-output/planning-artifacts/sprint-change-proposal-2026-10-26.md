---
date: 2026-10-26
scope: moderate
status: approved
approved: 2026-10-26 (« OK en bloc » d'Anaël, recommandations A1 à A10 retenues)
source: _bmad-output/implementation-artifacts/RUN-STATUS-v0.2.0.md, verifications-reelles-2026-10-18-v0.2.0.md, verifications-reelles-2026-10-26-v0.2.0.md, fix-arbitrages-8-3-8-8.md, 8-11-juges-claude-calibration.md
---

# Proposition de changement de sprint : epic 9 (lot v0.3.0)

## 1. Problème

La v0.2.0 est publiée (epic 8 clos le 2026-10-26). La calibration réelle a montré que les Juges locaux du profil `cpu` ne sont pas fiables (kappas de 0,19 à 0,53) : les scores de qualité des runs `mini-cpu` ne sont donc pas interprétables. Seul `claude-opus-5-5` passe le seuil de 0,6 sur les trois Critères après la réannotation de la fidélité (correctness 1,00, completeness 0,73, faithfulness 0,84). Anaël l'a retenu comme Juge principal le 2026-10-26.

Reports du lot v0.2.0 traités ici :

| # | Report | Source |
|---|---|---|
| 1 | Opus Juge principal dans les Expériences livrées, avec plafond ; AD-14 pour un Generator Claude | décision du 26/10, limites de la série du 26/10 |
| 2 | Rejuger le run mini-cpu du split dev (18 Questions, Gel b2) avec Opus | limite L3 confirmée |
| 3 | `wl calibrer` perd les verdicts payés en cas de plafond ou de 4xx | revue 8.11 (pre-existing) |
| 4 | Pas de modalité « sans objet » (Réponse vide jugée fidèle par convention) | série du 26/10 |
| 5 | Justification des Juges qui délibère jusqu'à la coupure | arbitrage B1 de la 8.8 |
| 6 | Balayage de `relevance_threshold` non discriminant (Decider 1 B, exemple `[0.0, 0.0]`) | arbitrage B2 de la 8.8 |
| 7 | Énergie : méthode `mixed`, poste `judging` non mesuré, GPU du profil `gpu` | reports 8.6 et fix-8-8 |
| 8 | Paquet long (~7 600 caractères par Réponse), tirage non stratifié, page hors code qui biaisait la fidélité | 8.9, réannotation du 26/10 |
| 9 | Kappa inter-annotateurs absent (hors run, humain) | série du 26/10 |

## 2. Impact

- **Epics 1 à 8** : pas de réouverture. Un nouvel epic 9, 12 stories (9.12 humaine, hors run), ajouté à `epics.md`.
- **PRD** (à appliquer après approbation) :
  - FR-36 : verdict `oui`, `non` ou `sans objet` ; justification d'une phrase.
  - FR-37 : ajout d'une exception, « un Juge unique est admis s'il est calibré au-dessus du seuil sur chaque Critère (FR-38) ; la règle de famille s'applique à lui ». La dernière conséquence (Panel local + Haiku au MVP) est remplacée par : « depuis la v0.3.0, `claude-opus-5-5` est Juge unique calibré des Expériences dont le Generator n'est pas Claude ».
  - FR-38 : kappa calculé hors `sans objet`, accords et désaccords `sans objet` comptés à part.
  - FR-32 : troisième étiquette « mixte » (CPU mesuré, RAM estimée).
- **Architecture** : AD-14 amendé (Juge unique calibré, `na` au Panel) ; AD-17 (phase `judging`, `mixed`, GPU du profil `gpu`). `contracts.md` : §4.4 (`panel_size: 1`, `llm_cache.isoler_configurations`), §4.3 (`energy.gpu`), §4.6 (`na`, paquet court), §5 (`rejudged_from`, verdicts au fil de l'eau), §6 (`mixed`), §7, §8 (`wl rejuger`, `wl annotations page`, `wl annotations importer`, `wl calibrer --reprendre/--ecraser`). Chaque story met à jour ce qu'elle touche.
- **Données** : `anael.yaml` (5 fidélités de Réponses vides passées à `na`) ; nouveau `corpora/minicorpus/calibration/opus.json` (dérivé du Mini-corpus fictif, publiable).
- **Pas d'UX** : seule la page d'annotation change, décrite dans la story 9.4.

## 3. Approche retenue

Ajustement direct : un nouvel epic, sans retour arrière. Le cœur est le Juge unique calibré. Il demande une recalibration d'Opus (9.9), puisque le prompt des Juges change (9.2, 9.3).

Le rejugement passe par une commande `wl rejuger` (9.6) plutôt que par un nouveau `wl run`. Elle ne demande pas Ollama, elle porte sur les Réponses mêmes qui ont été annotées, et elle resservira à chaque changement de Panel.

**Ressources.** Ollama sert à 9.11 seulement, en profil `cpu`, environ 1 h, sur accord d'Anaël. Le GPU ne sert qu'à une vérification facultative de 9.8, elle aussi sur accord.

**Dépense API estimée** (plafond du lot : 10 USD) :

| Poste | Estimation |
|---|---|
| 9.9 : calibration d'Opus, 40 Réponses × 5 passes | ~2,50 USD |
| 9.10 : rejugement, 72 Réponses (moins les `na` automatiques) | ~1,00 USD |
| 9.11 : balayage, 54 Réponses, surtout des abstentions | ~0,50 USD |
| Revues avec appels réels | ~0,20 USD |
| **Total** | **~4,20 USD** |

**Risques.**
- Le kappa d'Opus peut retomber sous 0,6 avec le nouveau prompt. La 9.9 s'arrête alors pour arbitrage avant 9.10 et 9.11.
- Le Decider `granite4.2:3b` sur CPU peut rester non discriminant. La limite est alors consignée.

## 4. Changements

| Story | Report | Contenu | Agent de dev |
|---|---|---|---|
| 9.1 | 3 | Verdicts de `wl calibrer` écrits au fil de l'eau, `--reprendre`, `--ecraser` | Sonnet |
| 9.2 | 5 | Justification d'une phrase, `maxLength: 200`, grammaire Ollama, troncature côté Anthropic | Sonnet |
| 9.3 ★ | 4 | `na` dans les annotations, les Juges, l'automatique, le Panel, le kappa et le Rapport ; 5 fidélités de `anael.yaml` passées à `na` | Opus (transverse) |
| 9.4 | 8, 9 | Paquet court, tirage stratifié, `--depuis` ; `wl annotations page` et `importer` ; scripts retirés | Sonnet |
| 9.5 ★ | 1 | `panel_size: 1` calibré ; Opus dans `mini-cpu` et `lazy-seuil-cpu` avec plafond ; `mini-real-haiku` à Juges factices | Sonnet |
| 9.6 | 2 | `wl rejuger` | Opus (runner, rundir, Rapport) |
| 9.7 | 6 | Prompt du Decider sans valeur, `granite4.2:3b`, `llm_cache.isoler_configurations` | Sonnet |
| 9.8 | 7 | `mixed`, phase `judging`, `energy.gpu` | Sonnet |
| 9.9 | 1 | Calibration réelle d'Opus, `opus.json` versionné | orchestrateur |
| 9.10 | 2 | Rejugement réel mini-cpu par Opus, série de vérifications | orchestrateur |
| 9.11 | 6 | Balayage réel (Ollama CPU, accord requis) | orchestrateur |
| 9.12 | 9 | Double annotation : préparée par le run, faite par un humain | humaine |

## 5. Arbitrages demandés à Anaël (une liste, avec recommandation)

Chaque point a une recommandation. Les recommandations sont déjà écrites dans les stories de l'epic 9 : une réponse « OK en bloc » suffit pour lancer le run.

| # | Question | Recommandation | Alternative |
|---|---|---|---|
| A1 | Panel des Expériences livrées. AD-14 et FR-37 exigent 2 Juges de familles différentes, or Opus est le seul Juge calibré. | **Juge unique calibré** (`panel_size: 1` admis seulement si le Juge passe le seuil sur chaque Critère d'un fichier de calibration). `mini-cpu` et `lazy-seuil-cpu` : `[claude-opus-5-5]`. `mini-real-haiku` : Juges factices gardés (c'est le test de coût SM-4, et aucun Juge non-Claude n'est calibré), mention « qualité non interprétable ». `calibration-claude` et `mini-test` : inchangés. | Opus + `qwen3.5:4b` avec le verdict d'Opus qui prime (le témoin qwen exige Ollama et ~30 min de jugement local par run) |
| A2 | Plafonds `per_run` Anthropic | `mini-cpu` 3,00 USD, `lazy-seuil-cpu` 2,00 USD, `calibration-opus` 4,00 USD ; plafond de période inchangé (50 USD) | |
| A3 | Rejuger le run mini-cpu | **`wl rejuger`** (nouvelle Exécution qui copie les Réponses des 18 Questions dev ; sans Ollama) | Nouveau `wl run` complet : préflight Ollama, génération servie par le Cache, énergie et latence rejouées donc non mesurées |
| A4 | « Sans objet » | Valeur `na`. `faithfulness` vaut `na` automatiquement (sans Juge) pour une Réponse vide ou une abstention. Les Juges peuvent dire `na` en `faithfulness` seulement. Le kappa est calculé hors `na`, avec le compte des accords et désaccords `na` à part. Taux de oui hors `na`. Les 5 fidélités des Réponses vides de `anael.yaml` passent de `yes` à `na`. | Kappa à 3 modalités ; `na` permis sur les 3 Critères côté Juges |
| A5 | Justification courte | Une phrase, `maxLength: 200` caractères (borné par la grammaire côté Ollama, tronqué à l'enregistrement côté Anthropic) ; budget de sortie inchangé | Schéma sans `justification` (perd l'explication de FR-36) |
| A6 | Calibration d'Opus | **5 passes** (FR-38 : au moins 5), ~2,50 USD ; fichier versionné `corpora/minicorpus/calibration/opus.json`, référencé par `excluded_from` | 2 passes comme la 8.11 (~1 USD, instabilité moins bien mesurée) |
| A7 | Paquet et page | Données de Réponse sur la 1re ligne seulement, `cited_anchors` réduit aux identifiants, cible de -50 % ; strates Configuration × Type de question, allocation proportionnelle ; page à l'aveugle, sans surlignage, réponse de référence seulement pour correctness et completeness, bouton « sans objet » | Tronquer les passages (le Juge les voit en entier : l'humain doit les voir aussi) |
| A8 | Énergie | `mixed` comme 3e méthode affichée à part ; phase `judging` mesurée pour les Juges locaux, hors coût de Configuration ; `energy.gpu: true` dans `gpu.yaml`. Vérification réelle GPU seulement sur ton accord (sinon « en attente ») | `mixed` en simple mention au Rapport, sans nouvelle valeur |
| A9 | Balayage LazyGraphRAG | Decider `granite4.2:3b`, prompt `{"scores": [<score du passage 1>, ...]}`, isolation du Cache par un champ d'Expérience `llm_cache.isoler_configurations`, seuils {0,1 ; 0,3 ; 0,5}. Juge : Opus. Ollama CPU ~1 h : je te demanderai le feu vert au moment de la 9.11. | Isolation par un paramètre propre à LazyGraphRAG |
| A10 | Double annotation (hors run) | 25 lignes tirées de `anael.yaml`, stratifiées par Critère, préparées pour un annotateur nommé `annotateur2` (renommable), fichiers hors de `annotations/` | |

## 6. Passation

- **Portée** : modérée (nouvel epic, amendement de FR-36, FR-37, FR-38, FR-32 et d'AD-14, pas de replanification).
- **Suite** : `bmad-sprint-planning` (epic 9 dans `sprint-status.yaml`), puis run autonome (`implementation-artifacts/run-autonome.md`), chaîne `agent-cost-kit` dev-story → second-avis → reviewer par story, suite complète avant chaque intégration, push en fin d'epic.
- **Succès** : 9.1 à 9.11 `done` ; `opus.json` au-dessus du seuil ; rejugement mini-cpu `completed` avec scores par Configuration consignés ; balayage consigné ; dépense du lot sous 10 USD ; 9.12 préparée ; recette d'Anaël avant la release v0.3.0.
