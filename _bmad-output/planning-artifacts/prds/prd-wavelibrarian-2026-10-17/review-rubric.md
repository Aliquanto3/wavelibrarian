# Revue de qualité du PRD : WaveLibrarian

Relu : `prd.md` et `addendum.md`. Grille : `.claude/skills/bmad-prd/assets/prd-validation-checklist.md`. Date : 2026-10-17.
Angle demandé : les FR-1 à FR-41 sont-elles assez testables et sans ambiguïté pour que des agents Claude Code écrivent l'architecture, les stories et le code en autonomie ? Quelles ambiguïtés les forceraient à deviner ?

## Verdict global

Le PRD est solide sur la thèse, la discipline de périmètre et le vocabulaire : glossaire dense, hypothèses indexées, contre-indicateurs, risques. Il est en revanche inégal sur la clarté de « terminé » pour un développement sans humain. Sept FR n'ont aucune conséquence testable. Plusieurs seuils et définitions sont absents, et quatre dépendances du MVP sont ambiguës ou contradictoires (le modèle de référence, l'embedder, le faux LLM, la notion de « qualité »). Grade selon la règle de synthèse : **Fair** (pas de constat critique, plusieurs constats de gravité haute). Correctifs courts, à faire avant de lancer l'architecture.

## Decision-readiness — adequate

Les décisions sont posées comme des décisions : D1 à D14 renvoyées au cadrage, ordre des architectures, plafond de 5 $, Haiku 5.5 exclu des longs contextes. Les arbitrages sont nommés avec ce qui est abandonné : pas de score global, pas d'interface d'annotation, pas de framework comme socle. Les Questions ouvertes sont réellement ouvertes et ont un responsable et une échéance (§10, Q1, Q2, Q5).

Risque : les Questions ouvertes Q2 (liste figée des modèles de référence) et Q3 (embedder par défaut) ne sont pas hors du chemin du MVP. SM-3 et SM-4 exigent des exécutions de bout en bout avec des modèles, ce que le §10 renvoie à plus tard. Le §10 donne aussi une valeur par défaut au kappa (0,6, Q1) alors que FR-38 parle d'un « seuil retenu » sans valeur : un agent doit choisir.

### Findings
- **[high]** Les modèles du MVP restent à décider alors que les critères de succès en dépendent (§10 Q2/Q3, §7.1, SM-3, SM-4) — Aucun Generator, embedder ni modèle de Filtre closed-book par défaut n'est nommé. L'addendum ne donne que des exemples (« Exemple : Generator Haiku 5.5… »), et aucun modèle d'embedding n'est installé sur la machine. L'agent d'architecture devra trancher seul. *Fix :* ajouter au §7.1 un « tableau des modèles par défaut du MVP » (Generator, juges, embedder, modèles closed-book) ou déclarer explicitement que l'architecte les fixe dans un fichier de configuration par défaut et que SM-3/SM-4 s'y réfèrent.
- **[medium]** Valeur du seuil de kappa incohérente (FR-38 « seuil retenu », §10 Q1 « proposition 0,6 », SM-5 `[ASSUMPTION]` 0,6) — Trois formulations pour une valeur. *Fix :* écrire dans FR-38 « seuil par défaut 0,6, configurable » et supprimer l'ambiguïté.

## Substance over theater — strong

Pas de théâtre de personas : un seul opérateur, deux rôles. Pas d'innovation ou de différenciation factices. Les exigences transverses contiennent de vrais seuils quand ils existent : plafond de 5 $, GPU de 8 Go, Python 3.12 géré par uv, comparaison appariée en McNemar. Le §5 « Robustesse » est la seule zone adjectivale (« nombre de tentatives borné »). La Vision est propre à ce produit et ne se transposerait pas ailleurs.

### Findings
- **[low]** Exigence de robustesse sans valeur (§5 « Robustesse ») — « réessayés avec un nombre de tentatives borné » ne dit ni le nombre ni le délai. *Fix :* par exemple 3 tentatives, attente exponentielle, valeurs configurables.

## Strategic coherence — strong

La thèse est claire : remplacer les avis par des mesures appariées avec juges calibrés. Les FR en découlent (Gel, test réservé, closed-book, kappa, bootstrap), et les contre-indicateurs SM-C1 à SM-C3 sont nommés, chacun adossé à son indicateur principal. La logique de MVP est un MVP de plateforme : socle, phases 1 et 2, le reste différé.

Point faible : tension interne sur l'unité de « qualité » (voir Done-ness).

### Findings
- **[high]** « Qualité » est utilisée comme axe scalaire alors que le PRD interdit tout score global (FR-31, FR-40, FR-41, SM-C3 contre FR-36 « Aucun score global » et §6) — Les fronts de Pareto « qualité × coût » et « qualité × énergie », le point mort « qualité égale ou supérieure » et le lancement d'un niveau « à partir du front de Pareto » exigent un nombre unique par Configuration. Or les Critères sont notés séparément. Un agent devra inventer l'agrégat (quel Critère, quel Type de question, quelle moyenne). *Fix :* définir « qualité » pour les besoins de Pareto/point mort : un Critère choisi dans l'Expérience (défaut : exactitude), ou un front par Critère. Définir « qualité égale » en termes d'intervalle de confiance : par exemple, les deux IC se recouvrent ou la différence appariée n'est pas significative (FR-39).

## Done-ness clarity — thin

C'est la dimension qui décide ici, et elle est inégale. Les FR-1 à FR-16, FR-25 à FR-38 et FR-40 comportent des « Conséquences (testables) » utilisables, et beaucoup sont de vraies assertions : message citant le chemin de la clé, identifiant indépendant du nom de fichier, somme des Traces égale au total du Rapport, refus avant tout appel. Elles se traduisent directement en tests.

À l'inverse, les FR suivantes n'ont aucune conséquence testable : **FR-17** (contexte parfait), **FR-18** (RAG naïf), **FR-20** (HyDE), **FR-21** (Corrective RAG), **FR-23** (RAPTOR), **FR-24** (PageIndex) et **FR-39** (statistiques). Elles décrivent une technique en une ligne. FR-14 (suite de conformité commune) couvre en partie le minimum, mais pas les comportements propres à chaque technique. Sans cela, un agent peut livrer une « implémentation » qui passe la conformité et ne fait pas ce que la technique prétend.

Ambiguïtés qui obligent à deviner (la liste demandée) :

1. **Faux LLM et faux embedder non spécifiés.** Toute la validation du MVP (FR-14, §5, UJ-4, SM-3) repose sur eux, mais le PRD ne dit pas ce qu'ils font : comment le faux LLM produit-il une Citation valide, un indicateur d'abstention, des tokens en cache, une réponse à un juge ? « Déterministes sans réseau » ne suffit pas à faire passer « réponse avec au moins une Citation valide » à une Architecture réelle.
2. **« Question réussie » du Filtre closed-book (FR-12)** : par correspondance exacte, par un Juge, ou par un seuil ? Si c'est un Juge, il est circulaire avec la calibration (le Juge n'est pas encore calibré au moment du Gel, UJ-1).
3. **Correspondance exacte « quand la Réponse de référence s'y prête » (FR-36)** : aucun critère de décision (type nombre, nom propre court, longueur maximale ?).
4. **Séparation développement/test (FR-13)** : pas de proportion. Avec un Jeu de référence de 30 Questions réparties sur 9 Types plus attributs (FR-8), la stratification donne un à trois exemples par Type : les intervalles de confiance et McNemar y sont presque vides. L'agent devra décider si les tests de bout en bout tolèrent cette taille.
5. **Seuils et paramètres techniques absents** : seuil de pertinence et nombre de boucles du Corrective RAG (FR-21), k de la recherche dense (FR-18), paramètres de regroupement et profondeur de l'arbre de RAPTOR (FR-23), nombre d'étapes et dépense maximale par Question pour l'agent (FR-26, « bornés par la Configuration » sans valeur par défaut), nombre de rééchantillons et niveau de confiance du bootstrap (FR-39).
6. **Définitions des Descripteurs (FR-7)** : « densité de liens » suppose une extraction d'entités nommées dont l'outil n'est pas fixé ; « part visuelle », « part tabulaire » (en tokens ? en blocs ?), tokenizer pour le « nombre de tokens » non précisés. Le nombre de tokens dépend du tokenizer utilisé, ce qui n'est pas anodin pour la comparaison à la fenêtre du modèle (FR-3, FR-16, FR-22).
7. **Format du fichier de questions (FR-9)** : « fichier éditable à la main », sans le format (YAML, JSONL, CSV ?). L'addendum ne tranche pas. UJ-1 parle d'éditeur, donc un format texte est probable, mais ce choix sera fait à l'aveugle.
8. **FR-4 « les mêmes résultats de recherche »** : le texte de conséquence promet aussi des Réponses identiques. Pour les appels hors cache (nouveaux), l'aléa des LLM locaux rend l'énoncé faux. Préciser que l'identité est garantie uniquement quand les caches sont rejoués.
9. **FR-3 « dimension d'embedding différente de celle de l'index en cache »** : cas d'usage flou, puisque la clé de cache inclut déjà l'Embedder (FR-28). Dire ce qui est testé (une Configuration qui référence un index existant avec un autre Embedder).
10. **Famille de modèles (FR-3, FR-37)** : la règle suppose une table modèle → Famille. Où est-elle déclarée (Grille tarifaire, Registre, configuration) ? À défaut, l'agent la codera en dur ou dérivera la Famille d'un préfixe de nom.
11. **FR-5 sensibilité et droits** : « niveau de sensibilité » et « droits d'accès » sans valeurs ni schéma. Comme c'est une préparation post-MVP, accepter un champ libre texte devrait suffire ; à écrire.
12. **FR-33 « coût maximal estimé »** : comment estimer le coût maximal d'un appel (tokens d'entrée comptés par quel tokenizer, sortie plafonnée à max_tokens) n'est pas dit. Devise : le PRD parle d'euros (Vision, FR-48) mais le plafond est en dollars (FR-33, 5 $) ; la Grille ne dit pas dans quelle devise elle est tenue.
13. **SM-4 « la dépense tracée correspond à la Grille tarifaire »** : tolérance non donnée, aucune source externe de vérité (facture) disponible de nuit ; le test ne peut vérifier que la cohérence interne.
14. **FR-8 « écrites à la main »** pour un mini-corpus produit par un agent : la phrase signifie en pratique « rédigées par l'agent, relues par Anaël après coup » ; le statut « écrite à la main » (FR-9) ne doit pas être attribué à l'agent. Préciser l'origine (« humain » vs « modèle »).

### Findings
- **[high]** Sept FR sans conséquence testable (FR-17, FR-18, FR-20, FR-21, FR-23, FR-24, FR-39) — Le plus gros risque de sur- ou de sous-implémentation silencieuse. FR-21, FR-23 et FR-24 sont les techniques où deux implémentations raisonnables divergent le plus. *Fix :* ajouter pour chacune au moins deux assertions vérifiables avec le faux LLM, par exemple HyDE : « l'embedding de la requête est celui de la réponse hypothétique, tracé comme étape distincte » ; Corrective RAG : « sous le seuil, une nouvelle recherche est émise, au plus N fois (défaut 2), puis abstention » ; RAPTOR : « l'arbre contient au moins un niveau de résumé et la recherche renvoie des Passages de niveaux différents » ; PageIndex : « l'arbre de table des matières est persistant et chaque section lue est tracée ».
- **[high]** Faux LLM et faux embedder non spécifiés alors que tout le contrôle du MVP en dépend (FR-14, §3, §5, UJ-4) — *Fix :* ajouter une FR « Composants factices » qui décrit leur contrat : le faux LLM renvoie une Réponse dérivée du contexte reçu (par exemple recopie de la première phrase du premier Passage avec sa Citation), s'abstient quand le contexte est vide, déclare des tokens et un cache simulés ; le faux embedder est un hachage déterministe de dimension fixe.
- **[high]** Définition de « Question réussie » du Filtre closed-book absente (FR-12, UJ-1) — Une définition circulaire avec les juges non calibrés ou une correspondance exacte trop stricte rendent la contamination non testable. *Fix :* fixer la règle (correspondance exacte si éligible, sinon Juge du Panel, verdict « correct » sur le Critère exactitude) et l'ordre d'exécution par rapport à la calibration.
- **[medium]** Paramètres numériques et formats manquants listés ci-dessus (points 3 à 7, 11 et 12 notamment). *Fix :* regrouper dans une section « Valeurs par défaut » du PRD ou de l'addendum, avec la mention « configurable » ; l'architecte peut ensuite les confirmer.
- **[medium]** Séparation développement/test non dimensionnée pour un Jeu de 30 Questions (FR-8, FR-13) — *Fix :* fixer une proportion (par exemple 50/50) et accepter explicitement que, sur le Mini-corpus, les statistiques ne sont qu'un test de plomberie.
- **[low]** FR-3 : la conséquence « dimension d'embedding » est plus précise à écrire (voir point 9). FR-4 : restreindre l'énoncé aux rejeux avec caches (point 8).

## Scope honesty — adequate

Les omissions sont explicites : §2.2, §6 et §7.2 délimitent clairement. Les `[Post-MVP]`, les 7 `[ASSUMPTION]` indexés et la table des risques sont honnêtes. Aucun `[NOTE FOR PM]` : acceptable pour un outil interne. Densité des éléments ouverts : 5 questions ouvertes et 7 hypothèses, proportionné à l'enjeu (un run de nuit sous 5 $), mais deux hypothèses bloquantes pour l'implémentation sont enfouies dans des FR : la Haiku 5.5 exclu du contexte long (FR-16) et le Panel MVP (FR-37).

Risque de faisabilité : 41 FR, dix familles d'Architectures et un budget de 5 $ pour une nuit. Le PRD le sait (ordre de priorité, SM-C1, « les Architectures livrées doivent toutes passer la conformité »), mais SM-3 n'exige que quatre Architectures, alors que §7.1 « Inclus » liste les dix : l'intention exacte (objectif ou minimum) n'est pas dite.

### Findings
- **[high]** Le Panel de juges et le test réel dépendent d'un budget et de modèles locaux dont la faisabilité n'est pas vérifiée (FR-16, FR-37, SM-4, addendum) — Contexte long et CAG sont refusés pour Haiku 5.5 ; aucun autre modèle API n'est prévu ; les modèles locaux de 3 à 12 Go sur GPU 8 Go ont une fenêtre limitée. Il est donc possible que *aucune* Configuration de contexte long ou de CAG ne soit exécutable au MVP, y compris sur le Mini-corpus (long document structuré, FR-8). Dans ce cas FR-16/FR-22 seraient « inapplicables » par construction et seraient testées sans jamais s'exécuter. *Fix :* dire quel modèle exécute la Baseline contexte long et le CAG dans les tests réels (par exemple Sonnet 5.5 plafonné, ou le faux LLM avec fenêtre simulée) et confirmer que la fenêtre déclarée couvre le Mini-corpus.
- **[medium]** Intention de SM-3 vs §7.1 (quatre vs dix Architectures) — *Fix :* « objectif : toutes, minimum accepté : quatre qui passent la conformité ».
- **[medium]** Dépendance de `docs/cadrage.md` pour des éléments que les FR invoquent sans les redéfinir : H1 à H17, D1 à D14, « niveau 0/1/2 », « phases 1 à 8 », « cadrage § Juges ». Un agent qui n'a pas lu le cadrage devine ; « D1 (150 Questions) » est le seul chiffre repris. *Fix :* mentionner dans §0 que le cadrage est une lecture obligatoire pour l'architecte et les stories, et définir « niveau 0/1/2 » dans le Glossaire.
- **[low]** Tests réseau : l'addendum choisit Docling (modèles téléchargés au premier usage) et un embedder local à installer, ce qui entre en tension avec « aucun appel réseau » (§5). *Fix :* préciser que l'installation des modèles est faite hors test et que les tests utilisent des fixtures ou les faux Composants.

## Downstream usability — adequate

Le glossaire est le point fort : les termes de domaine sont utilisés de façon cohérente (Ancrage, Passage, Poste de coût, Corpus/Document). IDs FR-1 à FR-51 contigus, SM-1 à SM-5 plus SM-C1 à SM-C3, UJ-1 à UJ-5 : pas de trou, pas de doublon. Les UJ ont un protagoniste (Anaël ou l'agent). Les renvois « Réalise UJ-x » résolvent. Les sections se lisent isolément.

Défauts : plusieurs termes de composants (Generator, Decider, Retriever, Reranker, ContextBuilder, QueryRewriter) sont cités dans l'énumération de « Composant » mais pas définis ; « Generator » est employé dans FR-17, FR-18 et FR-3 comme un terme établi. Les interfaces ne sont que nommées, ce qui est normal pour un PRD mais laisse à l'architecte de décider si « Decider » est un composant de MVP ou seulement de FR-21.

### Findings
- **[medium]** Termes d'interface non définis (§3 « Composant », FR-3, FR-17, FR-21) — Generator, Decider, Retriever, Reranker, QueryRewriter, ContextBuilder. *Fix :* une ligne de glossaire chacun (entrée, sortie), ou les renvoyer à `bmad-architecture` explicitement.
- **[low]** « Niveau 0 », « niveau 1 », « niveau 2 » (Baseline, FR-41, §3) et « phase 1 à 8 » ne sont définis qu'au cadrage. *Fix :* voir plus haut (définition au glossaire).

## Shape fit — adequate

Outil interne, mono-opérateur, CLI : un capability spec avec FR détaillées est la bonne forme. Les cinq UJ sont un peu de formalisme, mais UJ-1 à UJ-4 portent des cas limites utiles et sont reliés aux FR ; UJ-5 est étiqueté post-MVP. Les SM sont opérationnels (tests qui passent, dépense tracée), ce qui convient. Un point : le PRD sert de pilote à une chaîne architecture → stories → code. Le poids est donc à raison sur la testabilité des FR, ce que la section Done-ness juge insuffisant.

### Findings
- Aucun.

## Mechanical notes

- **Index des hypothèses** : les 7 `[ASSUMPTION]` en ligne (FR-7, FR-16, FR-25, FR-27, FR-37, SM-2, SM-5) sont tous indexés au §11 et inversement. Aller-retour correct.
- **Continuité des ID** : FR-1 à FR-51, SM-1 à SM-5, SM-C1 à SM-C3, UJ-1 à UJ-5 sans trou ni doublon. §0 écrit « FR-1 à FR-N » : remplacer N par 51.
- **Références croisées** : FR-11 renvoie à FR-6, FR-16 à FR-3, FR-37 à FR-3, FR-34 à FR-37 ; toutes résolvent. SM-1 « Valide FR-35 à FR-44 » mélange MVP et post-MVP, ce qui est cohérent avec « fin de phase 3 » mais devrait l'écrire.
- **Dérive de glossaire** : « Faux LLM » (glossaire, §5) vs « faux LLM » (FR-14) ; « Jeu d'évaluation de référence » vs « Jeu d'évaluation » du Mini-corpus ; « Plafond » vs « plafond » en minuscules dans FR-33 (« Plafond de dépense » cohérent). « Configuration inapplicable » vs « marquée inapplicable » : même sens. Dérive faible.
- **FR-16** : la balise `[ASSUMPTION]` figure dans une liste de conséquences testables ; l'hypothèse porte sur l'interprétation de « tarif multiplié par 5 » du cadrage. À vérifier à la source avant de coder le refus.
- **Doublon de règle** : FR-3 (4e puce) et FR-37 énoncent la même règle de Famille ; garder une définition et un renvoi.
- **FR-42 à FR-51** : une seule ligne chacune, conforme à l'intention « niveau capacité » ; aucun problème, mais la FR-43 contient une phrase mal formée (« routeur par requête avec bornes figé, routeur, oracle ») à corriger.
