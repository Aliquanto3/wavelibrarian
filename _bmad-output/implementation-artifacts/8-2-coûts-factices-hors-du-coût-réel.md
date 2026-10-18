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
2. En Faux LLM pur, `cost_eur_real` vaut 0, `cost_eur_fake` porte les coûts, les fronts de Pareto se calculent dessus avec mention.
3. SM-4 : `cost_eur_real` égale la dépense du Registre Anthropic convertie en euros (0,005 EUR près).

## Reports

- Levé à la revue : la possession calculée sur une énergie factice va dans `cost_eur_fake` ; en Faux LLM pur `cost_eur_real` vaut 0 exactement (AC 2 d'origine, sans « hors possession »).
- À confirmer par Anaël (choix de revue, aucun AC ni contrat changé) : en profil `test`, la part matérielle de la possession des spans locaux (secondes CPU réelles × prix du matériel) est classée fictive avec l'énergie factice, pour que `cost_eur_real` soit nul. Une énergie `measured` reste réelle.

## Revue

Revue Opus du 2026-10-18 sur `235ebad..21497bc`, avec le second avis (Haiku). Run `experiments/mini-test.yaml` rejoué : avant correctif `cost_eur_real` = 0,021062 € (102 lignes non nulles) ; après, 0 exactement, `cost_eur_fake` = 2,182274 €.

- high, second avis 1 : corrigé. AC 2 violé, mais la cause était la possession des spans `local` sans fournisseur (index, BM25), dont l'énergie vient du `FakeMeter` ; les spans `embed` fake ont 0 kWh et 0 s. Possession fictive (span `fake`, ou énergie non `measured` sous `energy.local: fake`) → `cost_eur_fake` ; `possession_eur` ne garde que la possession réelle.
- medium, second avis 2 : corrigé. Conséquence du 1 : la mention « `cost_eur_real` vaut 0 » est maintenant vraie, et `faux_llm_pur` exige `total_reel() == 0`.
- medium, second avis 3 : corrigé. En Faux LLM pur, le coût par requête et le point mort lisent `real + fake`, mention dans les paramètres.
- medium, second avis 4 : corrigé. `faux_llm_pur` repose sur l'absence de span d'un fournisseur réel (`spans_reels == 0`, Cache compris), plus sur un coût nul. Test `test_cache_reel_a_cout_nul_n_est_pas_du_faux_llm_pur`.
- medium, second avis 5 : corrigé en partie. Dans un run mixte, le front reste sur le coût réel (AC 1) ; une mention « Coûts fictifs exclus » donne le montant fictif écarté.
- low, second avis 6 : corrigé. Mention Faux LLM pur dans « Résultats par Palier ».
- low, second avis 7 : corrigé. `test_sm3` vérifie `cost_eur_real == 0 == possession_eur` sur chaque ligne ; test unitaire `test_possession_d_une_energie_factice_hors_du_cout_reel`.
- low, second avis 8 : rejeté. Vérifié sur `mini-test` : tous les spans `llm`, `embed` et `rerank` portent `fake` ; seuls les spans `local` (sans modèle) n'ont pas de fournisseur, par construction.
- medium, revue : corrigé. `test_story_4_13::test_front_qualite_cout_recalcule_depuis_les_csv` recalculait le front sur `cost_eur_real` ; en Faux LLM pur, il lit `cost_eur_real + cost_eur_fake` (AC 2).
- low, revue : corrigé. La spec reformulait l'AC 2 en « hors possession » : texte d'origine rétabli.
- SM-4 non relancé : le chemin réel (profil `cpu`, compteur codecarbon, spans Anthropic) n'a pas changé, et le test soustrait déjà `possession_eur`.
