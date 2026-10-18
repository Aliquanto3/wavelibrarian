---
date: 2026-10-18
scope: moderate
status: approved
source: _bmad-output/implementation-artifacts/epics-1-7-retro-2026-10-18.md
---

# Proposition de changement de sprint : epic 8 (lot v0.2.0)

## 1. Problème

La v0.1.0 (epics 1 à 7, 56 stories) est acceptée avec des points ouverts. Les vérifications réelles du 2026-10-18 ont montré que le Faux LLM masquait des défauts. Quatre limites faussent encore les résultats réels : `wl run` sort en `completed` et code 0 même si une Architecture n'a rien répondu (L1) ; `cost_eur_real` compte les Juges factices (L2) ; `wl calibrer` n'a jamais tourné sur des annotations réelles (L3) ; PageIndex sur CPU tronque ses sorties (L4). À cela s'ajoute un correctif : `corpus/declare.py:119` accepte `cc-by-nc-*` comme licence ouverte (P5). Anaël a tranché P1 à P9 ; les décisions sont déjà dans `epics.md` (stories 1.4, 1.8, 7.5) et dans `contracts.md`.

## 2. Impact

- **Epics 1 à 7** : pas de réouverture. Les AC des stories 1.4, 1.8 et 7.5 sont déjà réécrits ; les tests correspondants sont alignés par la story 8.5.
- **Nouvel epic 8** : 10 stories, dans l'ordre imposé F, B, A, G, H, E, D, run du split dev, C.
- **PRD** : aucune modification. FR-5, FR-29, FR-32, FR-38 et SM-5 restent valables ; l'epic 8 les réalise mieux.
- **Architecture** : `contracts.md` est déjà à jour (§2 `kind`, §4.1 licences, §4.2 `think`, §5 `max_error_rate` et `completed_with_errors`, §6 `wl.energy_source`, §8 codes de sortie et `--tolerer-erreurs`). La story 8.9 ajoutera la commande d'export du paquet d'annotation au §8.
- **Pas d'UX** : le produit n'a qu'une CLI.

## 3. Approche retenue

Ajustement direct : un nouvel epic, sans retour arrière. Risques : 8.6, 8.7, 8.8 et 8.10 dépendent du matériel réel (Windows, Ollama sur CPU) ; 8.10 attend les annotations d'Anaël. Les stories 8.1 à 8.5 et 8.9 tournent sans réseau et peuvent passer en run autonome.

## 4. Changements

| Story | Item rétro | Contenu |
|---|---|---|
| 8.1 | F (P5) | Liste blanche SPDX exacte ; `-NC`, `-ND` et inconnues restrictives ; message nommant les deux Documents identiques |
| 8.2 | B (L2) | `cost_eur_real` sans les spans `fake` ; colonne `cost_eur_fake` ; SM-4 vert |
| 8.3 | A (L1, P9) | `completed_with_errors`, `max_error_rate` 0,2, code 1, `--tolerer-erreurs`, bandeau du Rapport, reprise |
| 8.4 | G (P7) | `think: bool \| None = False` au Catalogue, clé de cache, run mini-cpu inchangé |
| 8.5 | H (P1, P2) | Test 1.8 à 0,90 + 0,90 sous 2,00 ; test 1.4 ; palier ×5 vérifié contre la page de prix |
| 8.6 | E (P4) | `windows_emi` vérifié sous charge, `measured` si le compteur suit, `wl.energy_source` |
| 8.7 | D (L4) | Étude `select_max_tokens`, `repeat_penalty`, `select_model` 3 à 4 B ; contrôle AD-14 |
| 8.8 | run du split dev (P8) | Run mini-cpu sur les 19 Questions dev ; balayage de `relevance_threshold` (0,1 ; 0,3 ; 0,5) |
| 8.9 | C (1) et (4) | Export du paquet d'annotation ; kappas et instabilité par Juge au Rapport |
| 8.10 | C (2), (3), (5) | Calibration réelle des Juges Ollama sur les annotations d'Anaël |

Choix de découpage : l'item C est coupé en deux. La partie code (8.9) peut tourner sans attendre ; la partie réelle (8.10) attend l'annotation humaine.

Hors lot : L5 (`index_gb`), mesure de la RAM pendant `wl run`, test socket sous Linux, profil `gpu`, vérifications réelles des graphes (L6), découpage de `cli.py`.

## 5. Passation

- **Portée** : modérée (nouvel epic, pas de replanification).
- **Suite** : `bmad-build` sur la story 8.1, avec l'enchaînement dev-story → second-avis → reviewer ; les stories 8.1 à 8.5 peuvent s'enchaîner en run autonome.
- **Succès** : les 10 stories `done` ; run mini-cpu du split dev en `completed` ; `calibration.json` réel ; release v0.2.0.
