# Cadrage — WaveLibrarian, banc de comparaison de recherche documentaire IA

Oct 17, 2026 · @Anaël Yahi

## Objectifs et livrables

WaveLibrarian livre une conviction mesurée, un outil de mission et une plateforme pédagogique ; la publication est un bonus.

| Livrable | Contenu | Critère de réussite |
| --- | --- | --- |
| 1. Conviction | Matrice « profil de corpus × type de question → architecture et modèles recommandés », avec qualité, coût, empreinte environnementale et lecture conformité-sécurité ; refonte des slides de conviction à partir des résultats | Chaque branche de l'arbre de décision confirmée ou corrigée par des mesures |
| 2. Outil de mission | Profilage d'un corpus client, génération du jeu d'évaluation, recherche optimisée de la configuration (parcours exhaustif en option), rapport comparatif avec une fiche conformité-sécurité par architecture, lisible par une direction de DSI | Configuration très fonctionnelle trouvée sous un budget borné en euros et en heures |
| 3. Plateforme pédagogique | Interface no code pour assembler une architecture, ajouter ou retirer un composant, observer chaque étape et apprendre à évaluer modèles et architectures, dans l'esprit de WaveStack | Utilisable en formation sans écrire de code |
| 4. Publication (optionnelle) | Protocole reproductible et résultats sur corpus diffusables | Code et corpus publiables sans contrainte de droits |

## Hypothèses à tester

Revue de la littérature au 17 octobre 2026 sur dix-sept hypothèses : 2 soutenues, 11 partiellement, 1 contredite dans sa forme forte, 3 non étudiées. Les apports originaux du banc sont H3 (effet du volume), H7 (modèle de décision sur un pipeline complet), H12 (effacement dans le contenu dérivé), H13 (énergie d'indexation) et H15 (comparaison directe des outils d'évaluation).

| ID | Hypothèse | État de la littérature | Ce que le banc doit tester |
| --- | --- | --- | --- |
| H1 | Le RAG hybride (BM25 + dense + reranker) domine le dense seul, à coût proche | Partiellement soutenue : l'hybride avec reranker gagne nettement (rappel@5 de 0,59 à 0,82, [arXiv 2604.01733](https://arxiv.org/html/2604.01733)), mais une fusion RRF non réglée peut faire moins bien que le dense ([arXiv 2609.22770](https://arxiv.org/abs/2609.22770)) | Séparer dense, BM25, RRF, fusion réglée et reranker ; mesurer la latence du reranker |
| H2 | GraphRAG ne gagne qu'en global et multi-sauts, rentable seulement sur corpus stable | Soutenue : perd sur les faits simples, gagne en raisonnement complexe, prompt global de \~331 000 tokens contre \~880 ([GraphRAG-Bench](https://arxiv.org/html/2506.05690v3)) ; hallucine sur les questions sans réponse ([arXiv 2502.11371](https://arxiv.org/html/2502.11371v2)) ; mise à jour \~100× plus coûteuse ([EraRAG](https://arxiv.org/pdf/2506.20963v1.pdf)) | Ventiler par type de question ; coût d'indexation et de mise à jour ; inclure LazyGraphRAG et LightRAG |
| H3 | LLM Wiki égale le RAG sur quelques centaines de documents, puis décroche | Non étudiée sur le volume : une étude sur 24 articles et 13 questions, wiki meilleur en synthèse, RAG en ancrage, \~21× plus de tokens ([arXiv 2605.18490](https://arxiv.org/html/2605.18490v1)) | Axe volume (100, 500, 2 000+ documents), coût de compilation, fidélité du wiki aux sources |
| H4 | PageIndex gagne sur documents longs et structurés, à coût LLM supérieur | Partiellement soutenue, surtout par l'éditeur ([PageIndex](https://github.com/VectifyAI/PageIndex)) ; une étude indépendante sur 50 questions, latence \~1,7× ([arXiv 2604.14222](https://arxiv.org/html/2604.14222v1)) | Comparaison indépendante ; documents peu structurés comme cas défavorable |
| H5 | La recherche agentique égale le RAG mais coûte plus ; elle gagne sur corpus volatil | Partiellement soutenue : 3,3× plus de tokens ([arXiv 2601.07711](https://arxiv.org/html/2601.07711v2)), jusqu'à 107 s par requête ([arXiv 2610.05750](https://arxiv.org/pdf/2610.05750)) ; avantage sur petit corpus qui s'efface vers 100 à 1 000 documents ([LlamaIndex](https://www.llamaindex.ai/blog/did-filesystem-tools-kill-vector-search)) ; volatilité jamais testée | Scénario d'ajout et de modification de documents : coût de réindexation et fraîcheur |
| H6 | Le routage par requête bat le meilleur choix figé par corpus | Partiellement soutenue : gain modeste, loin de l'oracle (43,7 contre 39,3 figé et 60,8 oracle, [RAGRouter-Bench](https://arxiv.org/html/2602.00296v2)) ; le gain porte surtout sur le coût ([Adaptive-RAG](https://arxiv.org/pdf/2403.14403)) | Trois bornes : figé, routeur, oracle ; coût autant qu'exactitude |
| H7 | Un modèle de décision remplace les juges LLM intermédiaires sans perte de qualité | Non démontrée : exactitude proche d'un LLM en vérification d'affirmations, mais 23 % d'affirmations non étayées acceptées contre 13 % ([Towards AI](https://pub.towardsai.net/jev-as-a-judge-for-rag-claim-verification-7b356619814c)) ; aucune étude sur un pipeline complet ; jev-corrective-rag mesure sa latence sur un simulacre d'API | Taux de faux passages par étape ; cascade vers un LLM sous un seuil de confiance |
| H8 | Le format d'entrée compte peu une fois converti en Markdown | Partiellement soutenue : parser et découpage dominent sur le texte, mais forte interaction parser × format sur graphiques et images ([arXiv 2508.15817](https://arxiv.org/html/2508.15817v1)) ; l'OCR coûte \~11 points de retrieval ([arXiv 2412.02592](https://arxiv.org/pdf/2412.02592)) | Croiser format × parser × type d'élément (texte, tableau, graphique, image) ; parsers candidats dont MinerU (parser de RAG-Anything) |
| H9 | Le format des données dans le prompt change surtout le nombre de tokens | Contredite dans sa forme forte : exactitude de 41 % à 61 % selon le format sur un même modèle ([Improving Agents](https://www.improvingagents.com/blog/best-input-data-format-for-llms)) ; TOON dégrade l'appel d'outils, jusqu'à 36 points pour Mistral ([arXiv 2605.29676](https://arxiv.org/html/2605.29676v2)) | Plusieurs modèles dont un SLM ; données plates et imbriquées |
| H10 | Un SLM local suffit si le retrieval est bon ; l'écart vient de la synthèse | Partiellement soutenue : écart concentré sur raisonnement et intégration, mais réel même avec contexte parfait ([LIT-RAGBench](https://arxiv.org/html/2603.06198v1), [MultiHop-RAG](https://arxiv.org/html/2401.15391)) | Condition « contexte parfait » ; ventilation par type de question |
| H11 | Le contexte long est une baseline difficile à battre sur petit corpus | Soutenue avec un modèle fort (+13 % avec GPT-4o, [arXiv 2407.16833](https://arxiv.org/html/2407.16833v1)) ; le RAG repasse devant vers 128 000 tokens et avec les petits modèles ([LaRA](https://arxiv.org/html/2502.09977v1)) | Faire varier taille de corpus et taille de modèle ; questions sans réponse |
| H12 | GraphRAG et LLM Wiki compliquent l'effacement, le respect des droits et élargissent la surface d'attaque | Partiellement soutenue : attaques très documentées, un empoisonnement de moins de 0,05 % du corpus fait chuter l'exactitude de GraphRAG de 95 % à 50 % ([arXiv 2508.04276](https://arxiv.org/abs/2508.04276)) ; seul un contrôle d'accès déterministe empêche les fuites ([Microsoft Research](https://www.microsoft.com/en-us/research/publication/enterprise-ai-must-enforce-participant-aware-access-control)) ; effacement dans le contenu dérivé jamais étudié | Document sentinelle effacé puis recherché partout ; deux profils de droits ; protocole PoisonedRAG |
| H13 | GraphRAG et LLM Wiki coûtent plus à l'indexation, à la mise à jour et, pour GraphRAG, à la requête : seul un gain de qualité peut les justifier | Partiellement soutenue sur le coût (requête GraphRAG globale \~377× un RAG vectoriel, [GraphRAG-Bench](https://arxiv.org/html/2506.05690v3)) ; énergie d'indexation et amortissement non étudiés | Trois postes séparés (indexation, mises à jour, requête) en kWh et en euros ; point mort calculé seulement à qualité égale |
| H14 | Le choix de la base vectorielle change surtout latence, mémoire et coût, peu la qualité, tant que le rappel de l'index reste proche de l'exact | Partiellement soutenue : un rappel ANN de 0,7 coûte peu en qualité de réponse, mais davantage en citations ([arXiv 2411.07396](https://arxiv.org/html/2411.07396v1)) ; faux pour le filtrage, qui dégrade le rappel à toute échelle ([arXiv 2507.21989](https://arxiv.org/html/2507.21989v1)) ; les suppressions répétées rendent \~3 % des points inatteignables en HNSW ([arXiv 2407.07871](https://arxiv.org/html/2407.07871v1)) | Sous-plan bases vectorielles (section Plan d'expérience) |
| H15 | Les métriques des outils d'évaluation divergent entre elles et des jugements humains | Partiellement soutenue : classements de systèmes différents selon l'outil ([ARES](https://arxiv.org/pdf/2311.09476)), ordre Ragas / TruLens inversé selon le jeu de données ([RAGBench](https://arxiv.org/abs/2407.11005)), même nom de métrique pour des mesures différentes ([GroUSE](https://arxiv.org/abs/2409.06595)) ; aucune comparaison directe avec kappa | Outil × juge × configuration ; inversions de classement ; référence humaine doublement annotée |
| H16 | Une recherche optimisée trouve une configuration proche de l'optimum de la grille complète pour une fraction du coût | Partiellement soutenue : l'optimisation bayésienne atteint une exactitude comparable à la grille avec jusqu'à 84 % de temps en moins (EACL 2026) et un meilleur front de Pareto qualité, coût, latence que les méthodes de base (arXiv 2502.18635) ; les configurations optimales se transposent mal d'une tâche à l'autre | Comparer l'optimiseur à la grille complète sur les corpus du banc : écart de qualité, coût et durée économisés |
| H17 | Un RAG managé d'hyperscaler approche la qualité d'un pipeline sur mesure bien réglé, pour un effort de mise en œuvre bien plus faible | Non étudiée de façon indépendante : seules des annonces d'éditeurs (Microsoft annonce +36 % de pertinence avec la recherche agentique de Foundry IQ, sans référence publiée) | Extension future : profil 3 contre meilleure configuration sur mesure, à corpus et jeu de questions identiques |

## Corpus et profilage

Chaque corpus a un rôle précis ; les corpus très présents dans les données d'entraînement servent de groupe témoin, pas de test principal.

| Corpus | Profil | Rôle dans le banc | Contamination attendue | Publiable |
| --- | --- | --- | --- | --- |
| Règles et scénarios CO Fantasy 1 et 2 (PDF) | Longs, très structurés, tableaux | Fidélité au contexte face à D&D, PageIndex, parsing PDF | Faible sur le détail, forte interférence D&D | Non (droits) |
| Notes MTG personnelles (Drive) | Centaines de pages rédigées par toi | Corpus vierge, questions de synthèse | Très faible | Oui, si tu l'acceptes |
| Veille IA des dernières semaines | Volatil, multi-sources, HTML | Fraîcheur, recherche agentique | Nulle sur les faits récents | Liens seulement |
| Wikis de jeux et BD (Palworld, LoL, Kingdom Hearts, Alix, Blake et Mortimer, Picsou, Rahan, Thorgal) | Encyclopédique, très lié | GraphRAG, multi-sauts, témoin de contamination | Forte | Selon licence du wiki |
| Version contrefactuelle d'un sous-corpus | Faits volontairement modifiés | Mesure stricte de l'ancrage | Nulle par construction | Oui |
| Données structurées (tables de jeu, bases de cartes) | Tabulaire | GenBI | Variable | Selon source |
| Schémas d'architecture | Images | Multimodal | Faible | Selon source |

Pour que l'outil serve en mission, chaque corpus est décrit par des descripteurs calculés automatiquement. Ce sont les axes de la matrice de conviction :

- volume (documents, tokens) et longueur moyenne ;
- profondeur de structure (hiérarchie, table des matières) ;
- densité de liens entre documents (entités partagées) ;
- volatilité (fréquence de mise à jour) ;
- part de données tabulaires et de contenu visuel ;
- langue.

## Jeu d'évaluation

Le jeu d'évaluation est construit et gelé avant tout pipeline : c'est le vrai goulot du projet.

**Typologie de questions**, à répartir dans chaque corpus :

- factuelle sur un seul document ;
- multi-sauts (plusieurs documents) ;
- globale ou de synthèse ;
- comparaison ;
- agrégation numérique (GenBI) ;
- temporelle, avec documents périmés ou versions contradictoires ;
- sans réponse dans le corpus (abstention attendue) ;
- piège de connaissance (règle CO différente de D&D, fait contrefactuel) ;
- visuelle (lecture d'un schéma).

S'y ajoutent des questions de suivi en conversation, qui dépendent des échanges précédents, et des questions interlingues : question en français sur un corpus anglais, et inversement.

**Référence (gold)** : une réponse attendue et ses passages sources. Les passages sont ancrés sur le document et la page ou section, pas sur un chunk : sinon le rappel dépend du découpage testé.

**Production** : questions générées par un LLM fort à partir des documents, puis validées ou corrigées par toi. Les pièges et les questions de synthèse sont rédigés à la main.

**Filtre closed-book** : chaque question passe par deux ou trois LLM sans contexte. Une question réussie sans contexte est marquée « contaminée » ; ses scores sont rapportés à part.

**Taille et statistique** : ordre de grandeur de 100 à 200 questions par corpus. Comparaisons appariées (bootstrap, McNemar) et intervalles de confiance dans chaque rapport.

**Séparation** : une partie « développement » sert au réglage ; une partie « test » n'est utilisée que pour les résultats finaux, pour éviter de surajuster les configurations.

## Métriques et juges

Les résultats se lisent en front de Pareto qualité × coût × latence, pas en classement unique.

| Famille | Métriques | Mesure |
| --- | --- | --- |
| Recherche | Rappel@k, MRR, nDCG sur les passages de référence | Automatique |
| Réponse | Exactitude, complétude, fidélité aux sources, citations correctes, abstention correcte | Juges LLM, correspondance exacte quand possible |
| FinOps – inférence | Tokens en entrée, en sortie et en cache ; coût par requête et pour 1 000 requêtes ; appels LLM par requête | Traces et grille tarifaire datée |
| FinOps – possession | Coût d'indexation et de mise à jour, stockage, amortissement du matériel local | Traces et hypothèses explicites |
| Performance | Latence p50 et p95, débit | Traces |
| GreenOps | Énergie par requête et par indexation, équivalent CO2 selon le mix électrique | Mesurée en local (CodeCarbon, méthode du banc SLM), estimée pour les API (EcoLogits) |

Coûts et énergie sont mesurés sur trois postes séparés : indexation initiale, mises à jour (ajout, modification, suppression) et requête, avec les passes de maintenance du LLM Wiki comptées comme coût récurrent. Un point mort sur un volume de requêtes n'est calculé qu'à qualité égale ou supérieure ; s'il n'existe pas, le rapport le dit. Deux fronts de Pareto sont produits : qualité × coût total et qualité × énergie.

**Juges** : un panel de deux ou trois juges de familles différentes, choisis pour leur coût : DeepSeek-V4-Flash ou Kimi K2.6 sur [Azure AI Foundry](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure), Claude Haiku 5.5 sur l'API Anthropic ([0,10 $ et 0,50 $ par million de tokens](https://www.eesel.ai/blog/claude-haiku-5-5-pricing), moitié prix en batch, tarif multiplié par 5 au-delà de 100 000 tokens de prompt). Les juges les plus chers (modèles frontière) servent à calibrer les 50 questions doublement annotées ; les juges abordables jugent tout le reste. Haiku 5.5 est exclu des baselines contexte long et CAG. Chaque critère est noté séparément, sans score global. Un juge ne note jamais les réponses d'un modèle de sa propre famille : pas de Haiku pour juger Claude, pas de Qwen pour juger Qwen.

**Calibration** : 50 à 100 réponses annotées par toi. On mesure l'accord juge-humain (kappa) et on écarte un juge sous le seuil retenu. Une partie des réponses est annotée par une deuxième personne pour connaître le plafond d'accord humain, et chaque juge passe au moins cinq fois pour mesurer le taux de verdicts instables.

### Outils d'évaluation et d'observabilité

Les outils de traces (Langfuse, Phoenix…) et d'évaluation (Ragas, DeepEval…) sont eux-mêmes des composants comparés. Le banc calcule ses métriques de référence en interne, calibrées sur tes annotations ; chaque outil est branché par un adaptateur et jugé sur son accord avec cette référence.

Critères de comparaison :

- accord des métriques avec les annotations humaines, et stabilité selon le LLM juge ;
- couverture : traces, coûts, énergie, jeux de données, comparaison d'expériences ;
- licence, auto-hébergement et localisation des traces (les traces contiennent les documents et les questions) ;
- compatibilité OpenTelemetry, pour changer d'outil sans réinstrumenter ;
- surcoût de latence et coût d'exploitation.

| Outil | Rôle | Licence | Auto-hébergement | OpenTelemetry | Point notable 2025-2026 |
| --- | --- | --- | --- | --- | --- |
| [Langfuse](https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability) | Traces et évaluation | MIT (cœur) + modules entreprise | Oui | Oui | Racheté par ClickHouse en janvier 2026, cœur resté en MIT |
| [Arize Phoenix](https://github.com/Arize-ai/phoenix) | Traces et évaluation | Elastic 2.0, non open source au sens OSI | Oui | Oui (OpenInference) | — |
| [MLflow Tracing](https://mlflow.org/docs/latest/genai/tracing/) | Traces et évaluation | Open source (Linux Foundation) | Oui | Oui | Ingestion des conventions GenAI |
| [Opik (Comet)](https://github.com/comet-ml/opik) | Traces et évaluation | Apache 2.0 | Oui | Oui | Intégration de Ragas |
| [OpenLIT](https://github.com/openlit/openlit) | Traces et évaluation | Apache 2.0 | Oui | Oui | — |
| [TruLens](https://github.com/truera/trulens) | Traces et évaluation | MIT | Oui | Oui | — |
| [LangSmith](https://www.langchain.com/pricing) | Traces et évaluation | Propriétaire | Offre Enterprise seulement | Partiel | Comparateur propriétaire de référence |
| [Helicone](https://helicone.ai/blog/joining-mintlify) | Traces | Apache 2.0 | Oui | Partiel | En maintenance depuis mars 2026 : à écarter |
| [Ragas](https://github.com/explodinggradients/ragas) | Évaluation | Apache 2.0 | — | — | — |
| [DeepEval](https://github.com/confident-ai/deepeval) | Évaluation | Apache 2.0 | — | Non | Lié au cloud Confident AI |
| [RAGChecker](https://arxiv.org/pdf/2408.08067) | Évaluation | Open source (Amazon) | — | — | Meilleur accord humain publié que Ragas |
| [ARES](https://github.com/stanford-futuredata/ARES) | Évaluation | Apache 2.0 | — | — | Intervalles de confiance ; activité récente incertaine |
| [promptfoo](https://github.com/promptfoo/promptfoo) | Évaluation | MIT | Oui | — | Racheté par OpenAI en mars 2026 |
| [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) | Évaluation | MIT | Oui | — | Pas de métriques RAG natives |

Protocole : croiser outil × LLM juge × configuration, mesurer les inversions de classement entre outils (tau de Kendall) et comparer les définitions des métriques avant leurs valeurs : la « fidélité » de Ragas et celle de DeepEval ne mesurent pas la même chose. Pour les outils de traces : surcoût de latence face à une exécution non instrumentée, spans perdus, fidélité de l'export OpenTelemetry, ressources en auto-hébergement, risque de pérennité.

## Conformité et sécurité

Chaque architecture reçoit une fiche conformité-sécurité, au même rang que la qualité et le coût ; elle sert de support face à une direction de DSI ou un RSSI.

| Critère | Ce qui est évalué | Comment |
| --- | --- | --- |
| Localisation des données | Où transitent documents, index et prompts : local, cloud UE, SecNumCloud, hors UE ; exposition extraterritoriale | Déclaratif par composant, tiré de la configuration |
| Copies et contenu dérivé | Nombre et nature des copies : index vectoriel, graphe, wiki (contenu synthétisé à protéger comme la source) | Inventaire automatique des stockages |
| Droit à l'effacement | Un document supprimé disparaît-il de l'index, du graphe, du wiki et des caches ? | Test : effacement d'un document sentinelle aux faits uniques, puis recherche de ces faits dans les chunks, les entités, les rapports de communautés et les pages du wiki ; coût et durée de remise en conformité |
| Droits d'accès | Respect des droits documentaires source au moment de la recherche ; fuite entre utilisateurs via un contenu synthétisé | Test avec deux profils de droits, taux de fuite mesuré ; contrôle d'accès déterministe avant le LLM, un filtre de sortie ne suffit pas |
| Injection et outils | Injection indirecte via un document piégé ; permissions des outils de la recherche agentique ; exfiltration | Documents piégés ajoutés au corpus de test (protocole PoisonedRAG, plus une variante universelle sur le graphe) ; nombre de requêtes touchées par document empoisonné |
| Traçabilité | Citations vérifiables, journal des requêtes et des sources, reproductibilité | Taux de citations correctes, présence des journaux |
| Cadre réglementaire | RGPD, AI Act selon l'usage, DORA ou NIS2 selon le secteur, dépendance fournisseur | Grille qualitative, alimentée par ton skill d'évaluation de souveraineté |

Les architectures à contenu dérivé (GraphRAG, LLM Wiki) méritent une attention particulière : la synthèse peut mélanger des sources de niveaux de droits différents et compliquer l'effacement.

**Reprise du harnais WaveStack** ([dépôt](https://github.com/Aliquanto3/agentic-harness-training-demo))

- **FinOps** : prix déclarés et datés par modèle, plafond de dépense par séance, décomposition « sans optimisation / coût réel / part du cache ». À étendre au coût d'indexation et au coût par requête réussie.
- **GreenOps** : EcoLogits pour le cloud et CodeCarbon en local, avec l'avertissement que les deux périmètres ne se comparent pas terme à terme. À compléter par l'embedding, le reranking et le GPU, non comptés dans le harnais.
- **Sécurité** : garde-fous en entrée et en sortie (données personnelles, injection), règle Autoriser / Demander / Refuser par outil, liste blanche réseau, journal de sécurité exportable. La grille « limites du harnais et ce qu'il faudrait en production » sert de modèle à la fiche DSI.
- **À ajouter au banc** : contrôle d'accès documentaire, RGPD et AI Act, mesure de la fidélité aux sources.

## Plan d'expérience

On ne parcourt pas la grille complète : chaque niveau ne garde que le front de Pareto du précédent, et on fait varier un seul facteur à la fois.

| Niveau | Ce qui varie | Ce qui reste fixe |
| --- | --- | --- |
| 0. Baselines | Sans contexte, contexte long (si le corpus tient), BM25 seul | Un LLM de référence |
| 1. Architectures | RAG naïf, hybride, HyDE, GraphRAG et variantes, PageIndex, RAPTOR (arbre de résumés), LLM Wiki, recherche agentique, Corrective RAG, CAG (corpus préchargé dans le cache du modèle) | Une configuration de modèles de référence |
| 2. Composants | Compréhension de la requête (réécriture, décomposition, questions de suivi), découpage (fixe, sémantique, contextual retrieval, parent-enfant, late chunking), embeddings (dont multilingues), base vectorielle et paramètres d'index, retriever (dont multi-vecteurs type ColBERT), reranker (dont Cohere Rerank v4 sur Azure), ingénierie du contexte (compression, ordre des passages, budget de tokens), LLM générateur (SLM local ou cloud) | Les 2 ou 3 meilleures architectures par profil |
| 3. Couche de décision | Routeur d'architecture par requête, filtre de passages, reranker, contrôle d'ancrage : Jev (API) et Microsoft-Decision-1 (Azure AI Foundry) contre options locales (Strands Decider 2B, AnyJev) | Meilleures configurations du niveau 2 |
| 4. Formats | Même contenu en TXT, Word, Excel, PowerPoint, JSON, Markdown, HTML, CSV, YAML ; parser fixe, puis Docling contre VLM | Meilleure configuration texte |
| 5. Extensions | GenBI, schémas d'architecture (dont recherche visuelle sans OCR : ColPali, ColQwen ; graphe multimodal : RAG-Anything, bâti sur LightRAG), puis audio et vidéo | Socle des niveaux 1 à 4 |

Les bases vectorielles (par exemple sqlite-vec, pgvector, Qdrant, LanceDB, Milvus, et LEANN, qui recalcule les embeddings à la requête au lieu de les stocker : stockage contre latence et énergie par requête, suppression à vérifier) et les bases de graphes ont leur propre sous-plan. La référence est une recherche exacte par force brute. On y fait varier le rappel de l'index (0,7, 0,9, 0,95, 1), la quantification (float32, int8, binaire, avec et sans recalcul des scores, sur deux modèles d'embedding) et la sélectivité du filtrage (50 % à 0,1 %, en comptant les requêtes qui renvoient moins de k résultats), sur 100 000 puis plus d'un million de chunks. Des cycles de suppression et réinsertion vérifient qu'aucun document supprimé ne remonte. Aucun chiffre d'éditeur n'est repris sans avoir été reproduit. On y mesure le rappel face à la recherche exacte, la latence, la mémoire, le coût d'indexation et la suppression effective d'un document. La base retenue est ensuite fixée pour les autres niveaux. Trois conditions de référence encadrent les niveaux : contexte parfait (isole le générateur), routage oracle (borne haute du routage) et scénario de mise à jour du corpus (fraîcheur, coût de réindexation). La liste des modèles est figée et datée au lancement de chaque niveau : l'état de l'art bouge plus vite que le banc.

## Recherche de configuration en mission

En mission, l'outil ne parcourt pas toutes les combinaisons : il cherche une configuration très fonctionnelle sous un budget fixé en euros et en heures. Le parcours exhaustif reste une option sur demande du client.

Le recuit simulé fonctionne, mais il est mal adapté ici. Chaque évaluation coûte cher, son score est bruité par les juges LLM, et l'espace mêle choix discrets (architecture, modèles) et réglages continus. L'état de l'art combine quatre leviers :

1. **Optimisation bayésienne** : un modèle de substitution désigne la prochaine configuration à évaluer. Elle atteint une exactitude comparable à la grille avec jusqu'à 84 % de temps en moins ([EACL 2026](https://preview.aclanthology.org/credits/2026.eacl-industry.19)). En multi-objectif, elle produit directement un front de Pareto qualité × coût × latence ([arXiv 2502.18635](https://arxiv.org/abs/2502.18635)).
2. **Multi-fidélité** : chaque configuration est d'abord jugée sur un petit échantillon de questions ; seules les meilleures passent sur le jeu complet (successive halving, Hyperband).
3. **Démarrage à chaud** : la matrice de conviction propose les premières configurations selon le profil du corpus, ce qui relie le livrable 1 au livrable 2.
4. **Ordre tenant compte du cache** : les configurations qui partagent un index sont évaluées ensemble, l'indexation étant le poste le plus coûteux.

Optuna (open source) couvre ces leviers : optimisation bayésienne TPE, multi-objectif NSGA-II, élagage multi-fidélité. L'arrêt intervient quand le front de Pareto ne progresse plus ou que le budget est atteint. Le banc valide la méthode elle-même : la configuration trouvée est comparée à l'optimum de la grille complète (H16).

## Cibles de déploiement

Le même code tourne sur cinq profils de déploiement ; le profil devient un facteur mesuré du banc (qualité, coût, latence, énergie, conformité) et un choix argumenté en mission.

| Profil | Exemples | Ce qu'on y teste | Points d'attention |
| --- | --- | --- | --- |
| 1. Local, en périphérie | PC portable, CPU ou petit GPU | SLM, embeddings et index locaux | Mémoire limitée ; énergie mesurée, pas estimée |
| 2. Hyperscaler, composants assemblés | AWS (Bedrock, OpenSearch, Aurora pgvector), Azure (AI Foundry, AI Search), GCP (Vertex AI, AlloyDB pgvector) | Modèles frontière, pipelines sur mesure | Exposition extraterritoriale ; quotas ; certains services managés facturent une capacité minimale même au repos |
| 3. Hyperscaler, RAG managé clé en main | [Bedrock Managed Knowledge Base et son Agentic Retriever](https://businesstechnavigator.com/news/amazon-bedrock-agentic-retriever-knowledge-base-2026) (juin 2026), [Foundry IQ dans Azure AI Search](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/-/4470720), [Vertex AI RAG Engine](https://cloud.google.com/blog/products/ai-machine-learning/introducing-vertex-ai-rag-engine) | Extension future, hors priorité : le projet teste d'abord les composants | Composants peu interchangeables, traces partielles, dépendance au fournisseur |
| 4. IaaS d'un fournisseur souverain | S3NS PREMI3NS, qualifié en décembre 2025 ([Next](https://next.ink/260765/secnumcloud-bleu-vise-desormais-une-qualification-pour-la-fin-dannee/)) ; OVHcloud, Outscale ; Scaleway en cours d'évaluation en avril 2026 ([IT-Connect](https://www.it-connect.fr/la-france-remplace-microsoft-par-scaleway-pour-heberger-les-donnees-de-sante/)) ; Bleu visant fin 2026 | Modèles open-weight auto-hébergés (vLLM) sur GPU, index et données sensibles | Disponibilité et prix des GPU ; pas de modèles frontière |
| 5. Hybride | Données, index et SLM en local ou chez un fournisseur souverain ; génération ou juges via API d'hyperscaler pour le non-sensible | Routage par sensibilité, où la couche de décision du niveau 3 trouve un usage métier | Une erreur de routage est une fuite : décision déterministe par métadonnées du document, le classifieur ne fait que compléter |

La qualification SecNumCloud n'est pas un critère du projet : ces fournisseurs illustrent les CSP avec lesquels travaillent les grands comptes français. Statuts à vérifier sur la liste de l'ANSSI avant toute recommandation client.

**Principes de portabilité**

- Une passerelle de modèles unique au format compatible OpenAI (LiteLLM, open source) vers Bedrock, Azure AI Foundry, Vertex AI, vLLM et llama.cpp.
- pgvector comme dénominateur commun des bases vectorielles, disponible chez les trois hyperscalers et les fournisseurs souverains, plus des adaptateurs natifs (OpenSearch, Azure AI Search, Vertex Vector Search).
- Conteneurs et infrastructure as code (OpenTofu, open source), un module par fournisseur.
- Traces OpenTelemetry quel que soit le fournisseur.
- FinOps : tarifs datés par fournisseur et par région, coûts fixes des services managés. GreenOps : intensité carbone de la région.

## Architecture de l'outil

&#91;embedded content: architecture du banc · 8 composants\]

Le banc enchaîne profilage, ingestion, indexation et évaluation ; le rapport situe le corpus sur la matrice de conviction.

- **Configuration déclarative** : chaque expérience est un fichier YAML (corpus, parser, découpage, modèles, architecture), versionné avec ses résultats.
- **Composants interchangeables** derrière des interfaces communes : QueryRewriter, Parser, Chunker, Embedder, VectorStore, GraphStore, Retriever, Reranker, ContextBuilder, Decider, Generator, Judge. Chaque composant est une clé du fichier de configuration : toute combinaison est exécutable, et une matrice de compatibilité bloque les combinaisons incohérentes (dimension d'embedding, recherche hybride non supportée).
- **Cache d'index** par combinaison corpus × parser × découpage × embedding × base : une indexation n'est jamais refaite.
- **Traçabilité** : chaque appel est tracé (tokens, coût, latence, énergie) via OpenTelemetry, vers plusieurs outils comparés (voir Métriques et juges).
- **Briques existantes** plutôt que code maison : Docling pour l'ingestion, frameworks RAG pour les composants standards.
- **Mode mission** : exécution 100 % locale possible pour les données sensibles ; enchaînement profilage, questions, validation métier, exécution, restitution avec une fiche conformité-sécurité par architecture.
- **Mutualisation** : même socle d'évaluation que le moteur de recherche local et le banc SLM.

**Exposition MCP** : chaque architecture configurée peut être servie comme serveur MCP, donc branchée telle quelle dans Copilot Studio, Claude ou un agent client, en mission comme en formation.

### Plateforme pédagogique

La plateforme réutilise le registre de composants et les traces du banc ; elle ajoute une interface no code pour la formation :

- **Atelier d'assemblage** : ajouter, retirer ou remplacer un composant (reranker, routeur, base vectorielle, modèle) et relancer la même question pour voir l'effet.
- **Vue pas à pas** : requête réécrite, passages retrouvés et leurs scores, passages filtrés, prompt final, réponse et citations, coût et énergie par étape.
- **Mode évaluation** : lancer un petit jeu de questions, comparer les scores des juges et des outils d'évaluation à une annotation humaine.
- **Fiche par composant** : à quoi il sert, quand l'utiliser, ce qu'il coûte, ce que dit la littérature, ce qu'a mesuré le banc.
- **Mode attaque** : document piégé, suppression d'un document, deux profils de droits, pour montrer les risques de la section Conformité.

WaveStack couvre déjà trois RAG (dense, hybride, reranking), les garde-fous, le FinOps et le GreenOps. Étendre WaveStack avec un atelier « recherche documentaire » coûte moins cher que créer une deuxième application, au prix d'un couplage entre les deux projets : c'est l'option retenue le 17 octobre 2026, avec un brief de développement dédié.

## Phasage et points de contrôle

Huit phases ; chacune se termine par un point de contrôle avant de passer à la suivante.

1. **Jeu d'évaluation et baselines** sur CO Fantasy et notes MTG. Contrôle : juges calibrés, baselines reproductibles.
2. **Architectures texte** (niveau 1). Contrôle : front de Pareto par corpus, premières hypothèses tranchées.
3. **Composants, bases vectorielles et couche de décision** (niveaux 2 et 3). Contrôle : première version de la matrice de conviction.
4. **Formats et parsers** (niveau 4). Contrôle : H8 et H9 tranchées.
5. **GenBI**. Contrôle : intégration au routeur par requête.
6. **Multimodal** : schémas d'abord, audio et vidéo ensuite. Contrôle : gain mesuré sur les questions visuelles.
7. **Optimiseur de configuration**, validé contre la grille complète du banc. Contrôle : H16 tranchée, écart de qualité et coût économisé mesurés.
8. **Plateforme pédagogique, mode mission et publication**. Contrôle : le banc tourne de bout en bout sur un corpus inconnu, fiches conformité-sécurité comprises ; une session de formation menée sur la plateforme ; slides de conviction refaites à partir des résultats.

La plateforme pédagogique se construit au fil des phases, car elle repose sur le même registre de composants.

## Risques et décisions à prendre

| Risque | Parade |
| --- | --- |
| Explosion combinatoire | Niveaux successifs, front de Pareto, un facteur à la fois |
| Biais des juges | Panel multi-familles, calibration sur annotations humaines |
| Coût API | Plafond par niveau, cache des réponses, appels en lot |
| Obsolescence des modèles | Liste datée et figée par niveau, relance périodique |
| Droits sur les corpus | Usage privé ; corpus publiable distinct (notes MTG, contrefactuel) |
| Conviction biaisée par des corpus non professionnels | Valider la matrice sur un corpus de mission réel avant de la diffuser |
| Dérive de périmètre | Multimodal et GenBI hors des phases 1 à 4 |

**Décisions à prendre**

Classées par échéance. D1 à D5 sont tranchées (17 octobre 2026) : plus rien ne bloque la phase 1. Recommandation à valider, corriger ou rejeter.

| # | Décision | Options | Ce que ça change | Recommandation | Échéance |
| --- | --- | --- | --- | --- | --- |
| D1 | Taille et annotation du jeu d'évaluation | 100, 150 ou 200 questions par corpus ; annotation par toi seul ou avec un second annotateur | Plus de questions = écarts plus fins détectables, mais des jours d'annotation ; sans second annotateur, pas de plafond d'accord humain | Décidé : 150 questions par corpus, dont 50 annotées aussi par un collègue | Avant la phase 1 |
| D2 | Budget cloud | Plafond mensuel ; clés personnelles, budget Wavestone ou crédits fournisseurs | Fixe la profondeur des niveaux 1 à 3 et le nombre de juges | Décidé : 50 €/mois sur Azure AI Foundry (Wavestone) et 50 $/mois sur l'API Anthropic (personnel). Conséquences : modèles serverless seulement, pas de VM GPU ; juges peu coûteux en masse, juge frontière réservé à la calibration ; API batch et cache de prompt ; génération et embeddings en local quand possible ; arrêt automatique au plafond | Avant la phase 1 |
| D3 | Hyperscaler de départ | AWS, Azure AI Foundry ou GCP Vertex, selon les accès confirmés | Un seul au départ divise l'effort d'infrastructure ; les autres arrivent par la passerelle de modèles | Décidé : Azure (AI Foundry) | Avant la phase 1 |
| D4 | Socle logiciel | LlamaIndex, Haystack, ou code minimal maison autour d'interfaces + Optuna | Un framework accélère le départ mais impose ses abstractions ; le maison garantit la flexibilité des composants | Décidé : code minimal maison et Optuna ; les frameworks entrent comme composants comparés | Avant la phase 1 |
| D5 | Corpus sous droits et cloud | Envoyer ou non les PDF CO et tes notes personnelles à des API cloud | Droits d'auteur et confidentialité contre puissance des modèles frontière | Décidé : aucune contrainte de droits à prévoir, tous les corpus peuvent passer par des API cloud | Avant la phase 1 |
| D6 | Fournisseur IaaS souverain (profil 4) | S3NS (qualifié, technologie Google), OVHcloud ou Outscale (qualifiés, capital français), Scaleway (en cours) | Disponibilité de GPU dans le périmètre qualifié, coût, argument de souveraineté | La qualification n'est pas un critère : choisir sur le prix et la disponibilité des GPU ; non couvert par le budget actuel, donc après la phase 3 | Avant le profil 4 |
| D7 | Règle de sensibilité du profil hybride | Métadonnées du document, classifieur, ou les deux | Déterministe et auditable contre plus souple mais faillible | Métadonnées obligatoires, classifieur en complément pour alerter | Avant le profil 5 |
| D8 | Plateforme WaveStack : métriques agrégées | Lever l'interdiction de la spec V2 sur la seule vue évaluation, ou rester aux verdicts par question | Enseigner l'évaluation sans scores agrégés est difficile | Lever sur la vue évaluation, toujours avec intervalle de confiance et accord humain affichés | Avant la spec du lot |
| D9 | Plateforme WaveStack : comparaison A/B | Rétablir deux exécutions côte à côte, ou non | « Retirer un composant et voir l'effet » en dépend | Rétablir, limité à deux exécutions | Avant la spec du lot |
| D10 | Plateforme WaveStack : articulation avec la V2 | Fusionner CAP-1 à CAP-4 et CAP-7/8 dans le lot, ou les livrer d'abord | CAP-1 (jeu de questions) est un prérequis de la vue évaluation | Livrer CAP-1 d'abord, fusionner le reste | Avant la spec du lot |
| D11 | Plateforme WaveStack : corpus et GraphRAG | Enrichir Exemplia ou nouveau corpus ; GraphRAG et LLM Wiki maison ou via bibliothèque | Cohérence et traductions existantes ; lisibilité pédagogique contre fidélité | Enrichir Exemplia (multi-sauts, versions, interlingue, document piégé) ; implémentations maison simplifiées | Avant la spec du lot |
| D12 | Budget par défaut du mode mission | Forfaits en euros et en heures | Ce que l'outil promet à un client | Fixer après la phase 7, sur mesures réelles | Phase 7 |
| D13 | Publication | Corpus publiables (notes MTG ?), cible (arXiv, atelier, blog Wavestone) | Les corpus sous droits ne peuvent pas être publiés | arXiv et blog Wavestone ; atelier si les résultats H3, H7, H12 ou H13 sont nets | Phase 8 |
| D14 | Mutualisation avec le moteur local et le banc SLM | Partager le harnais d'évaluation, la mesure d'énergie, le code applicatif | Gain de temps contre couplage entre projets | Partager l'évaluation et la mesure d'énergie, pas le code applicatif | Phase 1 |

Décidé : plateforme pédagogique en extension de WaveStack (17 octobre 2026) ; optimisation bayésienne avec évaluation progressive plutôt que recuit simulé.

## Sources

Toutes les pages ci-dessous ont été ouvertes lors des recherches du 17 octobre 2026. La colonne « Biais ou limite » signale ce qui fragilise une source.

| Hyp. | Source | Date | Biais ou limite |
| --- | --- | --- | --- |
| Général | [LLM Wiki (gist de Karpathy)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | avr. 2026 | Texte de référence du pattern, sans évaluation |
| Général | [Decision models explained (eesel.ai)](https://www.eesel.ai/blog/decision-models) | oct. 2026 | Synthèse de blog, scores en partie auto-déclarés |
| Général | [Artificial Analysis Decision Index](https://artificialanalysis.ai/articles/artificial-analysis-decision-index) | 13 oct. 2026 | Aucune tâche RAG dans l'index |
| Général | [AnyJev (Nokia)](https://github.com/nokia-applied-research/AnyJev) | oct. 2026 | Résultats publiés par les auteurs |
| H1 | [From BM25 to Corrective RAG](https://arxiv.org/html/2604.01733) | avr. 2026 | Un seul domaine (finance) |
| H1 | [Contextual Retrieval (Anthropic)](https://www.anthropic.com/news/contextual-retrieval) | sept. 2024 | Étude d'éditeur |
| H1 | [Parameterized Dense-Sparse Fusion](https://arxiv.org/abs/2609.22770) | sept. 2026 | — |
| H1 | [LiveRAG](https://arxiv.org/abs/2506.22644v1) | juin 2025 | Cadre de compétition, un corpus |
| H2 | [RAG vs. GraphRAG: A Systematic Evaluation](https://arxiv.org/html/2502.11371v2) | fév. 2025, rév. oct. 2025 | — |
| H2 | [When to use Graphs in RAG (GraphRAG-Bench)](https://arxiv.org/html/2506.05690v3) | rév. fév. 2026 | — |
| H2 | [Unbiased Evaluation Framework for GraphRAG](https://arxiv.org/abs/2506.06331) | rév. août 2026 | — |
| H2 | [LightRAG](https://arxiv.org/html/2410.05779) | oct. 2024 | Auteurs d'une architecture concurrente |
| H2 | [EraRAG](https://arxiv.org/pdf/2506.20963v1.pdf) | juin 2025 | Auteurs d'une architecture concurrente |
| H2 | [LazyGraphRAG (Microsoft Research)](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/) | nov. 2024 | Étude d'éditeur, 100 requêtes synthétiques |
| H3 | [Vector RAG vs LLM-Compiled Wiki](https://arxiv.org/html/2605.18490v1) | mai 2026 | 24 articles, 13 questions |
| H3 | [Retrieval as Reasoning via LLM-Wiki (Tencent)](https://arxiv.org/html/2605.25480v2) | mai 2026 | Passage à l'échelle non testé |
| H4 | [PageIndex (VectifyAI)](https://github.com/VectifyAI/PageIndex) | consulté oct. 2026 | Éditeur |
| H4 | [Mafin 2.5 (PageIndex)](https://pageindex.ai/blog/Mafin2.5) | fév. 2025 | Éditeur, protocole non publié |
| H4 | [Adaptive Query Routing](https://arxiv.org/html/2604.14222v1) | avr. 2026 | 22 à 50 questions, un auteur, juge GPT-4o-mini |
| H5 | [Did Filesystem Tools Kill Vector Search? (LlamaIndex)](https://www.llamaindex.ai/blog/did-filesystem-tools-kill-vector-search) | janv. 2026 | Éditeur, 5 questions |
| H5 | [Beyond Semantic Similarity (NVIDIA, CAIS'26)](https://arxiv.org/pdf/2610.05750) | 2026 | — |
| H5 | [Is Agentic RAG worth it?](https://arxiv.org/html/2601.07711v2) | rév. avr. 2026 | — |
| H5 | [Subramanian et al. (AWS)](https://arxiv.org/html/2602.23368v1) | 2025-2026 | Coût et latence non mesurés |
| H6, H11 | [RAG or Long-Context LLMs? (Self-Route, Google DeepMind)](https://arxiv.org/html/2407.16833v1) | juil. 2024 | Modèles de 2024 |
| H6 | [RAGRouter-Bench](https://arxiv.org/html/2602.00296v2) | 2026 | — |
| H6 | [Adaptive-RAG](https://arxiv.org/pdf/2403.14403) | mars 2024 | Modèles de 2024 (GPT-3.5) |
| H6 | [Ablation locale 7B (Shaikh)](https://arxiv.org/html/2606.21553v1) | juin 2026 | Un auteur, un modèle 7B |
| H7 | [Jev as a judge for RAG claim verification (Towards AI)](https://pub.towardsai.net/jev-as-a-judge-for-rag-claim-verification-7b356619814c) | sept. 2026 | Auteur chez un éditeur RAG |
| H7 | [Jev as an LLM judge (MLflow)](https://mlflow.org/blog/jev-llm-judge/) | sept. 2026 | 30 exemples, un seul critère |
| H7 | [TypeSafe Jev as LLM judge (Arize)](https://arize.com/blog/typesafe-jev-llm-judge/) | sept. 2026 | Chiffres fournis par TypeSafe |
| H7 | [jev-corrective-rag](https://github.com/sudeshkar/jev-corrective-rag) | 2026 | Latence mesurée sur un simulacre d'API, exactitude non mesurée |
| H8 | [OCR Hinders RAG (ICCV 2025)](https://arxiv.org/pdf/2412.02592) | 2025 | — |
| H8 | [Simmering et al.](https://arxiv.org/html/2508.15817v1) | 2025 | 41 présentations |
| H8 | [Sousa et al.](https://arxiv.org/abs/2604.04948) | mars 2026 | Un domaine, 50 questions |
| H8 | [BizDocBench](https://github.com/DocSlicer/BizDocBench) | juil. 2026 | Éditeur classé premier de son propre benchmark, pas d'Excel |
| H9 | [Which Table Format Do LLMs Understand Best? (Improving Agents)](https://www.improvingagents.com/blog/best-input-data-format-for-llms) | sept. 2025 | Un seul modèle (GPT-4.1-nano), tableaux plats |
| H9 | [Benchmarks TOON](https://toonformat.dev/guide/benchmarks) | consulté oct. 2026 | Publié par le projet TOON |
| H9 | [Notation Matters (Know Center)](https://arxiv.org/html/2605.29676v2) | 2026 | — |
| H9 | [Matveev](https://arxiv.org/html/2603.03306) | 2026 | — |
| H10 | [LIT-RAGBench](https://arxiv.org/html/2603.06198v1) | mars 2026 | 114 questions ; écarts moyennés par nos soins |
| H10 | [MultiHop-RAG](https://arxiv.org/html/2401.15391) | 2024 | Modèles anciens (Llama-2) |
| H10 | [RAG study (Pinecone)](https://pinecone.io/blog/rag-study) | janv. 2024 | Étude d'éditeur |
| H10 | [Pandey](https://arxiv.org/html/2603.11513) | mars 2026 | Un auteur, quantification 4 bits |
| H11 | [Long Context vs. RAG: An Evaluation and Revisits](https://arxiv.org/html/2501.01880v1) | janv. 2025 | — |
| H11 | [LaRA](https://arxiv.org/html/2502.09977v1) | fév. 2025 | — |
| Conformité, FinOps, GreenOps | [agentic-harness-training-demo (WaveStack)](https://github.com/Aliquanto3/agentic-harness-training-demo) | 2026 | Travaux personnels, démonstrateur pédagogique |

**Sources complémentaires (H12 à H16, outils d'évaluation)**

| Hyp. | Source | Date | Biais ou limite |
| --- | --- | --- | --- |
| H12 | [PoisonedRAG](https://arxiv.org/abs/2402.07867) | fév. 2024, rév. août 2024 | Questions cibles préparées à l'avance |
| H12 | [GraphRAG under Fire](https://arxiv.org/abs/2501.14050) | janv. 2025, v4 oct. 2025 | — |
| H12 | [A Few Words Can Distort Graphs](https://arxiv.org/abs/2508.04276) | août 2025 | — |
| H12 | [Exposing Privacy Risks in Graph RAG](https://arxiv.org/abs/2508.17222) | août 2025 | Pas de chiffres dans le résumé |
| H12 | [Enterprise AI Must Enforce Participant-Aware Access Control (Microsoft Research)](https://www.microsoft.com/en-us/research/publication/enterprise-ai-must-enforce-participant-aware-access-control) | sept. 2025 | Position d'éditeur |
| H12 | [OWASP LLM08:2025 Vector and Embedding Weaknesses](https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/) | 2025 | Référentiel, pas une mesure |
| H12 | [Questions-réponses de la CNIL sur l'IA générative](https://cnil.fr/fr/les-questions-reponses-de-la-cnil-sur-lutilisation-dun-systeme-dia-generative) | juil. 2024 | Rien sur l'exercice des droits dans un RAG |
| H12 | [RAG unlearning (Wang et al.)](https://arxiv.org/html/2410.15267v2) | 2024 | Oubli par ajout de consignes, sans suppression |
| H12 | [Moving to GraphRAG 1.0 (Microsoft Research)](https://www.microsoft.com/en-us/research/blog/moving-to-graphrag-1-0-streamlining-ergonomics-for-developers-and-users/) | déc. 2024 | Mise à jour documentée pour l'ajout seulement |
| H13 | [Guo et al. (énergie RAG)](https://arxiv.org/html/2601.02522v2) | janv. 2026 | Phase de requête seulement |
| H13 | [Heavey et Cook (PMLR 318)](https://proceedings.mlr.press/v318/heavey26a.html) | juin 2026 | Indexation non mesurée |
| H13 | [Jourlin (graphe de connaissances local)](https://arxiv.org/abs/2604.11104) | avr. 2026 | Outil de mesure non précisé |
| H13 | [Karpathy LLM knowledge base (VentureBeat)](https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an) | avr. 2026 | Article de presse |
| H14 | [Toward Optimal Search and Retrieval for RAG](https://arxiv.org/html/2411.07396v1) | nov. 2024 | Un retriever, deux lecteurs 7B |
| H14 | [Binary and Scalar Embedding Quantization (Hugging Face)](https://huggingface.co/blog/embedding-quantization) | mars 2024 | Retrieval seul, effet très dépendant du modèle |
| H14 | [Benchmarking Filtered ANN on Transformer Embeddings](https://arxiv.org/html/2507.21989v1) | juil. 2025 | Algorithmes, pas bases prêtes à l'emploi |
| H14 | [Results of the Big ANN: NeurIPS'23](https://arxiv.org/html/2409.17424v1) | sept. 2024 | Benchmarks fragiles (calcul de rappel corrigé) |
| H14 | [Enhancing HNSW for Real-Time Updates](https://arxiv.org/html/2407.07871v1) | juil. 2024 | — |
| H14 | [Benchmarks Qdrant](https://qdrant.tech/benchmarks/) | 2023 | Éditeur, biais reconnu |
| H14 | [VDBBench 1.0 (Zilliz)](https://zilliz.com/blog/vdbbench-1-0-benchmarking-with-your-real-world-production-workloads) | 2025 | Éditeur |
| H14 | [pgvector 0.8.0](https://www.postgresql.org/about/news/pgvector-0.8.0-released-2952/) | 2024 | Annonce sans chiffres |
| H15 | [ARES](https://arxiv.org/pdf/2311.09476) | v2 mars 2024 | Étude des auteurs d'ARES |
| H15 | [RAGChecker](https://arxiv.org/pdf/2408.08067) | août 2024 | Étude d'Amazon sur son outil |
| H15 | [RAGBench](https://arxiv.org/abs/2407.11005) | v2 janv. 2025 | Éditeur concurrent (Galileo) |
| H15 | [GroUSE](https://arxiv.org/abs/2409.06595) | sept. 2024 | — |
| H15 | [Brabant, EvalLLM](https://arxiv.org/abs/2607.07302) | juil. 2026 | 96 questions, un système |
| H15 | [Lau (variance des juges)](https://arxiv.org/abs/2603.04417) | fév. 2026 | Chiffres en graphiques seulement |
| H15 | [Ragas contre DeepEval sur une réponse fabriquée](https://dev.to/nickjlamb/we-gave-the-same-fabricated-answer-to-ragas-and-deepeval-one-scored-it-00-the-other-scored-it-10-57om) | 2026 | Expérience non académique |
| H15 | [Surcoût des outils de traces (AIMultiple)](https://aimultiple.com/agentic-monitoring) | juin 2026 | Une charge, sans variance |
| H16 | [Beyond Grid Search (EACL 2026 Industry)](https://preview.aclanthology.org/credits/2026.eacl-industry.19) | mars 2026 | Trois jeux de données publics |
| H16 | [Faster, Cheaper, Better: Multi-Objective HPO for LLM and RAG](https://arxiv.org/abs/2502.18635) | fév. 2025 | Pas de chiffres dans le résumé |
| H16 | [AutoRAGTuner (Ant Group)](https://arxiv.org/pdf/2605.02967) | 2026 | Comparé aux réglages par défaut, pas à la grille ; pas de dépôt public |
