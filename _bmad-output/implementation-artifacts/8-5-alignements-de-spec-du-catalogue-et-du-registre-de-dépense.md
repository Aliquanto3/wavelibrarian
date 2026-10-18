---
story: "8.5"
title: "Alignements de spec du Catalogue et du Registre de dépense"
status: done
---

# Story 8.5 : Alignements de spec du Catalogue et du Registre de dépense

Exigences : FR-30, FR-33 ; AD-9 ; stories 1.4 et 1.8 (arbitrages P1 et P2). Tests et journal seuls : aucun code produit modifié.

## Réalisé

- `tests/unit/llm/test_ledger_cache.py` : `test_plafond_de_periode_deux_executions_de_0_90` (plafond de période 2,00 USD, horloge injectée). Deux Exécutions réglées à 0,90 ; réservation de 0,10 acceptée (1,90 <= 2,00) ; 0,30 refusée au titre de la période (2,20 > 2,00) ; acceptée au 1er novembre 2026 UTC. Le test à 3,00 USD (2 x 1,50) est supprimé (revue) : l'AC 1 le désigne, et le nouveau test porte la même couverture (refus au titre de la période, bascule au mois civil UTC suivant, solde de période).
- `tests/unit/config/test_catalog.py` : `test_cout_un_million_catalogue_livre` vérifie `Decimal("3.00")` (1 M + 1 M) et `Decimal("0.03")` (50 000 + 50 000) pour `claude-haiku-5-5`, et retire le commentaire « à arbitrer par Anaël », obsolète.

## Recalcul des exemples contre la règle

- 1 M entrée + 1 M sortie : prompt 1 000 000 > 100 000, palier x5 sur tous les postes : (0,10 + 0,50) x 5 = 3,00. Concorde.
- 50 000 + 50 000 : sous le seuil, prix de base : 0,10 x 0,05 + 0,50 x 0,05 = 0,005 + 0,025 = 0,03. Concorde.
- Registre : 0,90 + 0,90 = 1,80 ; + 0,10 = 1,90 <= 2,00 ; + 0,30 = 2,20 > 2,00. Concorde.
- Aucune contradiction entre les AC réécrits et le code.

## Journal : relevé de la page de prix (orchestrateur, 2026-10-18)

URL : https://platform.claude.com/docs/en/about-claude/pricing (sections « Model pricing », « Batch processing », « Long context pricing »). Haiku 5.5 jusqu'à 100 000 tokens de prompt : entrée 0,10, écriture cache 5 min 0,125, 1 h 0,20, lecture 0,01, sortie 0,50 $/Mtok ; au-delà (« over 100,000 tokens ») : 0,50 / 0,625 / 1 / 0,05 / 2,50, soit x5 sur tous les postes ; batch 0,05/0,25 puis 0,25/1,25 (x5). « A request's prompt length counts all of its input tokens, including cache reads and cache writes. Each request is priced on its own. » Concorde avec `defaults/models.yaml` (`above_prompt_tokens: 100000`, `multiplier: "5"`). Seuil strict (« over ») : `config/catalog.py:52` applique `>`. Aucun écart : le Catalogue ne change pas, rien à soumettre à Anaël.

## Acceptance Criteria

1. Test 1.8 : 0,90 + 0,90, accepte 0,10, refuse 0,30, accepte 0,30 au mois suivant (horloge injectée).
2. Test 1.4 : `Decimal("3.00")` et `Decimal("0.03")` pour `claude-haiku-5-5`.
3. Palier comparé à la page de prix, résultat daté et sourcé ci-dessus.

## Tâches

- [x] Test du Registre (1.8).
- [x] Test du Catalogue (1.4).
- [x] Journal du relevé de prix.

## Reports

Aucun.

## Revue

- low, second avis : ancien test à plafond 3,00 USD conservé alors que l'AC 1 le vise. Corrigé : supprimé, sa couverture (refus « période », bascule de mois, solde) est portée par le nouveau test.
- low, second avis : acceptations sans assertion de solde. Corrigé : `period_remaining` vérifié après 0,10 (0,10), après le refus (inchangé), après 0,30 le 1er novembre (1,70).
- low, second avis : relevé de prix sans citation. Rejeté : la spec recopie déjà l'URL, les sections et la citation de la page (journal ci-dessus).
- low, second avis : couverture 1.4 ailleurs. Rejeté : l'AC 2 exige ce test précis, présent.
- low, second avis : `isinstance` redondants. Rejeté : `Decimal("3.00") == 3.0` est vrai, le contrôle de type garde un sens.
- Report : aucun.
