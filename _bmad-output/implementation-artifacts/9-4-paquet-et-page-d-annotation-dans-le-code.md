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

## Mesure de taille (objectif -50 % non atteint)

Run réel `20261018-115941-a2a512` (lecture seule), 40 Réponses (`--nombre 40 --graine 1`), exportées vers le scratchpad. Même paquet, forme ancienne reconstruite (les quatre clés répétées sur chaque ligne) contre forme courte :

| | caractères / Réponse | total |
| --- | --- | --- |
| ancien format | 6 620 | 264 819 |
| paquet court | 6 306 | 252 263 |
| gain | -4,7 % | |

Sur `anael.yaml` relu puis ré-exporté en forme courte (`exporter_depuis`, 40 Réponses, 92 lignes) : 7 657 → 6 199 caractères par Réponse (-19 %), le fichier de 306 304 à 247 972.

Cause : `context_passages` pèse 4 400 caractères par Réponse (66 à 70 %), `cited_anchors` 860 (13 %) sur la seule première ligne, et le paquet de 8.9 ne répétait déjà pas les Passages. La forme courte ne gagne que sur les clés répétées (`question`, `reference_answer`, `answer`, `cited_anchors` sur 1,3 à 2,3 lignes en plus par Réponse). Le texte `context_passages` est ce que reçoivent les Juges : on ne le raccourcit pas sans décision.

## Reports

- **Atteindre -50 %** demande une décision de conception : table de Passages partagée en tête de fichier (les Passages se répètent d'une Configuration à l'autre : 186 116 caractères pour 103 532 uniques sur le run réel, soit -33 % du fichier) et `cited_anchors` retiré du paquet (non affiché par la page, -13 %) donneraient environ -46 % ; le reste exigerait de ne montrer les Passages qu'aux Réponses qui affirment quelque chose. Non fait : change le format de §4.6 au-delà de la story.
- Les références à `scripts/page_annotation.py` et `importer_verdicts.py` restent dans `epics.md` (énoncé de la story) et dans la spec 9.3 (report vers 9.4), documents historiques.
- `--depuis` : graine par défaut 0 faute d'Expérience ; pas de lecture d'un dossier de paquets (un fichier).

## Commande de vérification

```
uv run pytest -q --tb=short tests/unit/report/test_story_9_4.py tests/unit/report/test_story_8_9.py tests/unit/runner/test_story_5_2.py tests/unit/runner/test_story_8_11.py
```
