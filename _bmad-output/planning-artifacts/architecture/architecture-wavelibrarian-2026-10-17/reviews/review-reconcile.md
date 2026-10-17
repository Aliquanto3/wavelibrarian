# Relecture de réconciliation : architecture contre PRD, addendum et cadrage

Date : 2026-10-17. Portée : FR-1 à FR-41, FR-52 à FR-55, §5, §7.3, SM-3, SM-4, addendum, cadrage (Plan d'expérience, Architecture de l'outil, Risques et décisions).

## Verdict

La couverture structurelle est bonne : chaque FR du MVP a un lieu (module), une règle ou un schéma. Les manques se concentrent sur (a) le contenu du Rapport (FR-40, FR-31, FR-53), qui n'a aucun contrat, (b) des types ou champs référencés mais non définis, (c) les valeurs par défaut du §7.3 non reportées dans les schémas.

## Manques et contradictions

### High

1. **Rapport (FR-40/31/53) sans contrat.** Rien n'est dit sur : latence p50/p95 (et sa définition : somme des spans d'une Question, avec la latence d'origine pour les hits du cache LLM, sinon elle vaut 0 au rejeu), débit en Questions/min, coût par requête et pour 1 000 requêtes, point mort (formule indexation + mises à jour contre coût par requête ; condition de Qualité égale par McNemar ou bootstrap apparié de FR-39 ; message explicite sinon), Fraîcheur (formule sur les Questions à `scenario_target`), définition de Qualité (exactitude, abstention correcte comptée exacte), axes de Pareto (coût total, énergie, latence p95, plus un front par Critère), séparation des Questions contaminées, résultats par Palier, Panel retenu et Juges exclus, configurations inapplicables, avertissement mesuré/estimé. Correction : section `contracts.md` §7 « Rapport » (sections, formules, colonnes de `scores.csv`, `pairs.csv`, `pareto.csv`, `costs.csv`) et un AD « Métriques dérivées » dans le spine.
2. **Clé de réponse sans palier ni état.** `answer_id = <run_id>/<config_id>/<condition>/<question_id>` (contracts §1, §5) entre en collision quand `tier: all` (FR-54) exécute plusieurs paliers, et ne distingue pas avant/après Scénario de mise à jour (FR-53, Fraîcheur). Correction : ajouter `tier` et `phase` (`base|after_update`) à `Answer`, à la clé d'`answers.jsonl`, à `answer_id` et aux attributs de trace (`wl.tier`, `wl.phase`).

### Medium

3. **`CorpusProfile` jamais défini** alors que `check(profile)`, FR-7 et `corpus_profile.json` en dépendent. Ajouter à contracts §1 : nb Documents, tokens, nom du tokenizer de référence, longueur moyenne, profondeur de structure max et moyenne, densité de liens, part tabulaire, part visuelle (images par Document), langue dominante, volatilité (déclarée).
4. **Valeurs par défaut du §7.3 absentes des schémas.** Seuls `k: 5`, `stats` et `dev_ratio 0.4` apparaissent. Manquent : Corrective RAG (seuil 0,5, 2 boucles), agent (8 étapes, 0,05 $ par Question ; AD-18 cite les bornes sans valeurs), PageIndex (8 nœuds), RAPTOR (groupes 5 à 10, profondeur 3), seuil kappa 0,6 (aucun champ dans `judges` ni dans `wl calibrate`), 5 passes de calibration (commentaire seulement), 5 Questions et 120 s pour les tests réels locaux. Correction : tableau « défauts des `Params` » dans contracts §4 et champ `judges.kappa_threshold`.
5. **Fidélité du wiki (FR-25) sans rôle, sans sortie ni schéma.** `JUDGED_CRITERIA` ne vise que des Réponses. Ajouter un rôle (par exemple `wiki_fidelity`) avec son schéma, un paramètre d'échantillon de pages et un fichier de sortie (`wiki_fidelity.json`) repris par le Rapport (AD-4 impose de modifier le Faux LLM dans la même story).
6. **GraphRAG (FR-27) : rôles manquants.** La liste fermée `LLMRole` n'a ni rapport de communauté ni recherche globale (map/reduce). Ajouter `community_report` et `global_map` (ou imposer `summarize` avec des schémas distincts) et fixer les noms d'étapes.
7. **Réutilisation explicite d'index (FR-3) sans champ.** AD-13 contrôle « la dimension d'un index réutilisé » mais le schéma d'Expérience n'a aucune clé pour désigner un index existant. Ajouter `configurations[].reuse_index: <index_key> | null`.
8. **CLI sans arguments ni lien aux FR.** Le spine liste `corpus, questions, run, calibrate, report, registry, install` ; le PRD parle de `calibrer`, `rapport`, `registre` (langue des noms à trancher). Manquent : profilage, génération avec répartition cible par Type (FR-10 : aucun paramètre de répartition dans `questions.yaml` ni pour `question_gen`), contrôle de validation (statuts, Types, écart à 150), closed-book, gel (`--dev-ratio`), application d'un Scénario, export du front (FR-41), `--resume`, `--split`, aide intégrée. Correction : contracts §8 « Commandes `wl` ».
9. **Règle de famille plus stricte que le PRD.** FR-3/FR-37 : un Juge n'est exclu que si sa Famille est celle du Generator évalué. AD-14 exclut toute Famille de tous les modèles de la Configuration (rewriter, decider, résumés, compilation), ce qui peut descendre sous 2 Juges et refuser des Configurations admises par le PRD. À arbitrer (aligner sur le Generator seul, ou amender le PRD). La règle du Filtre closed-book (Juge d'une Famille autre que le modèle testé, correspondance exacte normalisée, exclusion des Questions `unanswerable`, FR-12) est liée à AD-14 mais non énoncée.

### Low

10. **Divers à reporter.**
   - FR-28 : la Trace doit indiquer « cache » pour un hit du Cache d'index ; ajouter `wl.index_cache_hit` (bool) à contracts §6.
   - FR-54 : la règle « les Documents des Ancrages de référence figurent dans tous les Paliers » n'est écrite nulle part ; `corpus/tiers.py` est sous `evalset` dans les couches et ne peut pas lire les Questions : passer un ensemble `must_include` en argument.
   - FR-37 : l'égalité « Question signalée » n'a pas de champ (`tie_flagged` dans `verdicts.jsonl`). Le rôle « juge de calibration » n'a pas de comportement décrit.
   - FR-52 : le PRD dit que le marqueur de rôle est placé « par le Composant appelant », AD-4 dit « par la passerelle, jamais un Composant ». Intentionnel, à aligner dans le PRD.
   - FR-5 : l'ignorance d'un format non pris en charge sans arrêt de l'ingestion n'est pas écrite. Deux fichiers identiques à chemins différents donnent le même `doc_id` et des `anchor_id` en collision : préciser (déduplication ou erreur).
   - FR-8 : borne de 60 000 tokens du Corpus de base et éléments listés non repris dans un test de fixture.
   - FR-22 : « seconde Question avec tokens en cache non nuls » absent de la liste de conformité d'AD-16.
   - FR-20 : option « moyenne avec le vecteur de la Question » absente des Params HyDE (`average_with_question`).
   - FR-19 : noms des fusions (`rrf`, `weighted`, poids) et rerankers non fixés ; aucun reranker au Catalogue du MVP.
   - FR-55 / §7.3 : les modèles du profil GPU (qwen3.5:4b, ministral-3:8b, bge-m3) ne figurent qu'en commentaire dans `models.yaml` ; ils doivent y être, sinon refus par le Catalogue.
   - SM-4 : « coût tracé = coût recalculé au centime près » doit être un test `tests/real` explicite (recalcul indépendant à partir des tokens et de la grille).
   - SM-3 : ajouter un test e2e vérifiant que `mini-test.yaml` couvre les Baselines et au moins 4 Architectures du niveau 1, avec un Rapport contenant toutes les sections de l'item 1.
   - FR-13 : « le Rapport indique la partie utilisée » ; écrire le champ dans `manifest.json`.
   - Addendum : Docling (PDF) est en extra alors que le MVP utilise `pypdfium2` ; consigner la décision. D14 (mutualisation harnais et énergie) non citée. La décomposition FinOps « sans optimisation / coût réel / part du cache » est couverte par `cost_uncached` mais pas nommée. Cadrage « plafond par niveau » (Question ouverte 5) : pas de champ, à différer explicitement. LiteLLM, API batch, base vectorielle embarquée : différés ou tranchés (numpy_exact) de façon cohérente.

## Éléments vérifiés et couverts

FR-1, FR-2, FR-4, FR-6, FR-9 (champs complets), FR-11 (hors CLI), FR-12 (hors règle de famille), FR-14 à FR-18, FR-21 à FR-24, FR-26, FR-29, FR-30 (batch et cache déclarés), FR-32 (étiquettes mesuré/estimé), FR-33 (x1,2 + max_tokens, registre persistant, reprise, code de sortie 3), FR-34, FR-35 (méthode par `retrieval_method`), FR-36, FR-38 (kappa, instabilité, exclusion), FR-39 (défauts), FR-41, FR-52 (hors marqueur), FR-53 (conformité de suppression), FR-55, §5 (tests sans réseau, secrets, dépôt public, portabilité, robustesse, reprise), §7.3 (profils CPU et GPU, Panel, plafond 5 $), RAPTOR niveau exposé (`Passage.level`).
