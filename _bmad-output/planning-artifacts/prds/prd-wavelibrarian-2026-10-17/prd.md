---
title: WaveLibrarian
status: final
created: 2026-10-17
updated: 2026-10-17
---

# PRD : WaveLibrarian

## 0. Objet du document

Ce PRD s'adresse à Anaël (porteur et seul opérateur), à l'architecte et aux agents de développement qui implémenteront le banc en autonomie. Il couvre les livrables 1 (conviction mesurée) et 2 (outil de mission) du cadrage `docs/cadrage.md`, qui reste la source des hypothèses H1 à H17, des corpus, des sources et des décisions D1 à D14. La plateforme pédagogique (livrable 3) est une extension de WaveStack décrite dans un PRD séparé ; la publication (livrable 4) n'est traitée qu'au travers des exigences de reproductibilité.

Structure : vocabulaire fixé par le Glossaire (§3), fonctionnalités regroupées avec exigences numérotées FR-1 à FR-N (§4), exigences transverses (§5), périmètre MVP (§7). Les choix techniques (bibliothèques, formats, modèles) sont dans `addendum.md`. Les déductions non confirmées portent la balise `[ASSUMPTION]` et sont indexées au §11.

Le **MVP** correspond au premier run de développement autonome : socle, phase 1 (jeu d'évaluation, juges, baselines) et phase 2 (architectures texte du niveau 1). Les FR des phases suivantes sont décrites au niveau capacité et marquées `[Post-MVP]`. Les FR-52 à FR-55, ajoutées après revue, font partie du MVP.

**Lecture obligatoire** pour l'architecte et les agents de développement : `docs/cadrage.md` (hypothèses H1 à H17, décisions D1 à D14, plan d'expérience par niveaux, phasage). Les valeurs par défaut du MVP (modèles, seuils, paramètres) sont regroupées au §7.3.

## 1. Vision

WaveLibrarian est un banc de mesure qui compare les architectures de recherche documentaire IA (RAG naïf et hybride, GraphRAG, LLM Wiki, PageIndex, recherche agentique, CAG…) sur des corpus aux profils contrastés, et qui restitue pour chacune la qualité des réponses, le coût, la latence, l'empreinte énergétique et une lecture conformité-sécurité. Il remplace les avis de blog et les chiffres d'éditeurs par des mesures appariées, avec intervalles de confiance et juges calibrés sur des annotations humaines.

Le banc sert deux usages. En recherche, il confirme ou corrige chaque branche d'un arbre de décision « profil de corpus × type de question → architecture et modèles recommandés », qui alimente les slides de conviction. En mission, le même code profile le corpus d'un client, génère un jeu d'évaluation, cherche une configuration très fonctionnelle sous un budget borné en euros et en heures, et produit un rapport lisible par une direction de DSI.

Le banc est conçu pour être piloté par un seul opérateur, entièrement en ligne de commande et en fichiers versionnés, avec un plafond de dépense strict : chaque euro et chaque kWh dépensé est tracé et attribué à un poste (indexation, mise à jour, requête).

## 2. Utilisateurs

### 2.1 Jobs To Be Done

- **Anaël, chercheur-consultant** : trancher les hypothèses H1 à H17 par des mesures reproductibles, pour défendre une conviction devant des pairs et des clients sans dépendre des chiffres d'éditeurs.
- **Anaël, en mission** : recommander à une DSI une architecture argumentée (qualité, coût, énergie, conformité) sur son propre corpus, en quelques jours et sous un budget annoncé.
- **Agent de développement Claude Code** : implémenter un composant ou une architecture de façon isolée, avec des critères de réussite vérifiables sans réseau ni clé d'API.

### 2.2 Hors cible (v1)

- Utilisateurs non techniques : la plateforme no code relève de WaveStack (livrable 3).
- Production en ligne : le banc n'est pas un service de recherche documentaire à exploiter en continu, même si une architecture configurée peut être exposée en MCP `[Post-MVP]`.
- Équipes multiples : pas de gestion de comptes, de droits applicatifs ni de travail concurrent.

### 2.3 Parcours clés

- **UJ-1. Anaël prépare le jeu d'évaluation d'un corpus.** Il déclare un corpus dans un fichier de configuration, lance le profilage puis la génération de questions. Il relit le fichier de questions dans son éditeur, corrige ou rejette, écrit à la main les pièges et les synthèses, lance la validation qui vérifie chaque ancrage, puis le filtre closed-book. Il gèle le jeu : la partie test devient non modifiable et son empreinte est enregistrée. **Cas limite** : une question validée cite une page qui n'existe pas dans le document ; la validation la refuse et indique laquelle.
- **UJ-2. Anaël compare des architectures sur un corpus.** Il écrit une expérience YAML listant plusieurs configurations (baselines et architectures), lance l'exécution sur la partie développement avec un plafond de dépense. Les index déjà construits sont réutilisés. Il ouvre le rapport : scores par critère et par type de question, intervalles de confiance, comparaisons appariées, fronts de Pareto qualité × coût et qualité × énergie, questions contaminées à part. **Cas limite** : le plafond est atteint en cours d'exécution ; l'exécution s'arrête proprement, les résultats partiels sont conservés et la reprise ne refait pas les appels déjà payés.
- **UJ-3. Anaël calibre les juges.** Il annote 50 à 100 réponses dans un fichier, un collègue en annote une partie. La commande de calibration calcule l'accord juge-humain et l'accord entre annotateurs, passe chaque juge au moins cinq fois et écarte ceux sous le seuil. Les rapports suivants n'utilisent que les juges retenus.
- **UJ-4. Un agent de développement ajoute une architecture.** Il implémente l'interface d'architecture, l'enregistre au registre, écrit les tests sur le mini-corpus fictif avec le faux LLM et le faux embedder. Le contrôle rapide et les tests passent sans réseau. L'architecture devient sélectionnable dans une expérience sans autre modification.
- **UJ-5. `[Post-MVP]` Anaël mène une mission.** Il pointe l'outil sur le corpus du client (exécution 100 % locale si les données sont sensibles), obtient le profil du corpus et la position sur la matrice de conviction, fait valider les questions par le métier, lance l'optimiseur sous un budget en euros et en heures, et remet un rapport comparatif avec une fiche conformité-sécurité par architecture.

## 3. Glossaire

- **Corpus** : ensemble de Documents déclaré sous un identifiant unique, avec ses métadonnées (langue, licence, publiable ou non).
- **Document** : fichier source d'un Corpus, identifié par une empreinte de son contenu. Un Document contient des Ancrages.
- **Ancrage** : localisation stable dans un Document (document + page pour un PDF, document + chemin de titres pour un texte structuré), indépendante du Découpage.
- **Profil de corpus** : ensemble des Descripteurs calculés pour un Corpus ; il positionne le Corpus sur la Matrice de conviction.
- **Descripteur** : mesure automatique d'un Corpus (volume, longueur moyenne, profondeur de structure, densité de liens, volatilité, part tabulaire, part visuelle, langue).
- **Passage** : unité de texte produite par un Découpage et indexée ; un Passage recouvre un ou plusieurs Ancrages.
- **Découpage** : stratégie qui transforme les Documents parsés en Passages.
- **Composant** : implémentation interchangeable d'une interface (QueryRewriter, Parser, Chunker, Embedder, VectorStore, GraphStore, Retriever, Reranker, ContextBuilder, Decider, Generator, Judge), enregistrée sous un nom au Registre.
- **Registre** : catalogue des Composants et des Architectures disponibles, consulté par la Configuration.
- **Architecture** : manière de répondre à une Question à partir d'un Corpus (Baseline ou architecture du niveau 1), qui assemble des Composants et expose les opérations indexer, mettre à jour et répondre.
- **Baseline** : Architecture de référence du niveau 0 (sans contexte, contexte long, BM25 seul).
- **Configuration** : choix complet d'une Architecture et de ses Composants et paramètres, décrit en YAML.
- **Expérience** : fichier YAML qui associe un Corpus, un Jeu d'évaluation, une ou plusieurs Configurations, un Panel de juges et un Plafond de dépense.
- **Exécution** : passage d'une Expérience, identifiée par un identifiant unique, qui produit des Traces, des Réponses et un Rapport.
- **Question** : entrée du Jeu d'évaluation, avec son Type de question, sa Réponse de référence et ses Ancrages de référence.
- **Type de question** : factuelle, multi-sauts, globale, comparaison, agrégation numérique, temporelle, sans réponse, piège de connaissance, visuelle ; plus les attributs « suivi de conversation » et « interlingue ».
- **Jeu d'évaluation** : ensemble des Questions d'un Corpus, réparti en partie développement et partie test, qui devient immuable une fois Gelé.
- **Gel** : opération qui fige un Jeu d'évaluation et enregistre son empreinte.
- **Question contaminée** : Question réussie sans contexte par au moins un modèle du Filtre closed-book.
- **Filtre closed-book** : passage de chaque Question par deux ou trois LLM sans aucun contexte.
- **Réponse** : sortie d'une Architecture pour une Question : texte, Citations, Passages retrouvés et Trace.
- **Citation** : référence d'une Réponse vers un Ancrage.
- **Juge** : Composant qui note une Réponse sur un Critère.
- **Critère** : exactitude, complétude, fidélité aux sources, citations correctes, abstention correcte ; chaque Critère est noté séparément.
- **Panel de juges** : deux ou trois Juges de familles de modèles différentes.
- **Famille de modèles** : fournisseur ou lignée d'un modèle (Claude, Qwen, Mistral, Gemma…), utilisée pour la règle d'exclusion des Juges.
- **Calibration** : mesure de l'accord entre Juges et Annotations humaines, et de la stabilité des Juges.
- **Annotation humaine** : verdict d'une personne sur un Critère d'une Réponse.
- **Trace** : enregistrement d'un appel (modèle, tokens en entrée, en sortie et en cache, coût, latence, énergie, étape, Poste de coût).
- **Poste de coût** : indexation, mise à jour ou requête.
- **Grille tarifaire** : prix datés par modèle, fournisseur et région.
- **Plafond de dépense** : montant maximal engageable par Exécution et sur une période ; il bloque tout appel qui le dépasserait.
- **Cache d'index** : stockage des index déjà construits, indexé par la combinaison Corpus × Parser × Découpage × Embedder × VectorStore.
- **Cache de réponses LLM** : stockage des réponses de modèles indexé par la requête exacte, qui évite de repayer un appel identique.
- **Rapport** : synthèse d'une Exécution (scores, intervalles de confiance, comparaisons appariées, fronts de Pareto).
- **Matrice de conviction** : correspondance « Profil de corpus × Type de question → Architecture et modèles recommandés », issue des mesures.
- **Mini-corpus fictif** : Corpus inventé et publiable livré dans le dépôt, avec son Jeu d'évaluation de référence, qui sert aux tests de bout en bout.
- **Condition contexte parfait** : Exécution où le Generator reçoit les Ancrages de référence au lieu des Passages retrouvés.
- **Faux LLM / faux embedder** : Composants déterministes sans réseau qui remplacent les modèles dans les tests (contrat en FR-52).
- **Niveau** : étape du plan d'expérience du cadrage : 0 Baselines, 1 Architectures, 2 Composants, 3 couche de décision, 4 formats, 5 extensions.
- **Catalogue de modèles** : fichier qui déclare chaque modèle utilisable : fournisseur, Famille de modèles, fenêtre de contexte, tokenizer, prix (Grille tarifaire), support du cache de prompt.
- **Qualité** : pour les fronts de Pareto, le point mort et la sélection d'un Niveau, taux d'exactitude d'une Configuration (Critère exactitude, abstentions correctes comptées comme exactes). Un front supplémentaire est produit par Critère ; aucun Critère n'est pondéré avec un autre.
- **Qualité égale** : la différence appariée de Qualité entre deux Configurations n'est pas significative (FR-39), ou la première est significativement supérieure pour « égale ou supérieure ».
- **Coût de possession** : coût des ressources locales : énergie mesurée × prix du kWh, plus amortissement du matériel (prix ÷ heures de vie × durée de calcul), plus stockage ; paramètres déclarés et datés.
- **Scénario de mise à jour** : suite reproductible d'ajouts, de modifications et de suppressions de Documents appliquée à un Corpus indexé.
- **Fraîcheur** : part des Questions dépendant d'un Document mis à jour auxquelles une Architecture répond selon la version à jour.
- **Palier de volume** : sous-corpus emboîté d'un Corpus (par exemple 100 ⊂ 500 ⊂ 2 000 Documents), qui sert l'axe volume (H3, H11).

## 4. Fonctionnalités

### 4.1 Expériences, configuration et registre

**Description :** tout ce que le banc exécute est décrit dans des fichiers YAML versionnés. Une Expérience référence un Corpus, un Jeu d'évaluation, des Configurations, un Panel de juges et un Plafond de dépense. Chaque Composant est une clé de configuration résolue par le Registre ; toute combinaison cohérente est exécutable, une combinaison incohérente est refusée avant le moindre appel. Réalise UJ-2 et UJ-4.

#### FR-1 : Expérience déclarative

Anaël peut décrire une Expérience dans un fichier YAML et l'exécuter par une seule commande.

**Conséquences (testables) :**
- Un fichier contenant une clé inconnue ou une valeur hors du type attendu est refusé ; le message cite le chemin de la clé fautive.
- L'Exécution enregistre une copie de l'Expérience résolue (valeurs par défaut comprises) et son empreinte à côté des résultats.
- Deux Configurations d'une même Expérience peuvent différer d'un seul Composant ; le Rapport les compare deux à deux.

#### FR-2 : Registre de composants et d'architectures

Un agent de développement peut ajouter un Composant ou une Architecture en implémentant son interface et en l'enregistrant sous un nom, sans modifier le code d'orchestration. Réalise UJ-4.

**Conséquences (testables) :**
- Une commande liste les Composants et Architectures enregistrés, avec leurs paramètres et leur description.
- Un nom inconnu dans une Configuration produit une erreur qui liste les noms disponibles pour cette interface.

#### FR-3 : Matrice de compatibilité

Le banc refuse une Configuration incohérente avant tout appel de modèle.

**Conséquences (testables) :**
- Une Configuration qui réutilise explicitement un index existant avec un Embedder de dimension différente est refusée.
- Une Architecture qui exige la recherche hybride associée à un VectorStore qui ne la supporte pas est refusée.
- Une Baseline contexte long sur un Corpus qui dépasse la fenêtre du modèle est marquée « inapplicable » dans le Rapport au lieu d'échouer.
- Un Juge de la même Famille de modèles que le Generator évalué est refusé.

#### FR-4 : Reproductibilité

Anaël peut rejouer une Exécution et obtenir les mêmes résultats de recherche.

**Conséquences (testables) :**
- Toute source d'aléa est contrôlée par une graine déclarée dans l'Expérience.
- Rejouer une Exécution avec le même Cache d'index et le même Cache de réponses LLM produit des Passages retrouvés et des Réponses identiques, sans aucun appel payant. Hors cache, seule l'identité des Passages retrouvés est garantie ; les Réponses de LLM peuvent varier.
- La liste des modèles utilisés est datée et figée dans l'Expérience ; le Rapport l'affiche.

### 4.2 Corpus, ingestion et profilage

**Description :** un Corpus est un dossier de Documents déclaré dans un fichier de métadonnées. L'ingestion convertit chaque Document en texte structuré en conservant ses Ancrages ; le profilage calcule les Descripteurs. Réalise UJ-1.

#### FR-5 : Déclaration d'un corpus

Anaël peut déclarer un Corpus par un identifiant, un chemin, une langue, une licence et un indicateur « publiable ».

**Conséquences (testables) :**
- Chaque Document reçoit un identifiant dérivé de l'empreinte de son contenu ; renommer un fichier sans changer son contenu ne change pas son identifiant.
- Les formats acceptés au MVP sont Markdown, texte, HTML et PDF ; un autre format est signalé et ignoré, sans arrêter l'ingestion.
- Chaque Document peut porter un niveau de sensibilité (texte libre) et une liste de profils de droits autorisés (liste de chaînes) en métadonnées, sans effet au MVP (préparation de D7 et des tests de droits `[Post-MVP]`).
- Un Corpus sous licence restrictive ne peut pas être placé dans le dépôt : son chemin est hors du dépôt ou dans un dossier ignoré par git.

#### FR-6 : Ingestion avec ancrages

Le banc convertit chaque Document en texte structuré et conserve ses Ancrages.

**Conséquences (testables) :**
- Pour un PDF, chaque bloc de texte connaît sa page ; pour un Markdown ou un HTML, son chemin de titres.
- Un Ancrage de référence peut être retrouvé dans le texte parsé ; la validation du Jeu d'évaluation (FR-11) s'appuie sur cette fonction.
- Le résultat de l'ingestion est mis en cache par Document et par Parser.

#### FR-7 : Profilage du corpus

Anaël peut obtenir le Profil de corpus d'un Corpus par une commande.

**Conséquences (testables) :**
- Le profil contient : nombre de Documents, nombre de tokens, longueur moyenne, profondeur de structure (profondeur maximale et moyenne de la hiérarchie de titres), densité de liens (part des Documents qui partagent au moins une entité nommée avec un autre), part tabulaire (part des tokens situés dans des tableaux), part visuelle (nombre d'images par Document), langue dominante.
- Les tokens du profil sont comptés avec un tokenizer de référence unique, indiqué dans le profil ; la comparaison à la fenêtre d'un modèle (FR-3) utilise le tokenizer déclaré pour ce modèle au Catalogue de modèles, ou le tokenizer de référence majoré de 20 % à défaut.
- L'extraction d'entités nommées utilisée pour la densité de liens fonctionne sans réseau et sans LLM.
- La volatilité est déclarée en métadonnée du Corpus au MVP `[ASSUMPTION : calculée à partir de l'historique des versions en Post-MVP]`.
- Le profil est écrit en JSON et inclus dans le Rapport.

#### FR-8 : Mini-corpus fictif

Le dépôt contient un Mini-corpus fictif publiable qui permet de tester toute la chaîne sans réseau.

**Conséquences (testables) :**
- Environ 20 Documents inventés (univers contrefactuel cohérent), en Markdown et en PDF, dont au moins un long document structuré avec tableaux, plusieurs documents fortement liés par des entités partagées, deux versions contradictoires d'un même document et au moins deux Documents en anglais (le reste en français).
- Il contient aussi, hors du Corpus de base : un Scénario de mise à jour (FR-53) d'au moins un ajout, une modification et une suppression ; un document sentinelle aux faits uniques ; un document piégé contenant une injection indirecte ; des profils de droits sur au moins deux Documents. Ces éléments préparent FR-47 sans être exploités au MVP au-delà du Scénario de mise à jour.
- La taille totale du Corpus de base reste sous 60 000 tokens, pour que la Baseline contexte long et le CAG s'exécutent sous la règle des 100 000 tokens (FR-16).
- Un Jeu d'évaluation de référence d'au moins 40 Questions, rédigées par l'agent de développement (origine « modèle », statut « validée » après contrôle automatique des Ancrages, à relire par Anaël), couvrant tous les Types de question sauf « visuelle » et « agrégation numérique », avec au moins deux questions de suivi, deux questions interlingues et trois questions liées au Scénario de mise à jour.
- Le Mini-corpus fictif et son Jeu d'évaluation sont Gelés et servent aux tests de bout en bout de chaque Architecture ; sur cette taille, les statistiques ne valident que la plomberie.

### 4.3 Jeu d'évaluation

**Description :** le Jeu d'évaluation est construit et gelé avant tout pipeline. Les Questions sont générées par un LLM fort, puis validées ou corrigées par Anaël dans des fichiers éditables ; les pièges et les synthèses sont écrits à la main. Réalise UJ-1.

#### FR-9 : Format des questions

Chaque Question est un enregistrement d'un fichier YAML éditable à la main (un fichier par Corpus).

**Conséquences (testables) :**
- Champs : identifiant stable, Type de question, texte, langue, Réponse de référence, forme de la Réponse de référence (courte ou libre, voir FR-36), Ancrages de référence (zéro pour « sans réponse »), statut (générée, validée, corrigée, rejetée), partie (développement ou test), indicateur Question contaminée, historique de conversation pour les questions de suivi, origine (« humain » ou « modèle » avec le nom du modèle ou de l'agent), version du Document visée pour les Questions liées au Scénario de mise à jour.
- Un fichier invalide est refusé avec le numéro de l'enregistrement et le champ en cause.

#### FR-10 : Génération de questions

Anaël peut générer des Questions candidates pour un Corpus, avec une répartition cible par Type de question.

**Conséquences (testables) :**
- Chaque Question générée porte au moins un Ancrage de référence vérifié (FR-6), sauf pour le type « sans réponse ».
- La génération respecte le Plafond de dépense et passe par le Cache de réponses LLM.
- Les Questions générées arrivent avec le statut « générée » et ne sont jamais utilisées dans une Exécution avant validation.

#### FR-11 : Validation humaine

Anaël peut lister, valider, corriger ou rejeter des Questions en éditant le fichier, puis contrôler le résultat par une commande.

**Conséquences (testables) :**
- La commande de contrôle affiche le nombre de Questions par statut et par Type de question, ainsi que l'écart à la cible de D1 (150 Questions par Corpus).
- Elle refuse toute Question validée dont un Ancrage n'est pas retrouvé dans le Document.

#### FR-12 : Filtre closed-book

Anaël peut passer le Jeu d'évaluation au Filtre closed-book.

**Conséquences (testables) :**
- Chaque Question est posée sans contexte à deux ou trois modèles configurés ; une Question réussie par au moins un modèle est marquée Question contaminée, avec le nom du modèle.
- « Réussie » signifie : correspondance exacte normalisée pour une Réponse de référence courte ; sinon verdict « exact » d'un Juge du Panel d'une autre Famille que le modèle testé. Le filtre peut tourner avant la Calibration ; il est relancé si la Calibration exclut le Juge utilisé.
- Les Questions « sans réponse » ne passent pas le filtre.
- Le Rapport présente les scores des Questions contaminées séparément des autres.

#### FR-13 : Gel et séparation développement / test

Anaël peut Geler un Jeu d'évaluation, qui est alors réparti en partie développement et partie test, stratifiées par Type de question.

**Conséquences (testables) :**
- Le Gel enregistre l'empreinte du Jeu d'évaluation ; toute Exécution sur un Jeu d'évaluation modifié après Gel est refusée.
- La partie test n'est utilisée que si l'Exécution le demande explicitement ; le Rapport indique la partie utilisée.
- La répartition est déterministe pour une graine donnée ; proportion par défaut 40 % développement, 60 % test, configurable.

### 4.4 Architectures

**Description :** chaque Architecture expose trois opérations : indexer un Corpus, appliquer une mise à jour (ajout, modification, suppression de Documents) et répondre à une Question, éventuellement avec un historique de conversation. Une Réponse contient le texte, les Citations, les Passages retrouvés classés avec leurs scores et la Trace de chaque étape. Les Architectures sont implémentées dans l'ordre ci-dessous, du simple au complexe ; chacune laisse le banc utilisable. Réalise UJ-2 et UJ-4.

#### FR-14 : Contrat d'architecture

Toute Architecture respecte le même contrat d'entrée et de sortie.

**Conséquences (testables) :**
- Chaque Architecture passe une suite de tests de conformité commune sur le Mini-corpus fictif avec le faux LLM et le faux embedder : indexation, réponse avec au moins une Citation valide sur une question factuelle, abstention possible, mise à jour.
- Chaque Citation désigne un Ancrage existant.
- Une Architecture peut déclarer qu'elle ne supporte pas la mise à jour incrémentale ; la mise à jour déclenche alors une réindexation complète, comptée au poste « mise à jour ».

#### FR-15 : Abstention

Toute Architecture peut répondre qu'une information est absente du Corpus.

**Conséquences (testables) :**
- La Réponse porte un indicateur d'abstention, distinct du texte, que le Critère « abstention correcte » exploite.

#### FR-16 : Baselines

Anaël peut exécuter trois Baselines : sans contexte, contexte long (tout le Corpus dans le prompt) et BM25 seul.

**Conséquences (testables) :**
- La Baseline contexte long est « inapplicable » si le Corpus dépasse la fenêtre du modèle (FR-3).
- Un modèle dont le Catalogue déclare un palier tarifaire au-delà d'un seuil de prompt (Claude Haiku 5.5 : tarif multiplié par 5 au-delà de 100 000 tokens) est refusé en contexte long et en CAG si le prompt estimé dépasse ce seuil.
- La Baseline sans contexte n'a pas de métriques de recherche ; la Baseline contexte long a des métriques de recherche calculées sur ses Citations.

#### FR-17 : Condition contexte parfait

Anaël peut exécuter toute Configuration en Condition contexte parfait, pour isoler la qualité du Generator.

**Conséquences (testables) :**
- Le Generator reçoit exactement le texte des Ancrages de référence de la Question, dans un ordre fixe, et aucun Passage retrouvé ; pour une Question « sans réponse », il reçoit un contexte vide.
- Le Rapport étiquette ces résultats « contexte parfait » et ne les mêle pas aux autres.

#### FR-18 : RAG naïf

Découpage, embedding, recherche dense des k meilleurs Passages, génération avec Citations.

**Conséquences (testables) :**
- k est un paramètre (défaut 5) ; la Réponse expose exactement k Passages retrouvés, classés par score décroissant.
- Le prompt de génération contient ces k Passages avec leurs Ancrages, et seules ces Ancrages peuvent être cités ; une Citation hors de cet ensemble est retirée et comptée en erreur dans la Trace.

#### FR-19 : RAG hybride

Recherche BM25 et dense, fusion, puis reranker optionnel ; chaque étage s'active séparément pour que le Rapport isole l'effet de chacun (H1).

**Conséquences (testables) :**
- Fusions disponibles : RRF et fusion pondérée réglable.
- La latence du reranker apparaît comme une étape distincte de la Trace.

#### FR-20 : HyDE

Génération d'une réponse hypothétique dont l'embedding sert à la recherche dense.

**Conséquences (testables) :**
- La génération de la réponse hypothétique est une étape distincte de la Trace, imputée au poste « requête ».
- Le vecteur de recherche est celui de la réponse hypothétique (option : moyenne avec celui de la Question) ; la réponse hypothétique n'est jamais citée.

#### FR-21 : Corrective RAG

Évaluation de la pertinence des Passages retrouvés par un Decider ; sous un seuil, reformulation et nouvelle recherche, ou abstention. Le nombre de boucles est borné par la Configuration.

**Conséquences (testables) :**
- Le Decider attribue à chaque Passage un score de pertinence entre 0 et 1 ; seuil par défaut 0,5, nombre de boucles par défaut 2.
- Si aucun Passage n'atteint le seuil, la Question est reformulée et une nouvelle recherche est émise, au plus le nombre de boucles autorisé ; ensuite, l'Architecture s'abstient.
- Les Passages sous le seuil sont exclus du contexte de génération ; chaque boucle est tracée.
- Au MVP, le Decider est un LLM avec un prompt de notation ; les Deciders spécialisés arrivent au Niveau 3.

#### FR-22 : CAG

Le Corpus entier est préchargé dans le cache de prompt du fournisseur ; les Questions réutilisent ce cache.

**Conséquences (testables) :**
- Les tokens en cache sont tracés séparément ; le coût de préchargement est imputé au poste « indexation ».
- Inapplicable si le Corpus dépasse la fenêtre ou si le Catalogue de modèles ne déclare pas de cache de prompt pour le modèle (au MVP, seule l'API Anthropic en offre un).
- Une seconde Question sur le même Corpus montre des tokens en cache non nuls dans sa Trace.

#### FR-23 : RAPTOR

Construction d'un arbre de résumés par regroupement récursif des Passages ; recherche sur tous les niveaux de l'arbre.

**Conséquences (testables) :**
- L'arbre a au moins un niveau de résumés au-dessus des Passages ; chaque nœud de résumé référence ses enfants, et donc les Ancrages des Passages qu'il résume.
- La recherche porte sur l'ensemble des nœuds (« arbre aplati ») ; les Passages retrouvés peuvent venir de niveaux différents, et le niveau est exposé.
- Une Citation d'un nœud de résumé est convertie en Citations vers les Ancrages de ses Passages feuilles.
- Paramètres par défaut : taille cible des groupes 5 à 10 nœuds, profondeur maximale 3 ; les résumés sont imputés au poste « indexation ».

#### FR-24 : PageIndex

Construction d'un index hiérarchique (table des matières) de chaque Document ; navigation par le LLM dans cet arbre pour choisir les sections à lire.

**Conséquences (testables) :**
- L'arbre de chaque Document suit sa hiérarchie de titres (ou ses pages pour un PDF sans titres) ; chaque nœud porte un résumé court et son Ancrage ; l'arbre est persistant dans le Cache d'index.
- À la requête, le LLM choisit des nœuds à partir des titres et résumés, sans recherche vectorielle ; chaque nœud ouvert est tracé, dans la limite de 8 nœuds lus par Question (défaut).
- Les Passages retrouvés sont les sections lues, avec leurs Ancrages.

#### FR-25 : LLM Wiki

Compilation du Corpus en pages de wiki par un LLM, puis réponse à partir du wiki.

**Conséquences (testables) :**
- Chaque page du wiki référence les Ancrages dont elle est issue ; les Citations d'une Réponse remontent à ces Ancrages.
- Les passes de maintenance du wiki après une mise à jour sont tracées au poste « mise à jour » comme coût récurrent.
- Une mesure de fidélité du wiki aux sources est produite (affirmations du wiki vérifiées contre leurs Ancrages) `[ASSUMPTION : par un Juge, sur un échantillon de pages]`.

#### FR-26 : Recherche agentique

Un agent dispose d'outils de recherche lexicale, de lecture de Document et de liste du Corpus, et itère jusqu'à répondre.

**Conséquences (testables) :**
- Le nombre d'étapes et la dépense par Question sont bornés par la Configuration (défaut : 8 étapes, 0,05 $ par Question) ; au-delà, l'agent s'abstient.
- Les outils sont en lecture seule et limités au Corpus.
- Les Passages retrouvés sont les extraits lus par l'agent, dans l'ordre de lecture ; les métriques de recherche se calculent sur eux.

#### FR-27 : GraphRAG et variantes

Extraction d'entités et de relations, construction d'un graphe et de rapports de communautés ; recherche locale et recherche globale ; variantes LazyGraphRAG et LightRAG.

**Conséquences (testables) :**
- Chaque variante est une Architecture distincte du Registre.
- Le Rapport ventile les résultats par Type de question (H2) et sépare le coût d'indexation et de mise à jour (H13).
- `[ASSUMPTION]` Implémentations maison simplifiées, conformes aux articles, plutôt que les bibliothèques de référence ; une bibliothèque peut entrer plus tard comme Architecture comparée (D4).

#### FR-28 : Cache d'index

Une indexation déjà réalisée pour une combinaison Corpus × Parser × Découpage × Embedder × VectorStore (et, pour les Architectures à contenu dérivé, leurs paramètres et le modèle utilisé) n'est jamais refaite.

**Conséquences (testables) :**
- La seconde Exécution d'une même Configuration ne déclenche aucun appel d'indexation ; la Trace indique « cache ».
- Une mise à jour du Corpus produit une nouvelle entrée de cache sans écraser la précédente.

### 4.5 Mesure : traces, FinOps, GreenOps

**Description :** chaque appel de modèle, d'embedding ou de reranker produit une Trace attribuée à un Poste de coût. Les coûts viennent d'une Grille tarifaire datée ; l'énergie est mesurée en local et estimée pour les API. Un Plafond de dépense bloque tout dépassement. Réalise UJ-2.

#### FR-29 : Traces

Chaque appel produit une Trace avec : étape, modèle, fournisseur, tokens en entrée, en sortie et en cache, coût, latence, énergie estimée ou mesurée, Poste de coût, identifiant d'Exécution, de Configuration et de Question.

**Conséquences (testables) :**
- Les Traces sont émises au format OpenTelemetry et écrites dans un fichier local par Exécution ; l'envoi vers un outil de traces externe est une option de configuration.
- La somme des coûts des Traces d'une Exécution égale le coût total affiché par le Rapport.
- Pour un appel d'API, les tokens tracés sont ceux renvoyés par le fournisseur ; le coût est recalculé à partir de la Grille tarifaire.

#### FR-30 : Grille tarifaire datée

Les prix par modèle, fournisseur et région sont déclarés dans un fichier avec leur date de relevé.

**Conséquences (testables) :**
- Un modèle d'API sans prix déclaré est refusé à la validation de l'Expérience. Un modèle local n'a pas de prix au token : son coût est un Coût de possession (FR-31).
- Chaque prix est déclaré dans la devise du fournisseur ; le Rapport convertit tout en euros avec un taux de change daté déclaré dans la grille, et affiche la date de la grille.
- Les tarifs en lot (API batch) et en cache sont déclarés séparément quand le fournisseur les propose.

#### FR-31 : Postes de coût séparés

Le Rapport présente coût et énergie séparément pour l'indexation initiale, les mises à jour et les requêtes, ainsi que le coût par requête et pour 1 000 requêtes, et le débit (Questions par minute).

**Conséquences (testables) :**
- Le coût de chaque poste additionne le coût des appels d'API et le Coût de possession des calculs locaux ; les paramètres (prix du kWh, prix et durée de vie du matériel, coût du stockage) sont déclarés et datés dans la configuration.
- Le point mort (volume de requêtes à partir duquel une Architecture à indexation coûteuse devient rentable) n'est calculé que si sa Qualité est égale ou supérieure (au sens du Glossaire) à celle de l'Architecture comparée ; sinon le Rapport l'indique explicitement.

#### FR-32 : Énergie

L'énergie est mesurée en local et estimée pour les appels d'API.

**Conséquences (testables) :**
- Le Rapport étiquette chaque valeur « mesurée » ou « estimée » et avertit que les deux périmètres ne se comparent pas terme à terme.
- L'équivalent CO2 utilise l'intensité carbone déclarée de la région d'exécution.

#### FR-33 : Plafond de dépense

Anaël fixe un Plafond de dépense par Exécution et un plafond cumulé sur une période, par fournisseur et dans la devise du fournisseur (D2 : 50 $/mois sur Anthropic, 50 €/mois sur Azure AI Foundry) ; aucun appel payant ne peut le dépasser.

**Conséquences (testables) :**
- Avant chaque appel payant, le coût maximal estimé (tokens d'entrée comptés par le tokenizer du Catalogue de modèles majorés de 20 %, plus le maximum de tokens de sortie demandé) est comparé au solde restant ; si le solde est insuffisant, l'appel n'est pas émis et l'Exécution s'arrête proprement avec un statut « plafond atteint ».
- Après l'appel, la dépense réelle (tokens renvoyés par le fournisseur) remplace l'estimation dans le registre.
- La dépense cumulée est persistée dans un registre local qui survit aux redémarrages ; le plafond de période s'applique à toutes les Exécutions.
- Les résultats partiels d'une Exécution arrêtée sont conservés et la reprise ne refait que les appels manquants.
- Le plafond par défaut du premier run autonome est de 5 $ sur l'API Anthropic.

#### FR-34 : Cache de réponses LLM

Un appel identique (modèle, paramètres, messages) déjà payé est servi depuis le Cache de réponses LLM.

**Conséquences (testables) :**
- Un appel servi depuis le cache a un coût nul et l'indique dans la Trace ; le Rapport distingue le coût réel du coût sans cache.
- Les Juges à verdicts multiples (FR-37) contournent le cache par un identifiant de passe explicite.

### 4.6 Juges et métriques

**Description :** les métriques de recherche sont calculées automatiquement sur les Ancrages de référence. Les métriques de réponse sont notées par un Panel de juges multi-familles, calibré sur des Annotations humaines. Chaque Critère est noté séparément, sans score global. Réalise UJ-2 et UJ-3.

#### FR-35 : Métriques de recherche

Le banc calcule rappel@k, MRR et nDCG des Passages retrouvés par rapport aux Ancrages de référence.

**Conséquences (testables) :**
- Un Passage est pertinent s'il recouvre un Ancrage de référence, quel que soit le Découpage.
- Les métriques sont calculées par Question puis agrégées par Type de question.
- Pour les Architectures sans liste classée de Passages (LLM Wiki, recherche agentique, contexte long, CAG), les métriques portent sur les Ancrages effectivement fournis au Generator ou cités, et le Rapport indique la méthode utilisée.

#### FR-36 : Métriques de réponse

Chaque Réponse est notée sur chaque Critère par chaque Juge du Panel ; la correspondance exacte remplace le Juge pour le Critère exactitude quand la Réponse de référence est de forme « courte ».

**Conséquences (testables) :**
- Une Réponse de référence « courte » est un nombre, une date ou une expression d'au plus 5 mots ; la correspondance exacte compare après normalisation (casse, accents, ponctuation, format des nombres) et recherche la référence dans la Réponse.
- Chaque Juge rend pour chaque Critère un verdict binaire (oui / non) et une justification courte ; l'abstention correcte est calculée sans Juge à partir de l'indicateur d'abstention et du Type « sans réponse ».
- Le Critère « citations correctes » est calculé automatiquement à partir des Citations et des Ancrages de référence.
- Aucun score global n'est calculé.

#### FR-37 : Panel de juges et règle de famille

Le Panel de juges comprend deux ou trois Juges de Familles de modèles différentes ; un Juge ne note jamais une Réponse produite par un modèle de sa Famille.

**Conséquences (testables) :**
- La règle est vérifiée à la validation de l'Expérience (FR-3), à partir de la Famille déclarée pour chaque modèle au Catalogue de modèles.
- Le verdict du Panel sur un Critère est la majorité des Juges admissibles ; en cas d'égalité, le verdict est « non » et la Question est signalée.
- Un rôle « juge de calibration » distinct, plus coûteux, peut être déclaré : il ne note que les Réponses doublement annotées (FR-38).
- Au MVP, faute de clé Azure AI Foundry, le Panel associe des modèles locaux de familles différentes (via Ollama) et Claude Haiku 5.5, qui ne juge pas les Réponses de modèles Claude (§7.3).

#### FR-38 : Calibration des juges

Anaël peut calibrer le Panel à partir d'un fichier d'Annotations humaines.

**Conséquences (testables) :**
- La commande calcule le kappa juge-humain par Critère, le kappa entre deux annotateurs humains sur les Réponses doublement annotées, et le taux de verdicts instables sur au moins cinq passes par Juge.
- Un Juge sous le seuil de kappa (défaut 0,6, configurable) est marqué exclu ; les Rapports suivants l'ignorent et le mentionnent.
- Le fichier d'Annotations humaines est un fichier YAML par annotateur, référencé par identifiant de Réponse et Critère.

#### FR-39 : Statistiques appariées

Le Rapport fournit pour chaque métrique un intervalle de confiance par bootstrap, et pour chaque paire de Configurations une comparaison appariée (bootstrap apparié pour les scores continus, McNemar pour les verdicts binaires).

**Conséquences (testables) :**
- Valeurs par défaut : 2 000 rééchantillons, intervalle à 95 %, seuil de significativité 0,05, graine de l'Expérience.
- Les comparaisons ne portent que sur les Questions communes aux deux Configurations ; le nombre de Questions comparées est affiché.
- Sur des données synthétiques connues, l'intervalle et la p-valeur reproduisent les valeurs d'une implémentation de référence (tests unitaires).

### 4.7 Rapports et plan d'expérience

#### FR-40 : Rapport d'exécution

Chaque Exécution produit un Rapport lisible sans outil spécialisé.

**Conséquences (testables) :**
- Contenu : Expérience résolue, Profil de corpus, partie du Jeu d'évaluation utilisée, Panel de juges retenu, scores par Critère et par Type de question avec intervalles de confiance, comparaisons appariées, Questions contaminées à part, coûts et énergie par Poste de coût, latence p50 et p95, débit, Fraîcheur si un Scénario de mise à jour a été appliqué, résultats par Palier de volume si déclarés, fronts de Pareto Qualité × coût total, Qualité × énergie et Qualité × latence p95 (plus un front par Critère), Configurations inapplicables avec leur raison.
- Formats : Markdown, et données brutes en fichiers tabulaires pour toute réanalyse.

#### FR-41 : Plan d'expérience par niveaux

Anaël peut lancer un niveau du plan d'expérience à partir du front de Pareto du niveau précédent, en ne faisant varier qu'un facteur à la fois.

**Conséquences (testables) :**
- Le front de Pareto d'une Exécution peut être exporté comme liste de Configurations de départ d'une nouvelle Expérience.

### 4.8 Ajouts MVP après revue

#### FR-52 : Composants factices

Le banc fournit un Faux LLM et un faux embedder qui permettent d'exécuter toute Architecture sans réseau, avec des sorties déterministes.

**Conséquences (testables) :**
- Le faux embedder produit un vecteur de dimension fixe (défaut 64) dérivé de façon déterministe des mots du texte (hachage de sacs de mots), pour que deux textes qui partagent des mots soient proches.
- Le Faux LLM reconnaît le rôle de l'appel (génération, juge, réécriture, résumé, extraction d'entités, choix de nœuds, outil d'agent, notation de pertinence) par un marqueur placé dans le prompt par le Composant appelant, et renvoie une sortie au format attendu pour ce rôle.
- En génération, il répond par la première phrase du premier Passage du contexte et le cite ; avec un contexte vide, il s'abstient.
- Il déclare des tokens d'entrée et de sortie (nombre de mots), des tokens en cache quand le préfixe du prompt a déjà été vu, un coût calculé sur un prix fictif du Catalogue de modèles et une latence simulée nulle.
- Un mode scénarisé permet à un test d'imposer la sortie d'un appel donné (par exemple un score de pertinence faible pour exercer la boucle du Corrective RAG).

#### FR-53 : Scénario de mise à jour et Fraîcheur

Anaël peut appliquer un Scénario de mise à jour à un Corpus indexé et mesurer coût, durée et Fraîcheur pour chaque Architecture.

**Conséquences (testables) :**
- Un Scénario de mise à jour est un fichier qui liste des opérations ordonnées (ajout, modification, suppression) avec les fichiers concernés.
- Après application, un Document supprimé n'apparaît plus dans aucun Passage retrouvé ni aucune Citation pour les Questions liées au scénario.
- Le coût, l'énergie et la durée de la mise à jour sont imputés au poste « mise à jour » ; la Fraîcheur est calculée sur les Questions liées au Scénario.

#### FR-54 : Paliers de volume

Anaël peut déclarer des Paliers de volume emboîtés pour un Corpus et exécuter une Expérience sur chacun.

**Conséquences (testables) :**
- Les Paliers sont tirés de façon déterministe (graine) et emboîtés : tout Document d'un Palier figure dans les Paliers supérieurs.
- Les Documents qui portent les Ancrages de référence du Jeu d'évaluation appartiennent à tous les Paliers.
- Le Rapport présente les résultats par Palier ; au MVP, le mécanisme est testé sur le Mini-corpus fictif (par exemple 5 ⊂ 10 ⊂ 20 Documents).

#### FR-55 : Catalogue de modèles

Les modèles utilisables sont déclarés dans un Catalogue de modèles versionné.

**Conséquences (testables) :**
- Chaque entrée déclare : identifiant, fournisseur, Famille de modèles, fenêtre de contexte, tokenizer, prix et paliers tarifaires (FR-30), support du cache de prompt, local ou API.
- Un modèle absent du Catalogue est refusé à la validation de l'Expérience.

### 4.9 Conviction et mission `[Post-MVP]`

Fonctionnalités décrites au niveau capacité ; elles seront détaillées avant leur phase.

- **FR-42 : Sous-plan bases vectorielles (phase 3)** : référence force brute, rappel de l'index (0,7 à 1), quantification, sélectivité du filtrage, cycles de suppression et réinsertion, de 100 000 à plus d'un million de Passages (H14).
- **FR-43 : Composants de niveau 2 et couche de décision (phase 3)** : réécriture et décomposition de requête, découpages, embeddings, rerankers, ingénierie du contexte, Generator local ou cloud ; routeur par requête avec bornes figé, routeur, oracle (H6) ; Deciders contre juges LLM avec cascade (H7).
- **FR-44 : Matrice de conviction (phase 3)** : à partir des Rapports, production de la Matrice de conviction et de l'arbre de décision, chaque branche marquée confirmée, corrigée ou non mesurée.
- **FR-45 : Outils d'évaluation et de traces comparés** : adaptateurs Ragas, DeepEval, RAGChecker, etc., jugés sur leur accord avec les métriques de référence du banc ; tau de Kendall des classements (H15).
- **FR-46 : Formats et parsers (phase 4)**, **GenBI (phase 5)**, **multimodal (phase 6)**.
- **FR-47 : Fiche conformité-sécurité** : localisation des données par Composant, inventaire des copies et contenus dérivés, test d'effacement d'un document sentinelle, test de fuite avec deux profils de droits, documents piégés (PoisonedRAG), traçabilité, grille réglementaire (H12).
- **FR-48 : Optimiseur de configuration (phase 7)** : optimisation bayésienne multi-objectif sous budget en euros et en heures, multi-fidélité, démarrage à chaud par la Matrice de conviction, ordre tenant compte du Cache d'index ; validation contre la grille complète (H16).
- **FR-49 : Mode mission** : enchaînement profilage, questions, validation métier, exécution, restitution, exécution 100 % locale possible (UJ-5).
- **FR-50 : Exposition MCP** : toute Configuration peut être servie comme serveur MCP.
- **FR-51 : Profils de déploiement** : hyperscaler (Azure en premier, D3), IaaS souverain (D6), hybride avec règle de sensibilité par métadonnées obligatoires et classifieur en alerte (D7).

## 5. Exigences transverses

- **Tests sans réseau** : la suite de tests par défaut ne fait aucun appel réseau et ne nécessite aucune clé ; elle utilise le Faux LLM, le faux embedder et le Mini-corpus fictif. Les tests qui appellent une vraie API ou un modèle local sont marqués séparément et sautés si la clé ou le modèle est absent. Le téléchargement des modèles (embedder, modèles de parsing) se fait par une commande d'installation distincte, jamais pendant les tests par défaut.
- **Tests réels bornés** : les tests contre l'API Anthropic s'exécutent sous le Plafond de dépense, sur Claude Haiku 5.5 et sur quelques Questions.
- **Secrets** : les clés sont lues depuis un fichier `.env` ignoré par git ou depuis l'environnement ; aucune clé n'apparaît dans les Traces, les Rapports ou les journaux.
- **Dépôt public** : aucun corpus sous licence restrictive, aucune donnée client, aucun Rapport issu d'un corpus non publiable dans le dépôt ; les dossiers de données et de résultats sont configurables et ignorés par git par défaut.
- **Local d'abord** : génération, embeddings et juges peuvent tourner en local (machine de référence : GPU de 8 Go) ; aucun Composant n'impose un service cloud.
- **Portabilité** : Windows et Linux ; Python 3.12 ou plus, géré par uv.
- **Robustesse** : une erreur sur une Question (délai dépassé, réponse non conforme) est enregistrée et n'arrête pas l'Exécution ; les appels de modèle sont réessayés 3 fois au plus, avec attente exponentielle (valeurs configurables).
- **Reprise** : une Exécution interrompue reprend là où elle s'est arrêtée.
- **Interface** : ligne de commande unique avec sous-commandes (corpus, questions, run, calibrer, rapport, registre) ; chaque sous-commande a une aide intégrée.

## 6. Non-objectifs

- Pas de plateforme no code ni d'interface web dans ce produit (livrable 3, WaveStack).
- Pas de service de recherche documentaire en production, pas de multi-utilisateur.
- Pas d'interface d'annotation : l'annotation se fait dans des fichiers.
- Pas de dépendance à un framework RAG comme socle (D4) : les frameworks n'entrent que comme Composants ou Architectures comparés.
- Pas de reprise de chiffres d'éditeurs sans les avoir reproduits.
- Pas de score global unique : les résultats se lisent en front de Pareto.

## 7. Périmètre MVP (premier run autonome)

### 7.1 Inclus

- FR-1 à FR-41 et FR-52 à FR-55.
- Architectures dans cet ordre de priorité : Baselines (FR-16), RAG naïf, RAG hybride, HyDE, Corrective RAG, CAG, RAPTOR, PageIndex, LLM Wiki, recherche agentique, GraphRAG et variantes (FR-18 à FR-27). Objectif : toutes ; minimum accepté : quatre Architectures du niveau 1 en plus des Baselines. Si le run s'arrête avant la fin, les Architectures livrées doivent toutes passer la suite de conformité.
- Mini-corpus fictif et son Jeu d'évaluation de référence (FR-8).
- Fournisseurs de modèles : API Anthropic et modèles locaux via Ollama ; les autres fournisseurs passent par la même passerelle et seront branchés plus tard.

### 7.2 Hors MVP

- FR-42 à FR-51 (phases 3 à 8).
- Azure AI Foundry : pas encore de clé.
- Corpus réels (CO Fantasy, notes MTG, veille, wikis) : branchés par Anaël après le run, hors du dépôt.
- Annotation réelle de 150 Questions et calibration réelle : le code est livré, les données viennent d'Anaël.
- Paliers de volume réels (100, 500, 2 000+ Documents) : le mécanisme est livré (FR-54), les données viennent avec les corpus réels.

### 7.3 Valeurs par défaut du MVP

Toutes sont configurables ; elles figurent dans la configuration par défaut livrée avec le code. Deux profils d'exécution locale sont livrés. Le profil **CPU** est celui par défaut du run autonome : le GPU est occupé par un autre banc, Ollama est donc appelé avec zéro couche sur GPU (`num_gpu: 0`) et l'embedder tourne sur CPU. Le profil **GPU** sert à l'usage ultérieur. Le profil fait partie de la Configuration et apparaît dans le Rapport.

| Rôle | Profil CPU (run autonome) | Profil GPU (plus tard) |
| --- | --- | --- |
| Generators | Claude Haiku 5.5 (API Anthropic) et minicpm5:1b (Ollama, CPU) | Claude Haiku 5.5 et qwen3.5:4b |
| Contexte long et CAG | Claude Haiku 5.5, autorisé tant que le prompt reste sous 100 000 tokens (FR-16) | idem |
| Embedder | multilingual-e5-small (environ 120 M de paramètres), sur CPU | bge-m3 |
| Panel de juges | Pour un Generator Claude : minicpm5:2b et granite4.2:3b. Pour un Generator MiniCPM : Claude Haiku 5.5 et granite4.2:3b | Pour Claude : qwen3.5:4b et ministral-3:8b. Pour Qwen : Haiku 5.5 et ministral-3:8b |
| Filtre closed-book | Claude Haiku 5.5, minicpm5:1b, granite4.2:3b | Claude Haiku 5.5, qwen3.5:4b, ministral-3:8b |
| Tests locaux réels | Au plus 5 Questions, délai de 120 s par appel | — |
| Génération de questions | Claude Haiku 5.5 au MVP ; un modèle plus fort pour les corpus réels (Question ouverte 2) |
| Plafond de dépense du run autonome | 5 $ sur l'API Anthropic |
| Paramètres | k = 5, seuil Corrective RAG 0,5 et 2 boucles, agent 8 étapes et 0,05 $ par Question, PageIndex 8 nœuds lus, RAPTOR groupes de 5 à 10 et profondeur 3, bootstrap 2 000 rééchantillons à 95 %, kappa 0,6, répartition 40 % / 60 % |

## 8. Indicateurs de succès

**Principaux**
- **SM-1** : chaque branche de l'arbre de décision du cadrage est marquée confirmée ou corrigée par une mesure (fin de phase 3). Valide FR-35 à FR-44.
- **SM-2** : en mission, la configuration trouvée sous budget atteint au moins 95 % de la qualité de l'optimum de la grille complète `[ASSUMPTION : seuil à confirmer en phase 7]`. Valide FR-48.

**MVP**
- **SM-3** : au réveil, `uv run pytest` passe sans réseau, et une Expérience sur le Mini-corpus fictif avec les Composants factices exécute toutes les Baselines et au moins quatre Architectures du niveau 1 de bout en bout, avec un Rapport complet. Valide FR-1 à FR-41 et FR-52 à FR-55.
- **SM-4** : un test réel de bout en bout sur Claude Haiku 5.5 et 5 Questions du Mini-corpus fictif passe sous le Plafond de dépense ; le coût tracé égale, au centime près, le coût recalculé à partir des tokens renvoyés par l'API et de la Grille tarifaire (cohérence interne, sans facture). Valide FR-29, FR-30, FR-33.

**Secondaires**
- **SM-5** : accord juge-humain (kappa) d'au moins 0,6 par Critère pour chaque Juge retenu. Valide FR-38.

**Contre-indicateurs (ne pas optimiser)**
- **SM-C1** : nombre d'Architectures livrées. Une Architecture qui ne passe pas la suite de conformité ne compte pas. Contrebalance SM-3.
- **SM-C2** : score sur la partie développement. L'optimiser revient à surajuster ; seuls les résultats sur la partie test fondent la conviction. Contrebalance SM-1.
- **SM-C3** : coût minimal à tout prix. Une Architecture moins chère mais de qualité inférieure ne « gagne » pas ; le point mort n'existe qu'à qualité égale. Contrebalance FR-31.

## 9. Risques

| Risque | Parade |
| --- | --- |
| Dépense non maîtrisée pendant le run autonome | Plafond bloquant avant appel, registre persistant, tests réels limités à Haiku 5.5 |
| Architectures complexes incomplètes au matin | Ordre du simple au complexe, suite de conformité commune, chaque story livrable seule |
| Juges biaisés ou instables | Panel multi-familles, règle de famille, calibration et passes multiples |
| Surajustement des configurations | Gel et partie test réservée |
| Contamination par les données d'entraînement | Filtre closed-book, Mini-corpus fictif contrefactuel |
| Fuite de corpus sous droits dans le dépôt public | Chemins de données hors dépôt ou ignorés par git, contrôle à la déclaration du Corpus |

## 10. Questions ouvertes

1. Seuil de kappa d'exclusion d'un Juge : 0,6 par défaut, à confirmer sur la calibration réelle. Responsable : Anaël.
2. Liste figée des modèles de référence du niveau 1 (Generator, Panel de juges, Filtre closed-book, génération de questions) pour les corpus réels. Responsable : Anaël, au lancement de la phase 2 réelle.
3. Date d'obtention de la clé Azure AI Foundry, qui conditionne les juges DeepSeek ou Kimi.
4. Identité et disponibilité du second annotateur (D1).
5. Plafond par Niveau du plan d'expérience (cadrage, risque « Coût API ») : à fixer avant la phase 2 réelle.

## 11. Index des hypothèses

- §4.2 FR-7 : volatilité déclarée au MVP, calculée plus tard.
- §4.4 FR-25 : fidélité du wiki mesurée par un Juge sur un échantillon de pages.
- §4.4 FR-27 : GraphRAG, LazyGraphRAG et LightRAG en implémentations maison simplifiées.
- §8 SM-2 : seuil de 95 % de l'optimum.
