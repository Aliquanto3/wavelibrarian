# Vérifications réelles du 2026-10-26 (lot v0.2.0, stories 8.10 et 8.11)

Calibration réelle des Juges sur les annotations humaines d'Anaël. Windows 11. `WL_HOME` vaut `C:/Users/Utilisateur/Documents/GitHub/wl-runs-v0.2.0` (hors dépôt, non commité). Exécution annotée : `20261018-115941-a2a512`, le run mini-cpu de la story 8.8, avec l'ancien Gel (19 Questions dev). Le Gel b2 du même jour retire q-044 du split dev. Toute calibration relancée après ce Gel porte donc sur 88 lignes au lieu de 92.

| # | Vérification | Résultat | Sortie |
|---|---|---|---|
| a | 8.10 : Juges Ollama, profil `cpu`, `experiments/mini-cpu.yaml`, 5 passes | `granite4.2:3b` et `qwen3.5:4b` sous le seuil sur les 3 Critères, tous deux exclus | `calibration.json`, `calibration_verdicts.jsonl` |
| b | 8.11 : Juges Claude, `experiments/calibration-claude.yaml`, 2 passes, plafond de 10 $ | `claude-opus-5-5` au-dessus du seuil sur les 3 Critères (après réannotation) ; `claude-haiku-5-5` exclu | `calibration-claude.json`, `calibration-claude_verdicts.jsonl` |
| c | Réannotation à l'aveugle de la fidélité | Kappa d'Opus en faithfulness : 0,15 → 0,84 | `anael.yaml` (`d02ef03`) |
| d | Kappa inter-annotateurs | Absent : un seul annotateur, aucune double annotation | |

## Échantillon

`corpora/minicorpus/annotations/anael.yaml`, annotateur `anael`. Il compte 92 lignes Réponse × Critère sur 40 Réponses et 19 Questions : correctness 12, completeness 40, faithfulness 40.

- Première annotation (`56b7855`, 92 verdicts) : faithfulness 36 oui et 4 non, completeness 8 oui et 32 non, correctness 4 oui et 8 non.
- Réannotation de la fidélité (`d02ef03`) : 14 oui et 26 non.

Un Juge dont un appel n'a donné aucun verdict valide à la passe 0 n'entre pas dans le kappa de cette Réponse : c'est ce qui explique un `n` inférieur à 40.

## (a) et (b) Kappas Juge-humain

Seuil `kappa_threshold` : 0,6. Le kappa compare le verdict de la passe 0 à l'annotation. L'instabilité est la part des Réponses notées à au moins deux passes dont les verdicts diffèrent. Les kappas « réannotation » sont recalculés hors ligne : `scoring.calibration.fiches_du_juge` est appliqué aux verdicts enregistrés, sans nouvel appel.

| Juge | Critère | n | Kappa (1re annotation) | Kappa (réannotation) | Instabilité |
|---|---|---|---|---|---|
| claude-opus-5-5 | correctness | 12 | 1,00 | 1,00 | 0,00 |
| claude-opus-5-5 | completeness | 40 | 0,73 | 0,73 | 0,00 |
| claude-opus-5-5 | faithfulness | 40 | 0,15 | **0,84** (0,80 sans les 5 Réponses vides, n = 35) | 0,00 |
| claude-haiku-5-5 | correctness | 9 | 0,55 | 0,55 | 0,00 |
| claude-haiku-5-5 | completeness | 33 | 0,14 | 0,14 | 0,09 |
| claude-haiku-5-5 | faithfulness | 33 | 0,26 | 0,64 (0,59, n = 30) | 0,09 |
| qwen3.5:4b | correctness | 12 | 0,53 | 0,53 | 0,00 |
| qwen3.5:4b | completeness | 38 | 0,26 | 0,26 | 0,00 |
| qwen3.5:4b | faithfulness | 38 | 0,19 | 0,31 (0,25, n = 33) | 0,00 |
| granite4.2:3b | correctness | 11 | 0,23 | 0,23 | 0,09 |
| granite4.2:3b | completeness | 37 | 0,21 | 0,21 | 0,03 |
| granite4.2:3b | faithfulness | 37 | 0,22 | 0,40 (0,38, n = 32) | 0,06 |

**Exclusions constatées.** Avec la réannotation, seul `claude-opus-5-5` reste au-dessus du seuil sur les trois Critères. `claude-haiku-5-5` est exclu par completeness (0,14) et correctness (0,55). `qwen3.5:4b` et `granite4.2:3b` sont exclus sur les trois Critères. Les fichiers `calibration*.json` écrits par `wl calibrer` portent les kappas de la première annotation, parce que les annotations ont été lues au lancement. Ceux de la réannotation sont dans ce tableau.

**Décision d'Anaël (2026-10-26).** `claude-opus-5-5` devient le Juge principal. Sa mise en œuvre dans les Expériences livrées est reportée au lot suivant (voir Limites).

## Appels, passes et coût

- **Passes 1 et plus envoyées au fournisseur.** Le gateway n'utilise le Cache qu'à la passe 0 (`use_cache = pass_id == 0`). Les spans `judge` avec `wl.llm_cache_hit=true` sont donc des passes 0 : 17 côté Ollama (granite 12, qwen 5) et 11 côté Claude (Opus 6, Haiku 5).
- **Ollama (8.10).** Lancement à 05:44, fin à 08:07, soit 2 h 23 min, au rythme d'environ 3,2 appels par minute. Il y a eu 432 spans `judge`, dont 368 ok et 64 `non_conformant` relancés : granite 44, qwen 20. Coût API : 0. RAM libre au départ : 20,4 Go.
- **Claude (8.11).** Lancement à 06:15, fin à 06:22, avec 152 appels. On compte 182 spans `judge` : Opus 80, tous ok ; Haiku 102, dont 30 `non_conformant`. 8 Réponses de Haiku restent sans verdict de passe 0. Coût : **1,34 $**, sous le plafond de 10 $.
- **Revue de la 8.11.** 3 appels réels à Opus, pour environ 0,01 $.
  - `tool_choice` forcé : HTTP 400, « tool_choice: type "tool" and "any" are not supported for this model ».
  - `temperature` : HTTP 400, « deprecated ».
  - `tool_choice: auto` avec consigne : HTTP 200, `stop_reason: tool_use`.
  - Correctifs portés au Catalogue : `forced_tool_choice: false` et `thinking_reserve_tokens: 4000`.

## (c) Réannotation de la fidélité

Les 19 désaccords d'Opus en faithfulness allaient tous dans le même sens : l'humain disait oui, le Juge disait non. Les notes d'Anaël montrent une lecture lexicale : les mots de la réponse se retrouvent-ils dans un extrait ? Opus applique, lui, une lecture d'étayage : l'affirmation, prise comme réponse à la question, est-elle soutenue par les extraits ? C'est la lecture standard.

La page de la story 8.9 y poussait de trois façons : sa consigne était courte, elle surlignait dans les extraits les mots de la réponse, et elle affichait la réponse attendue.

La réannotation s'est faite à l'aveugle, sans voir les verdicts des Juges, sur une page hors dépôt (`Documents/annotation-fidelite-wavelibrarian.html`). Elle ne montre ni surlignage ni réponse attendue, et sa consigne est explicite : une réponse qui n'affirme rien est fidèle, et une réponse fidèle à un extrait faux reste fidèle.

Après réannotation, Opus garde 3 désaccords (q-004 en bm25 et en rag-naif, q-019 en rag-naif). L'humain y a dit non pour une réponse incomplète mais exacte au regard des extraits : c'est un défaut de completeness. Ces labels sont laissés tels quels.

Les 5 Réponses de PageIndex sans aucun extrait (q-014, q-016, q-025, q-040, q-042) sont vides. Opus et l'humain les jugent fidèles, puisqu'il n'y a aucune affirmation à vérifier.

## Limites

- **L3 confirmée.** Les Juges locaux du profil `cpu`, de 3 à 4 B, ne sont pas fiables sur ce corpus : leurs kappas vont de 0,19 à 0,53. Les scores de qualité des runs `mini-cpu` jugés par granite et qwen sont donc à lire avec cette réserve.
- **Opus Juge principal, au lot suivant.** Il faut l'ajouter aux Expériences livrées, avec un plafond Anthropic. Contrainte AD-14 : Opus ne peut pas juger un Generator Claude (`mini-real-haiku.yaml`) ; il faut alors un second Juge d'une autre famille.
- **Échantillon.** 92 lignes, un seul annotateur, dont 12 seulement en correctness : les intervalles des kappas sont larges. Une double annotation partielle par un second annotateur donnerait le kappa inter-annotateurs prévu par l'AC.
- **Pas d'état « sans objet ».** Une Réponse vide est jugée fidèle par convention, ce qui gonfle les oui. Une modalité « sans objet » est à étudier.
- **Verdicts perdus en cours de route.** Si le plafond est atteint ou si une erreur 4xx inattendue survient en cours de calibration, tous les verdicts payés sont perdus, parce que rien n'est écrit au fil de l'eau. C'est un défaut antérieur à ce lot, reporté.
- **`--reprendre` refusé** pour les runs faits avec l'ancien Gel (empreinte `76fa20b7…`).
