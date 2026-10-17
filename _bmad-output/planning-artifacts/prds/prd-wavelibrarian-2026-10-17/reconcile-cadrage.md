# Réconciliation cadrage / PRD : WaveLibrarian

Date : 2026-10-17. Sources comparées : `docs/cadrage.md` (source), `prd.md` et `addendum.md` (même dossier).
Périmètre : livrables 1 et 2. MVP = socle + phases 1 et 2 (FR-1 à FR-41) ; phases 3 à 8 au niveau capacité (FR-42 à FR-51). Gravité jugée surtout au regard du MVP.

## Verdict

Le PRD reprend fidèlement l'essentiel du cadrage (typologie des questions, gel, closed-book, panel multi-familles, calibration, trois postes de coût, point mort à qualité égale, cache d'index, dix architectures du niveau 1, contexte parfait). Il reste trois trous nets côté MVP : le scénario de mise à jour du corpus n'est pas défini, les coûts de possession (stockage, amortissement) et le débit sont absents, et l'axe volume (H3, H11) n'a aucune exigence. S'y ajoutent des écarts moyens sur les juges frontière, le budget multi-fournisseur, la latence dans le front de Pareto et le contenu du mini-corpus.

## Tableau de synthèse

| # | Écart | Section PRD | Gravité |
| --- | --- | --- | --- |
| E1 | Scénario de mise à jour et fraîcheur non spécifiés | FR-14, FR-28, FR-31, §4.4 | haute |
| E2 | Coûts de possession (stockage, amortissement) absents | FR-31, FR-29 | haute |
| E3 | Axe volume (H3, H11) sans exigence | FR-8, FR-41, §4.8 | haute |
| E4 | Latence absente du front de Pareto, débit absent | FR-40, FR-31 | moyenne |
| E5 | Juges frontière réservés à la calibration absents | FR-37, FR-38 | moyenne |
| E6 | Budget : deux plafonds, batch, plafond par niveau | FR-33, FR-34 | moyenne |
| E7 | Exclusion de Haiku 5.5 sur-interprétée ; CAG limité au cache fournisseur | FR-16, FR-22, §7.1 | moyenne |
| E8 | Métriques de recherche non définies pour les architectures sans passages | FR-35 | moyenne |
| E9 | Mini-corpus sans sentinelle, piège, profils de droits, ni langue seconde | FR-8, FR-13 | moyenne |
| E10 | Aucune donnée de conformité-sécurité produite au MVP | FR-14, FR-40, FR-47 | moyenne |
| E11 | Sécurité du harnais WaveStack (garde-fous, permissions d'outils) perdue | FR-26, §5 | moyenne |
| E12 | Volatilité déclarée au lieu de calculée | FR-7 | basse |
| E13 | Autres métriques FinOps manquantes (appels LLM par requête, coût par requête réussie, décomposition) | FR-29, FR-31, FR-34 | basse |
| E14 | Rôle des corpus (groupe témoin, contamination attendue) perdu | FR-5 | basse |
| E15 | Configuration de modèles de référence du niveau 1 non figée | FR-41 | basse |
| E16 | Points de contrôle de phase non repris | §8 | basse |
| E17 | Détails du test de conformité (FR-47) et H17 | FR-47, FR-51 | basse |
| E18 | Risques et parades du cadrage omis | §9 | basse |
| E19 | Budget en heures, budget de l'optimiseur | FR-33, FR-48 | basse |
| E20 | Idées qualitatives perdues | §1, §2 | basse |

## Écarts détaillés

### E1. Scénario de mise à jour du corpus : condition de référence non définie (haute)

- Cadrage, Plan d'expérience : « Trois conditions de référence encadrent les niveaux : contexte parfait (isole le générateur), routage oracle (borne haute du routage) et scénario de mise à jour du corpus (fraîcheur, coût de réindexation). » H5 : « Scénario d'ajout et de modification de documents : coût de réindexation et fraîcheur » ; « volatilité jamais testée ».
- PRD : la condition contexte parfait a son FR (FR-17) et l'oracle est en FR-43. En revanche le scénario de mise à jour n'a aucune exigence. FR-14 définit seulement l'opération « mettre à jour » dans le contrat d'architecture, FR-28 le cache d'index et FR-31 le poste de coût « mise à jour ».
- Ce qui manque : un scénario reproductible (séquence ajout, modification, suppression sur un Corpus), une mesure de fraîcheur (la Réponse reflète-t-elle la version modifiée, ignore-t-elle le document supprimé ?), une comparaison du coût de réindexation entre architectures (H2 : « mise à jour ~100× plus coûteuse », H5, H13), un type de corpus volatil. Sans cela, le poste « mise à jour » du rapport n'a aucune charge de travail qui l'alimente, et SM-3 ne le vérifie pas.
- Lien MVP : le Mini-corpus fictif a deux versions contradictoires d'un document (bon pour les questions temporelles) mais aucun scénario de mises à jour successives.
- Recommandation : ajouter un FR « Scénario de mise à jour » au bloc 4.5 ou 4.7, avec un fichier de scénario déclaratif, une métrique de fraîcheur, et l'étendre au mini-corpus.

### E2. Coûts de possession absents (haute)

- Cadrage, Métriques : « FinOps – possession : Coût d'indexation et de mise à jour, stockage, amortissement du matériel local | Traces et hypothèses explicites ». Reprise WaveStack : « À étendre au coût d'indexation et au coût par requête réussie. »
- PRD : FR-31 ne ventile que indexation, mise à jour, requête. FR-29 trace tokens, coût, latence, énergie. Aucune exigence sur le stockage (taille d'index, de graphe, de wiki) ni sur l'amortissement du matériel local (GPU de 8 Go). Un modèle local a un coût monétaire nul (FR-30) : le front qualité × coût total favorise donc mécaniquement le local.
- Pourquoi c'est grave au MVP : le MVP compare des modèles locaux (Ollama) à Haiku 5.5. Sans coût de possession explicite, la comparaison de coût est biaisée.
- Recommandation : un FR « coûts de possession » (taille de stockage par index, hypothèse d'amortissement déclarée dans la grille tarifaire, imputation par durée de GPU), avec des hypothèses explicites dans le Rapport.

### E3. Axe volume (H3, H11) sans exigence (haute)

- Cadrage, H3 (apport original du banc) : « Axe volume (100, 500, 2 000+ documents), coût de compilation, fidélité du wiki aux sources ». H11 : « Faire varier taille de corpus et taille de modèle ». Les apports originaux listés incluent H3.
- PRD : aucune exigence ne permet de faire varier le volume d'un Corpus (sous-échantillonnage reproductible à N Documents). FR-8 limite le mini-corpus à environ 20 Documents. FR-42 à FR-51 ne mentionnent ni H3 ni H11. La fidélité du wiki est en FR-25 mais pas l'axe volume.
- Recommandation : un FR (même Post-MVP) « Sous-corpus à volume contrôlé » (tirage déterministe de 100, 500, 2 000 Documents), et vérifier que le profilage, le cache d'index et l'Expérience le supportent dès le MVP. Ajouter H3 et H11 à la liste de couverture des hypothèses.

### E4. Latence absente du front de Pareto, débit absent (moyenne)

- Cadrage : « Les résultats se lisent en front de Pareto qualité × coût × latence, pas en classement unique. » Performance : « Latence p50 et p95, débit ».
- PRD : FR-40 produit « fronts de Pareto qualité × coût total et qualité × énergie » (reprise des deux fronts de la section sur les postes de coût) et la latence p50 et p95, mais la latence n'est pas un axe de Pareto et le débit n'est jamais mentionné. Le §1 du PRD ne cite pas la latence comme axe de lecture. FR-48 (optimiseur) la reprend plus tard.
- Recommandation : ajouter au moins un front qualité × coût × latence (ou qualité × latence) à FR-40 et une mesure de débit.

### E5. Juges frontière réservés à la calibration (moyenne)

- Cadrage, Juges : « Les juges les plus chers (modèles frontière) servent à calibrer les 50 questions doublement annotées ; les juges abordables jugent tout le reste. » D2 : « juge frontière réservé à la calibration ».
- PRD : FR-37 et FR-38 ne distinguent pas deux rôles de juges. Le panel est unique. L'ASSUMPTION de FR-37 (modèles locaux + Haiku 5.5) n'a pas de juge frontière.
- Conséquence : le PRD ne dit pas comment l'on mesure le plafond « juge frontière » ni comment la calibration utilise les 50 Questions doublement annotées plutôt que les 50 à 100 Réponses annotées par Anaël. Les deux jeux d'annotation du cadrage (« 50 à 100 réponses annotées par toi » et « 50 questions doublement annotées ») sont mélangés en UJ-3.
- Recommandation : préciser les deux rôles (calibration frontière, jugement de masse) et la distinction entre l'échantillon de 50 à 100 Réponses et les 50 Questions doublement annotées.

### E6. Budget : deux plafonds, API en lot, plafond par niveau (moyenne)

- Cadrage, D2 : « 50 €/mois sur Azure AI Foundry (Wavestone) et 50 $/mois sur l'API Anthropic (personnel). Conséquences : modèles serverless seulement […] API batch et cache de prompt ; génération et embeddings en local quand possible ; arrêt automatique au plafond ». Risques : « Plafond par niveau, cache des réponses, appels en lot ». Juges : Haiku 5.5 « moitié prix en batch ».
- PRD : FR-33 prévoit un plafond par Exécution et un plafond cumulé par période, sans distinction de fournisseur ni de devise (euros et dollars), sans plafond par niveau du plan d'expérience, et sans appels en lot. Le cache de réponses (FR-34) est repris. Le cache de prompt n'apparaît que dans CAG. L'API batch (moitié prix) est absente, alors qu'elle est la principale économie annoncée pour les juges.
- Recommandation : plafonds par fournisseur (et devise), plafond par niveau, et un FR sur les appels en lot pour les Juges.

### E7. Exclusion de Haiku 5.5 et CAG (moyenne)

- Cadrage : « Haiku 5.5 […] tarif multiplié par 5 au-delà de 100 000 tokens de prompt […] Haiku 5.5 est exclu des baselines contexte long et CAG. » CAG : « corpus préchargé dans le cache du modèle ».
- PRD : FR-16 refuse toute Configuration Haiku 5.5 en contexte long ou CAG, sans condition de taille (balisé `[ASSUMPTION]`, §11). La motivation (surtarif au-delà de 100 000 tokens) ne vaut que pour les gros prompts : le Mini-corpus fictif de 20 Documents est probablement bien en dessous. FR-22 définit CAG par le « cache de prompt du fournisseur » et déclare CAG inapplicable sans cache fournisseur, ce qui exclut un cache de contexte local (KV cache llama.cpp), pourtant couvert par la formule « cache du modèle ».
- Conséquence MVP : seule l'API Anthropic (Haiku 5.5) offre un cache de prompt ; si Haiku est exclu, CAG n'a aucun modèle éligible au MVP, alors qu'il est dans l'ordre de priorité du §7.1 et dans SM-3 (au moins quatre architectures, CAG optionnel). Le cadrage ne tranche pas non plus qui peut faire CAG et contexte long.
- Recommandation : conditionner l'exclusion à la taille du prompt, accepter un cache local pour CAG, et lever l'`[ASSUMPTION]` avec Anaël.

### E8. Métriques de recherche non définies pour les architectures sans passages (moyenne)

- Cadrage : « Rappel@k, MRR, nDCG sur les passages de référence » ; les passages de référence sont « ancrés sur le document et la page ou section, pas sur un chunk ».
- PRD : FR-35 définit la pertinence par recouvrement d'un Ancrage de référence. Le contrat FR-14 impose pourtant à chaque Réponse des « Passages retrouvés classés avec leurs scores ». Pour le contexte long, le CAG, la recherche agentique, le LLM Wiki et GraphRAG global, il n'existe pas de liste classée de Passages. Le PRD ne dit pas comment s'y appliquent rappel@k, MRR ou nDCG (ou s'ils sont « non applicables »), ni comment le Rapport traite ces cas dans les comparaisons.
- Recommandation : préciser la correspondance (Ancrages cités ou lus par l'agent, pages de wiki remontées à leurs Ancrages) ou marquer les métriques « non applicables ».

### E9. Mini-corpus : contenu insuffisant pour des tests ultérieurs (moyenne)

- Cadrage, Conformité : « effacement d'un document sentinelle aux faits uniques » ; « deux profils de droits » ; « documents piégés […] PoisonedRAG ». Typologie : questions interlingues, « question en français sur un corpus anglais, et inversement » ; version contrefactuelle d'un sous-corpus ; « piège de connaissance ».
- PRD : FR-8 ne demande ni document sentinelle (faits uniques), ni document piégé, ni deux profils de droits, ni documents en deux langues. Il demande une question interlingue sans dire que le corpus contient une seconde langue. Le mini-corpus étant Gelé (FR-8, FR-13), toute modification ultérieure change son empreinte et invalide les résultats. FR-5 prépare les métadonnées de sensibilité et de droits, mais aucune donnée de test ne les emploie.
- Recommandation : intégrer dès maintenant dans le mini-corpus un document sentinelle, un document piégé, deux niveaux de droits et au moins un document dans une seconde langue.

### E10. Aucune donnée de conformité-sécurité au MVP (moyenne)

- Cadrage : « Chaque architecture reçoit une fiche conformité-sécurité, au même rang que la qualité et le coût » ; localisation des données « Déclaratif par composant, tiré de la configuration » ; copies et contenu dérivé : « Inventaire automatique des stockages » ; traçabilité : « Taux de citations correctes, présence des journaux ».
- PRD : la fiche est entièrement Post-MVP (FR-47) et le Rapport MVP (FR-40) ne contient aucune rubrique de conformité. Or les données nécessaires sont bon marché à saisir dès le MVP : métadonnée de localisation par Composant dans le Registre (FR-2), déclaration des stockages créés par chaque Architecture (index, graphe, wiki), inventaire dans la Trace. Si le contrat FR-14 ne les exige pas maintenant, chaque architecture livrée au MVP devra être reprise plus tard. Le livrable 1 (« lecture conformité-sécurité ») dépend de ces métadonnées.
- Recommandation : ajouter à FR-2 et FR-14 la déclaration de localisation et de stockages, et la suppression d'un document comme opération testée sur tous les stockages d'une Architecture.

### E11. Sécurité du harnais WaveStack (moyenne)

- Cadrage, Reprise du harnais : « garde-fous en entrée et en sortie (données personnelles, injection), règle Autoriser / Demander / Refuser par outil, liste blanche réseau, journal de sécurité exportable ». Conformité : « permissions des outils de la recherche agentique ; exfiltration ».
- PRD : FR-26 garantit seulement des outils « en lecture seule et limités au Corpus ». Aucune règle par outil, aucune liste blanche réseau, aucun journal de sécurité, aucun garde-fou d'entrée ou de sortie. La recherche agentique et la CAG sont dans le MVP.
- Recommandation : au minimum, une politique d'outils déclarative pour FR-26 et un journal exportable des appels d'outils.

### E12. Volatilité déclarée au lieu de calculée (basse)

- Cadrage : « chaque corpus est décrit par des descripteurs calculés automatiquement », dont « volatilité (fréquence de mise à jour) ».
- PRD : FR-7 la déclare en métadonnée au MVP (`[ASSUMPTION]`). Choix assumé et raisonnable, mais la volatilité est un axe de la matrice de conviction et la clé de H5. À rapprocher d'E1 : le scénario de mise à jour peut fournir cette valeur.

### E13. Autres métriques FinOps manquantes (basse)

- Cadrage : « appels LLM par requête » ; « coût par requête réussie » (extension WaveStack) ; décomposition « sans optimisation / coût réel / part du cache ».
- PRD : le nombre d'appels LLM par requête n'est pas une métrique du Rapport (FR-31, FR-40) ; le coût par requête réussie est absent ; FR-34 distingue seulement coût réel et coût sans cache (pas de décomposition à trois termes, mentionnée seulement dans l'addendum).

### E14. Rôle des corpus : groupe témoin et contamination attendue (basse)

- Cadrage : « les corpus très présents dans les données d'entraînement servent de groupe témoin, pas de test principal » ; colonnes « Rôle dans le banc » et « Contamination attendue ».
- PRD : FR-5 ne porte que langue, licence, publiable. Le rôle du corpus (groupe témoin, test principal) et la contamination attendue ne sont pas des métadonnées, et le Rapport ne traite pas un corpus témoin différemment. Seul le filtre closed-book par question est repris.

### E15. Configuration de modèles de référence du niveau 1 (basse)

- Cadrage : niveau 1, « Ce qui reste fixe : une configuration de modèles de référence ».
- PRD : FR-41 énonce « un facteur à la fois » sans exiger de figer un jeu de modèles de référence pour le niveau 1 (la liste figée est en question ouverte 2 et en FR-4, au niveau de l'Expérience).

### E16. Points de contrôle des phases (basse)

- Cadrage, Phasage : phase 1 « juges calibrés, baselines reproductibles » ; phase 2 « front de Pareto par corpus, premières hypothèses tranchées ».
- PRD : les indicateurs de succès (§8) ne reprennent pas ces contrôles comme critères de sortie de phase, ni le « front de Pareto par corpus » (le Rapport est par Exécution).

### E17. Détails du test de conformité (FR-47) et H17 (basse, Post-MVP)

- Cadrage : effacement testé « dans les chunks, les entités, les rapports de communautés et les pages du wiki », avec « coût et durée de remise en conformité » et caches ; fuite entre utilisateurs avec « taux de fuite mesuré » et « contrôle d'accès déterministe avant le LLM, un filtre de sortie ne suffit pas » ; injection avec « variante universelle sur le graphe » et « nombre de requêtes touchées par document empoisonné ». Profil 3 (RAG managé) et H17.
- PRD : FR-47 est une liste d'intitulés sans ces critères. FR-51 omet le profil 3 et aucune exigence ne porte sur H17 (le cadrage la classe « extension future »). Aussi omis : l'indicateur « cadre réglementaire alimenté par ton skill d'évaluation de souveraineté ».

### E18. Risques et parades omis (basse)

- Cadrage : « Conviction biaisée par des corpus non professionnels : valider la matrice sur un corpus de mission réel avant de la diffuser » ; « Dérive de périmètre : multimodal et GenBI hors des phases 1 à 4 » ; « Obsolescence des modèles : relance périodique ».
- PRD §9 ne contient pas ces trois risques (le deuxième est partiellement couvert par FR-46 en Post-MVP). Le premier touche directement SM-1 : une branche « confirmée » sur corpus personnels ne vaut pas validation pour une mission.

### E19. Budget en heures et optimiseur (basse)

- Cadrage : « budget borné en euros et en heures » (critère de réussite du livrable 2) ; D12 « Forfaits en euros et en heures ».
- PRD : FR-33 n'a qu'un plafond en monnaie ; le budget en heures n'apparaît que dans FR-48 (Post-MVP). Acceptable pour le MVP, mais une limite de durée d'Exécution serait peu coûteuse.

### E20. Idées qualitatives perdues (basse)

- La hiérarchie des livrables : « la publication est un bonus ».
- Les apports originaux du banc (H3, H7, H12, H13, H15) comme fil directeur de l'effort : le PRD ne les distingue pas des autres hypothèses (voir aussi E3 pour H3).
- La littérature comme contrainte de conception : H1 « une fusion RRF non réglée peut faire moins bien que le dense » (repris dans FR-19 par la fusion pondérée), H14 « faux pour le filtrage » (FR-42), H15 « comparer les définitions des métriques avant leurs valeurs » (absent de FR-45).
- « Les traces contiennent les documents et les questions » : le critère de localisation des traces est absent de FR-29 (l'envoi vers un outil externe est une simple option).
- « Les corpus sont publiables selon licence » : le cadrage prévoit un corpus publiable distinct (notes MTG, contrefactuel) ; FR-5 a l'indicateur mais pas de contrôle de publication des Rapports par corpus, partiellement couvert par §5 Dépôt public.
- Mutualisation : « partager l'évaluation et la mesure d'énergie, pas le code applicatif » (D14) est dans l'addendum, pas dans une exigence.

## Contradictions éventuelles

Aucune contradiction frontale. Deux tensions à lever :
1. FR-16 (exclusion de Haiku sans condition de taille) va au-delà du cadrage (E7).
2. FR-22 (CAG limité au cache fournisseur) restreint la définition du cadrage (« cache du modèle ») et, combiné à FR-16, rend CAG impraticable au MVP (E7).

## Éléments vérifiés et couverts (pour mémoire)

- Typologie des questions complète (glossaire), suivi et interlingue en attributs (FR-9).
- Référence ancrée document + page/section (Ancrage, FR-6, FR-9, FR-11).
- Production par LLM, validation humaine, pièges écrits à la main (UJ-1, FR-10, FR-11).
- Closed-book et scores séparés (FR-12), gel et séparation développement/test (FR-13), 150 questions (FR-11), bootstrap et McNemar (FR-39).
- Critères séparés sans score global (FR-36), règle de famille (FR-3, FR-37), kappa, plafond humain et cinq passes (FR-38).
- Trois postes de coût, point mort à qualité égale, deux fronts de Pareto (FR-31, FR-40), énergie mesurée/estimée avec avertissement (FR-32), grille tarifaire datée (FR-30), plafond bloquant (FR-33).
- Niveau 0 et niveau 1 complets (FR-16 à FR-27), contexte parfait (FR-17), cache d'index (FR-28), matrice de compatibilité (FR-3), YAML déclaratif (FR-1), reproductibilité (FR-4).
- Optimiseur, bases vectorielles, couche de décision, outils d'évaluation, mode mission, MCP, profils de déploiement : présents au niveau capacité (FR-42 à FR-51).
