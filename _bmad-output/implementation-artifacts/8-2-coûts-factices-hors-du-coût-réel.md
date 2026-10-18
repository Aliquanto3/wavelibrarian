---
story: "8.2"
title: "Coûts factices hors du coût réel"
status: review
---

# Story 8.2 : Coûts factices hors du coût réel

Exigences : FR-29, FR-31, SM-4 ; AD-8, AD-9 ; `contracts.md` §6, §7. Limite L2 : `report/couts.py` additionnait `wl.cost` de tous les spans.

## Réalisé

- `report/couts.py` : un span dont `gen_ai.provider.name == "fake"` va dans `LigneCout.api_fake` (colonne `cost_eur_fake` de `costs.csv`, ajoutée en dernière position) ; tous les autres (Anthropic, Ollama, spans locaux sans fournisseur) restent dans `api_real` (`cost_eur_real`). Le coût hors cache (`cost_eur_uncached`) ne compte plus le fake. `Couts.total_fake()` et `Couts.faux_llm_pur` (coût réel nul et coût fictif non nul) ; `total_configuration(..., fictif=True)` donne le coût fictif (+ possession).
- `report/fronts.py` et `section_fronts.py` : en Faux LLM pur, les fronts et le coût par Palier se calculent sur `cost_eur_fake`, avec une mention explicite dans « Configurations non dominées ». Sinon le front reste sur le coût réel.
- `report/section_couts.py` : colonne « € fictif (fake) » par Poste et ligne de paramètres « Coûts fictifs », dont la mention Faux LLM pur.
- Tests : `tests/unit/report/test_story_4_12.py` (2 tests : exclusion du fake, colonne séparée et front fictif), `tests/e2e/test_sm3.py` réaligné (réel hors fake, fictif à part), `tests/real/test_sm4.py` réaligné sur le Registre.
- Aucun AC, valeur par défaut ni prix du Catalogue modifié. La possession (calcul local) reste comprise dans `cost_eur_real`, comme avant.

## Résultat réel SM-4 (2026-10-18, `real_api`)

4 tests verts. `mini-real-haiku` : 21 appels, coût tracé 0,0092426 USD = Registre réglé (écart 0) ; `cost_eur_real` (hors possession) 0,008262 EUR = Registre converti 0,0082610 EUR, à l'arrondi micro-euro par ligne de `costs.csv` près. Expérience des Juges : 2 appels, 0,0010234 USD ; `cost_eur_real` 0,000915 EUR = Registre converti 0,000915 EUR. Les Juges factices de `mini-real-haiku` sont dans `cost_eur_fake`, hors de l'égalité. Dépense réelle relevée au Registre : 0,0102660 USD au total, loin du plafond de 5 USD.

## Acceptance Criteria

1. `cost_eur_real` ne somme que les spans de fournisseur non `fake` ; `cost_eur_fake` les somme à part, affichée comme fictive.
2. En Faux LLM pur, `cost_eur_real` (hors possession) vaut 0, `cost_eur_fake` porte les coûts, les fronts de Pareto se calculent dessus avec mention.
3. SM-4 : `cost_eur_real` égale la dépense du Registre Anthropic convertie en euros (0,005 EUR près).

## Reports

- `cost_eur_real` inclut encore le Coût de possession du calcul local (comportement 4.12) ; en Faux LLM pur avec calcul local il n'est donc pas strictement nul. Séparer la possession dans une colonne dédiée relèverait d'une autre story.
