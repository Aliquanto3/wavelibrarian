---
story: "9.4"
title: "Paquet et page d'annotation dans le code"
status: review
---

# Story 9.4 : Paquet et page d'annotation dans le code

Exigences : FR-38 ; `contracts.md` §4.6, §8. Arbitrages A7 et A10 (proposition du 2026-10-26). Leçon de la réannotation (verifications-reelles-2026-10-26-v0.2.0.md, section c) : une Réponse qui n'affirme rien est sans objet ; une Réponse fidèle à un extrait faux reste fidèle ; pas de surlignage ; pas de réponse attendue pour la fidélité ; annotation à l'aveugle.

## Réalisé

- **Paquet court** (`report/paquet.py`) : `question`, `reference_answer`, `answer`, `cited_anchors` (identifiants d'Ancrage), `reference_passages`, `context_passages` sur la première ligne de chaque Réponse seulement ; les autres lignes n'ont que `answer_id`, `criterion`, `verdict`, `note`. `anael.yaml` (ancien format) reste chargeable tel quel, non réécrit : le chargeur de la 5.1 ignore les clés de contexte, test dédié (92 verdicts).
- **Tirage stratifié** : `repartir()` (allocation proportionnelle, plus grands restes, au moins une Réponse par strate non vide si N le permet, jamais plus que la strate, déterministe), strates Configuration × Type de question, ordre des doubles mélangé par la graine (pas de biais de strate), stable à graine égale. `Paquet.repartition` (strate → retenues, disponibles) ; la CLI l'affiche (« config × type : retenues / disponibles »).
- **`--depuis`** (`exporter_depuis`, `wl annotations exporter --depuis <paquet annoté> --vers … --annotateurs … --nombre N`, sans run_id) : N lignes tirées parmi celles dont le verdict est renseigné (`yes|no|na`), stratifiées par Critère ; le nouveau paquet garde `answer_id` et Critères, verdicts et notes vides, et les données de la Réponse sur sa première ligne retenue. Graine par défaut 0 (pas d'Expérience). Refus : annotateur du même nom que la source, aucune ligne annotée, source absente, dossier déjà rempli sans `--ecraser`. `run_id` et `--depuis` sont exclusifs (code 2).
- **Page** (`report/page_annotation.py`, `wl annotations page <paquet.yaml> --vers <page.html>`) : portée depuis `scripts/page_annotation.py`. Autonome (aucune ressource externe), à l'aveugle (ni verdict ni note du paquet dans la charge), sans surlignage (fonction `hl` et `<mark>` retirés) ; réponse attendue (et « d'où elle vient ») dans les blocs `correctness` et `completeness` seulement ; bloc `faithfulness` avec la consigne stricte et les extraits reçus, sans réponse attendue ; boutons Oui / Non / Sans objet ; progression et position gardées en `localStorage` ; export `verdicts-<annotateur>.json`. Sécurité : tout champ passe par `esc()` (y compris `'`), la charge JSON échappe `<` (`<`) et U+2028/2029.
- **Importer** (`report/importer.py`, `wl annotations importer <paquet.yaml> <verdicts.json>`) : portée depuis `scripts/importer_verdicts.py`. Édition textuelle : seules les lignes `verdict:` (remplacées si le JSON en a un) et `note: ''` (remplie si le JSON a une note ; une note déjà saisie reste) changent ; le reste est conservé octet pour octet. Le résultat est relu avant écriture (même annotateur, mêmes lignes et clés hors verdict et note), sinon `ConfigError` et rien n'est écrit. `na` accepté ; verdict inconnu, JSON d'un autre annotateur ou illisible : code 2. Les clés du JSON absentes du paquet sont signalées.
- **Retrait** de `scripts/page_annotation.py` et `scripts/importer_verdicts.py`. `contracts.md` §4.6 (paquet court) et §8 (quatre lignes `wl annotations`) à jour. `lire_yaml` (alias public du lecteur de `calibration.py`) évite d'importer un nom privé.
- Tests : `tests/unit/report/test_story_9_4.py` (21 : allocation, forme courte, stratification et stabilité, `--depuis`, refus, page : hors ligne, aveugle, sans surlignage, échappement XSS, réponse de référence, import aller-retour ligne à ligne, notes, refus sans écriture, CLI) ; `test_story_8_9.py` réaligné (données de Réponse sur la première ligne seulement).

## Mesure de taille (objectif -50 % atteint après revue)

Run réel `20261018-115941-a2a512` (lecture seule), 40 Réponses (`--nombre 40 --graine 1`, Corpus relu), exportées vers le scratchpad. La forme ancienne est reconstruite à partir du même paquet (`question`, `reference_answer`, `answer`, `cited_anchors` répétés sur chaque ligne, Passages en clair sur la première).

| | caractères / Réponse | total |
| --- | --- | --- |
| ancien format | 6 633 | 265 334 |
| paquet court sans table (livraison dev) | 6 306 | 252 263 |
| paquet court avec table `passages` (revue) | 2 904 | 116 167 |
| gain sur l'ancien format | -56,2 % | |

63 Passages distincts dans la table. Le gain vient de l'étiquette `[S<n>]` sortie du texte : un même extrait reçu en `[S1]` par une Configuration et en `[S3]` par une autre est partagé (97 652 caractères de contexte uniques avec l'étiquette, 45 014 sans). Aucun Passage n'est tronqué (A7) : relu par `lire_paquet`, `context_passages` est identique, octet pour octet, aux `context_texts` des 40 Réponses du run réel.

Sur `anael.yaml` relu puis ré-exporté (`exporter_depuis`, 40 Réponses, 92 lignes) : 306 304 → 112 068 caractères (-63,4 %), Passages identiques à la source.

## Reports

- **`--part-double` non stratifié** (second avis, low) : la part doublement annotée suit l'ordre du tirage mélangé par la graine, sans quota par strate ; avec peu de Réponses doubles, une strate peut en être absente. Le kappa inter-annotateurs reste calculé sur ce qui est double. À reprendre si la recette d'Anaël le demande.
- Les références à `scripts/page_annotation.py` et `importer_verdicts.py` restent dans `epics.md` (énoncé de la story) et dans la spec 9.3 (report vers 9.4), documents historiques.
- `--depuis` : graine par défaut 0 faute d'Expérience ; pas de lecture d'un dossier de paquets (un fichier).

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/report/test_story_9_4.py tests/unit/report/test_story_8_9.py tests/unit/runner/test_story_5_2.py tests/unit/runner/test_story_8_11.py
```

## Revue

### Passe 1 (2026-10-26, SHA revu 2479490)

Branche rebasée sur `story/9-3` revue (2ed872c) : `main` ne contient pas encore 9.3.

- **Important**, medium, revue : AC 1 non atteint (-4,7 %). Corrigé : table `passages` en tête (empreinte courte de l'Ancrage et du texte, étiquette `[S<n>]` gardée sur la ligne), `lire_paquet` / `resoudre_passages` pour la page et `--depuis` (table utile recopiée, Ancrages de référence gardés), chargeur 5.1 inchangé (ignore la table) ; -56,2 % sur le run réel, sans troncature (A7). Tests `test_table_des_passages_partagee_et_sans_perte`, `test_reference_de_passage_inconnue_refusee`, `test_depuis_recopie_la_table_utile`.
- **Important**, medium, second avis 1 : verdict vidé dans la page ni retiré ni signalé. Corrigé selon l'arbitrage : conservé dans le paquet, compté (`Import.vides_conserves`) et affiché par la CLI. Test `test_import_note_nulle_et_verdict_vide`.
- **Important**, medium, revue : l'importeur gardait l'`answer_id` de l'entrée précédente quand une entrée ne commençait pas par `answer_id` (paquet réordonné à la main) : verdict reporté sur la mauvaise ligne sans erreur. Corrigé : remise à zéro à chaque `- `, et contrôle sémantique avant substitution (verdicts et notes relus égaux aux attendus, sinon code 2, rien écrit). Test `test_import_entree_sans_answer_id_en_tete_refusee`.
- **Nit**, low, second avis 2 : la charge JSON portait réponse et Passages de référence pour un item `faithfulness` seul (et les extraits pour un item sans fidélité). Corrigé (filtre par Critères de l'item). Test `test_page_sans_reference_pour_un_item_fidelite_seul`.
- **Nit**, low, second avis 3 : note `null` écrite « None », U+0085 (et U+2028/2029, C1, DEL) altérés. Corrigé (note non texte refusée, `null` vide, échappement `\uXXXX`). Tests paramétrés `test_import_notes_speciales_relues_a_l_identique`.
- **Nit**, low, second avis 4 : CRLF converti en LF, écriture non atomique. Corrigé : lecture en octets, `\r` gardé ligne à ligne, fichier voisin relu puis `os.replace` ; docstring juste. Test `test_import_garde_les_fins_de_ligne_crlf`.
- **Nit**, low, second avis 5 : `--part-double` non stratifié. Reporté (Reports).
- **Nit**, low, second avis 6 : tests manquants. Ajoutés : note avec `\` et `#`, doublon de Critère (désormais refusé par la page, comme par le chargeur 5.1), `answer_id` absent (page et `--depuis`, ce dernier levait `KeyError`).
- **Nit**, low, second avis 7 : `--depuis --ecraser` pouvait écraser sa source. Corrigé (code 2). Test `test_depuis_refuse_d_ecraser_sa_source`. Même garde pour `wl annotations page --vers <le paquet>`.
- **Nit**, low, revue : `--part-double` passé avec `--depuis` est ignoré sans message. Non corrigé (sans effet sur les données).
- **Nit**, low, revue : la progression de la page est rangée sous `wl-annot-<annotateur>` : deux paquets du même annotateur ouverts dans le même navigateur partagent leurs verdicts (les clés étrangères sortent en « absents du paquet » à l'import). Non corrigé.
- Complexité : 0 constat (table de Passages en dictionnaire, import en un passage linéaire).
