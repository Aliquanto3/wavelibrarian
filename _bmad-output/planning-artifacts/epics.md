---
status: final
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-wavelibrarian-2026-10-17/prd.md
  - _bmad-output/planning-artifacts/prds/prd-wavelibrarian-2026-10-17/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-wavelibrarian-2026-10-17/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/architecture/architecture-wavelibrarian-2026-10-17/contracts.md
---

# WaveLibrarian - Découpage en epics

## Vue d'ensemble

Ce document découpe le MVP de WaveLibrarian (premier run de développement autonome) en epics et stories. Il part des exigences du PRD et des décisions d'architecture (AD-1 à AD-22, `contracts.md`). Le produit n'a qu'une interface en ligne de commande : il n'y a pas de document UX.

## Inventaire des exigences

### Exigences fonctionnelles

FR-1 : Expérience déclarative. Une Expérience YAML s'exécute par une seule commande. Une clé inconnue ou mal typée est refusée avec son chemin. L'Expérience résolue (défauts compris) et son empreinte sont écrites à côté des résultats. Deux Configurations peuvent ne différer que d'un Composant, et le Rapport les compare deux à deux.
FR-2 : Registre. On ajoute un Composant ou une Architecture en implémentant l'interface et en l'enregistrant sous un nom, sans toucher à l'orchestration. Une commande liste les noms, leurs paramètres et leur description. Un nom inconnu donne une erreur qui liste les noms disponibles pour l'interface.
FR-3 : Matrice de compatibilité. Refus avant tout appel : index réutilisé avec un Embedder de dimension différente, Architecture hybride sur un VectorStore non hybride, Juge de la même Famille que le Generator. La Baseline contexte long sur un Corpus trop grand est marquée « inapplicable » au lieu d'échouer.
FR-4 : Reproductibilité. Tout aléa vient de la graine de l'Expérience. Un rejeu avec les mêmes caches donne des Passages et des Réponses identiques, sans appel payant. Hors cache, seule l'identité des Passages retrouvés est garantie. La liste des modèles est datée, figée dans l'Expérience et affichée au Rapport.
FR-5 : Déclaration d'un Corpus : identifiant, chemin, langue, licence, publiable. `doc_id` dérivé du contenu, donc insensible au renommage. Formats Markdown, texte, HTML et PDF ; un autre format est signalé et ignoré. Métadonnées de sensibilité et de profils de droits, sans effet au MVP. Un Corpus restreint ne peut pas être placé dans le dépôt.
FR-6 : Ingestion avec Ancrages : page pour un PDF, chemin de titres pour Markdown et HTML. Un Ancrage de référence se retrouve dans le texte parsé. Le parsing est mis en cache par Document et par Parser.
FR-7 : Profilage. Nombre de Documents, tokens, longueur moyenne, profondeur de titres (max et moyenne), densité de liens (entités nommées partagées, extraites sans réseau ni LLM), part tabulaire, images par Document, langue dominante. Tokens comptés avec un tokenizer de référence unique ; comparaison à la fenêtre par le tokenizer du Catalogue, ou référence × 1,2. Volatilité déclarée. Profil en JSON, inclus dans le Rapport.
FR-8 : Mini-corpus fictif publiable. Environ 20 Documents (Markdown et PDF) dans un univers contrefactuel : un long document structuré avec tableaux, des documents liés, deux versions contradictoires, au moins deux Documents en anglais. Corpus de base sous 60 000 tokens. En plus : un Scénario de mise à jour (ajout, modification, suppression), une sentinelle, un document piégé, des profils de droits. Jeu d'évaluation de référence de 40 Questions ou plus, tous Types sauf visuelle et agrégation numérique, dont au moins 2 de suivi, 2 interlingues et 3 liées au Scénario. Jeu Gelé.
FR-9 : Format des Questions. Un fichier YAML par Corpus, avec les champs de `contracts.md` §4.5. Un fichier invalide est refusé avec le numéro de l'enregistrement et le champ en cause.
FR-10 : Génération de Questions candidates selon une répartition par Type. Chaque Question porte au moins un Ancrage vérifié, sauf « sans réponse ». La génération passe par le Plafond et le Cache de réponses LLM. Statut « générée », jamais utilisé avant validation.
FR-11 : Validation humaine par édition du fichier, puis commande de contrôle : comptes par statut et par Type, écart à la cible de 150, refus de toute Question validée dont un Ancrage est introuvable.
FR-12 : Filtre closed-book. Chaque Question est posée sans contexte à 2 ou 3 modèles. Une Question réussie par un modèle est marquée contaminée, avec le nom du modèle. « Réussie » : correspondance exacte normalisée pour une réponse courte, sinon verdict d'un Juge d'une autre Famille. Les « sans réponse » sont exclues. Le Rapport présente les contaminées à part.
FR-13 : Gel et séparation dev / test. Empreinte enregistrée ; une Exécution sur un jeu modifié après Gel est refusée. Répartition stratifiée par Type, déterministe par la graine, 40 % dev par défaut. La partie test n'est utilisée que sur demande explicite, et le Rapport indique la partie utilisée.
FR-14 : Contrat d'Architecture. Suite de conformité commune sur le Mini-corpus avec les faux : indexation, Citation valide sur une question factuelle, abstention, mise à jour. Toute Citation désigne un Ancrage existant. Une Architecture sans mise à jour incrémentale réindexe, au poste « mise à jour ».
FR-15 : Abstention. Indicateur d'abstention distinct du texte, exploité par le Critère « abstention correcte ».
FR-16 : Baselines sans contexte, contexte long et BM25 seul. Contexte long « inapplicable » au-delà de la fenêtre. Refus en contexte long et en CAG d'un modèle à palier tarifaire si le prompt estimé dépasse le seuil (Haiku 5.5 : 100 000 tokens). Pas de métriques de recherche pour la Baseline sans contexte ; métriques sur les Citations pour le contexte long.
FR-17 : Condition contexte parfait. Le Generator reçoit exactement le texte des Ancrages de référence, dans un ordre fixe (vide pour « sans réponse »). Les résultats sont étiquetés à part dans le Rapport.
FR-18 : RAG naïf. Découpage, embedding, recherche dense des k meilleurs Passages (k = 5), génération avec Citations. Exactement k Passages, classés par score décroissant. Une Citation hors du contexte est retirée et comptée en erreur.
FR-19 : RAG hybride. BM25 et dense, fusion RRF ou pondérée, reranker optionnel. Chaque étage s'active séparément. La latence du reranker est une étape distincte de la Trace.
FR-20 : HyDE. Réponse hypothétique tracée comme étape distincte, au poste « requête ». Son vecteur sert à la recherche (option : moyenne avec la question). Elle n'est jamais citée.
FR-21 : Corrective RAG. Le Decider note chaque Passage dans [0, 1] (seuil 0,5). Si aucun n'atteint le seuil, reformulation et nouvelle recherche, au plus 2 boucles, puis abstention. Les Passages sous le seuil sont exclus du contexte. Chaque boucle est tracée. Decider LLM au MVP.
FR-22 : CAG. Corpus préchargé dans le cache de prompt, préchargement au poste « indexation ». Tokens en cache tracés à part. Inapplicable au-delà de la fenêtre ou sans cache de prompt au Catalogue. Une seconde Question montre des tokens en cache non nuls.
FR-23 : RAPTOR. Arbre de résumés par regroupement récursif (groupes de 5 à 10, profondeur 3), au moins un niveau au-dessus des Passages. Recherche sur l'arbre aplati, niveau exposé. Une Citation d'un résumé est convertie vers les Ancrages des feuilles. Résumés au poste « indexation ».
FR-24 : PageIndex. Arbre par Document (titres, ou pages pour un PDF sans titres), avec résumé court et Ancrage par nœud, persistant dans le Cache d'index. Navigation par le LLM sans recherche vectorielle, au plus 8 nœuds lus, chaque nœud tracé. Les Passages retrouvés sont les sections lues.
FR-25 : LLM Wiki. Compilation en pages de wiki qui référencent leurs Ancrages ; les Citations remontent à ces Ancrages. La maintenance après mise à jour est tracée au poste « mise à jour ». Mesure de fidélité du wiki par un Juge sur un échantillon de pages.
FR-26 : Recherche agentique. Outils en lecture seule : recherche lexicale, lecture, liste. Au plus 8 étapes et 0,05 $ par Question, puis abstention. Passages retrouvés = extraits lus, dans l'ordre de lecture.
FR-27 : GraphRAG et variantes. Extraction d'entités et de relations, graphe, rapports de communautés, recherche locale et globale. LazyGraphRAG et LightRAG sont des Architectures distinctes. Implémentations maison simplifiées. Rapport ventilé par Type de question, coûts d'indexation et de mise à jour séparés.
FR-28 : Cache d'index adressé par Corpus × Parser × Découpage × Embedder × VectorStore (plus paramètres et modèle des contenus dérivés). Une seconde Exécution ne déclenche aucun appel d'indexation et la Trace indique « cache ». Une mise à jour crée une nouvelle entrée sans écraser l'ancienne.
FR-29 : Traces. Chaque appel produit une Trace : étape, modèle, fournisseur, tokens (entrée, sortie, cache), coût, latence, énergie, Poste, identifiants. Format OpenTelemetry, fichier local par Exécution, export externe en option. Somme des Traces = coût total du Rapport. Tokens renvoyés par le fournisseur, coût recalculé par la Grille.
FR-30 : Grille tarifaire datée. Un modèle d'API sans prix est refusé ; un modèle local relève du Coût de possession. Prix en devise du fournisseur, convertis en euros au taux daté, date de la grille affichée. Tarifs en lot et en cache déclarés à part.
FR-31 : Postes de coût séparés : indexation, mise à jour, requête, avec coût par requête, pour 1 000 requêtes, et débit. Le coût d'un poste additionne API et Coût de possession (paramètres déclarés et datés). Le point mort n'est calculé qu'à Qualité égale ou supérieure ; sinon, le Rapport dit pourquoi.
FR-32 : Énergie mesurée en local, estimée pour les API, étiquetée « mesurée » ou « estimée », avec un avertissement que les deux ne se comparent pas. CO2e par l'intensité carbone déclarée de la région.
FR-33 : Plafond de dépense par Exécution et par période, par fournisseur et en devise du fournisseur. Avant appel : estimation (tokens du Catalogue + 20 % + max de sortie) comparée au solde, sinon arrêt propre « plafond atteint ». Après appel, la dépense réelle remplace l'estimation. Registre persistant. Résultats partiels conservés, la reprise ne refait que les appels manquants. Plafond par défaut : 5 $ Anthropic.
FR-34 : Cache de réponses LLM. Un appel identique est servi gratuitement, la Trace l'indique, et le Rapport distingue coût réel et coût sans cache. Les passes multiples des Juges contournent le cache par un identifiant de passe.
FR-35 : Métriques de recherche rappel@k, MRR et nDCG. Pertinence par recouvrement d'Ancrage, quel que soit le Découpage. Calcul par Question, agrégé par Type. Pour les Architectures sans liste classée, calcul sur les Ancrages fournis ou cités, avec la méthode indiquée.
FR-36 : Métriques de réponse. Chaque Juge note chaque Critère en verdict binaire avec justification. Correspondance exacte normalisée pour une réponse courte (exactitude). Abstention correcte et citations correctes calculées sans Juge. Aucun score global.
FR-37 : Panel de 2 ou 3 Juges de Familles différentes ; un Juge ne note jamais un modèle de sa Famille (vérifié à la validation). Verdict à la majorité, égalité = « non » et signalement. Rôle « juge de calibration » optionnel. Panel MVP : modèles locaux Ollama et Claude Haiku 5.5.
FR-38 : Calibration. Kappa juge-humain par Critère, kappa entre annotateurs, taux de verdicts instables sur au moins 5 passes. Exclusion sous le seuil (0,6) ; les Rapports suivants ignorent le Juge et le mentionnent. Annotations : un YAML par annotateur.
FR-39 : Statistiques appariées. IC bootstrap par métrique ; comparaisons appariées (bootstrap apparié pour le continu, McNemar pour le binaire). Valeurs par défaut : 2 000 rééchantillons, 95 %, alpha 0,05, graine de l'Expérience. Comparaison sur les Questions communes, n affiché. Résultats identiques à une implémentation de référence sur données synthétiques.
FR-40 : Rapport d'exécution en Markdown plus fichiers tabulaires. Contenu : Expérience résolue, Profil, partie utilisée, Panel, scores par Critère et par Type avec IC, comparaisons appariées, contaminées à part, coûts et énergie par Poste, latence p50 et p95, débit, Fraîcheur, Paliers, fronts de Pareto (Qualité × coût, × énergie, × latence p95, plus un par Critère), inapplicables avec leur raison.
FR-41 : Plan par niveaux. Le front de Pareto d'une Exécution s'exporte comme liste de Configurations de départ d'une nouvelle Expérience.
FR-52 : Composants factices. Faux embedder (dimension 64, hachage de sacs de mots). Faux LLM qui reconnaît le rôle et renvoie une sortie conforme : en génération, première phrase du premier Passage, citée, et abstention sur contexte vide. Tokens = mots, tokens en cache sur préfixe déjà vu, prix fictif, latence nulle. Mode scénarisé pour imposer une sortie.
FR-53 : Scénario de mise à jour et Fraîcheur. Fichier d'opérations ordonnées (ajout, modification, suppression). Après application, un Document supprimé n'apparaît plus dans les Passages ni les Citations. Coût, énergie et durée au poste « mise à jour » ; Fraîcheur calculée sur les Questions liées.
FR-54 : Paliers de volume emboîtés et déterministes. Les Documents des Ancrages de référence sont dans tous les Paliers. Résultats par Palier ; testé sur le Mini-corpus (5 ⊂ 10 ⊂ 20).
FR-55 : Catalogue de modèles versionné : identifiant, fournisseur, Famille, fenêtre, tokenizer, prix et paliers, cache de prompt, local ou API. Un modèle absent est refusé à la validation.

Hors MVP : FR-42 à FR-51 (phases 3 à 8).

### Exigences non fonctionnelles

NFR-1 : Tests sans réseau. La suite par défaut ne fait aucun appel réseau et n'exige aucune clé : Faux LLM, faux embedder, Mini-corpus. Tests réels marqués à part et sautés si la clé ou le modèle manquent. Les modèles se téléchargent par une commande d'installation, jamais pendant les tests.
NFR-2 : Tests réels bornés. Tests contre l'API Anthropic sous Plafond, sur Claude Haiku 5.5 et au plus 5 Questions. Tests locaux : délai de 120 s par appel.
NFR-3 : Secrets. Clés lues depuis `.env` (ignoré par git) ou l'environnement ; aucune clé dans les Traces, les Rapports ou les journaux.
NFR-4 : Dépôt public. Aucun corpus restreint, aucune donnée client, aucun Rapport de corpus non publiable dans le dépôt. Dossiers de données et de résultats configurables et ignorés par git.
NFR-5 : Local d'abord. Génération, embeddings et juges peuvent tourner en local (GPU de 8 Go) ; aucun Composant n'impose le cloud. Profil CPU par défaut pour le run autonome (`num_gpu: 0`).
NFR-6 : Portabilité Windows et Linux ; Python ≥ 3.12, géré par uv.
NFR-7 : Robustesse. Une erreur sur une Question est enregistrée et n'arrête pas l'Exécution ; 3 essais au plus avec attente exponentielle (configurable).
NFR-8 : Reprise. Une Exécution interrompue reprend là où elle s'est arrêtée.
NFR-9 : Interface. CLI unique avec sous-commandes (corpus, questions, run, calibrer, rapport, registre), chacune avec une aide intégrée.
NFR-10 : Critères de sortie du MVP. SM-3 : `uv run pytest` passe sans réseau, et une Expérience sur le Mini-corpus avec les faux exécute toutes les Baselines et au moins 4 Architectures du niveau 1, avec un Rapport complet. SM-4 : un test réel Haiku 5.5 sur 5 Questions passe sous le Plafond, et le coût tracé égale le recalcul au centime près.
NFR-11 : Contre-indicateurs. Une Architecture qui ne passe pas la conformité ne compte pas (SM-C1) ; pas d'optimisation sur la partie dev (SM-C2) ; pas de point mort hors Qualité égale (SM-C3).

### Exigences additionnelles (architecture)

- **Pas de gabarit de démarrage tiers.** Le squelette `uv` (`uv_build`, `src/wavelibrarian/`) suit le germe structurel du spine. La première story pose `pyproject.toml` avec la pile épinglée (`>=x.y,<x+1`, `uv.lock` fait foi) et les extras `local`, `energy` et `docling`, plus torch CPU par l'index `download.pytorch.org/whl/cpu` dans `[tool.uv.sources]`.
- **AD-1 Couches.** `cli` > `runner` | `report` > `architectures` > `components` > `evalset` > `scoring` > `corpus` > `llm` | `measure` | `stats` > `config` > `registry` > `ports` > `core`. Contrat `layers` d'`import-linter` dans `pyproject.toml`, ajouté aux `COMMANDES` du contrôle rapide. Seuls `llm/providers/` importent `anthropic` et `httpx`, seuls `components/embedders/` importent `sentence_transformers`, seul `measure/` importe `opentelemetry`, `codecarbon` et `ecologits` (sauf l'adaptateur `anthropic`, qui lit les impacts EcoLogits).
- **AD-2 Registre.** `@register(kind, name)`, `Params` pydantic (`extra="forbid"`, `frozen=True`), docstring utilisée comme description, construction par `cls(params, ctx)`, sous-Composants par `ctx.build`. `discover()` par `pkgutil`. Liste fermée de `kind`.
- **AD-3 Passerelle mesurée.** `MeteredGateway` est le point de passage unique, dans un ordre fixe : marqueur, cache, réservation au registre, appel avec 3 essais, coût par le Catalogue, règlement, mise en cache, span. Providers `anthropic` (SDK, `cache_control`), `ollama` (`/api/chat` par httpx, options du profil, `format` JSON) et `fake`. Les spans LLM ne viennent que de la passerelle ; Embedder et Reranker tracent leurs lots ; une Architecture ou un Retriever ne tracent jamais.
- **AD-4 Rôles fermés.** `LLMRole` est une liste fermée. `inputs` est rempli par l'appelant et seul le Faux LLM le lit. Marqueur `[[wl:role=…]]` posé par la passerelle. `complete_structured` réessaie une fois, puis lève `NonConformantOutput` (Question en `status: error`). Un nouveau rôle modifie `roles.py` et `fake.py` dans la même story.
- **AD-5 Identités.** `source_path`, `doc_id = sha256[:16]`, formats d'`anchor_id`, résolution des ancrages par `ParsedCorpus.resolve`. Tous les hachages passent par `core/ids.py`.
- **AD-6** Une Architecture ne reçoit que `QuestionInput`. Le runner complète `ArchAnswer` en `Answer` et construit lui-même la Condition contexte parfait (`answer_with_context`).
- **AD-7** Étiquettes `[S1]…[Sn]` et table `labels`. Les Citations invalides sont retirées et comptées dans `invalid_citations`. Un nœud de résumé porte les `anchor_ids` de ses feuilles.
- **AD-8** Le runner fixe le Poste de coût (`indexing`, `update`, `query`, `judging`, `evalset`) par context manager ; les Composants ne nomment que `step`.
- **AD-9** Montants en `Decimal` dans la devise du fournisseur. `ledger.sqlite` (réserver, puis régler ou libérer ; mois civil UTC par fournisseur) est la source du plafond, et `traces.jsonl` celle des coûts du Rapport. Conversion en euros dans `report/` seulement. Une réservation orpheline est réglée au montant estimé.
- **AD-10 Cache d'index.** Clé `index_key` adressée par contenu. Écriture dans `.tmp-<key>/` puis `os.replace`. Instance neuve et `load` après `index` ou `update`. Parsing en cache par `(parser, doc_id)`. Test de sensibilité de la clé aux Params hors `query_params`.
- **AD-11 Exécution.** Séquentielle, un processus et un fil applicatif (`SimpleSpanProcessor`), `run.lock`, SQLite en `BEGIN IMMEDIATE`. Fichiers append-only dans `runs/<run_id>/`. Préflight (Ollama, `/api/tags`, clés) avec code 4 en cas d'échec. Reprise par clés. `BudgetExceeded` donne un arrêt propre et un Rapport partiel, généré par `cli.py` après le runner (AD-1 : `runner` n'importe pas `report`).
- **AD-12 Configuration.** `yaml.safe_load` et schémas `extra="forbid"`. `ConfigError` au chemin pointé. Précédence : code, puis profil, puis Expérience. `experiment.resolved.yaml` et son `sha256` sont écrits avant tout appel. `costs.yaml` est surchargeable par `<WL_HOME>/costs.yaml` puis par `costs:`.
- **AD-13** `config/validate.py` rassemble toutes les erreurs statiques dans un seul `ValidationFailed`, sans réseau. Les contrôles dépendants du Corpus passent par `Architecture.check(profile)` et donnent `inapplicable` dans `applicability.json`.
- **AD-14 Panel.** Les `panel_size` premiers modèles du réservoir hors Famille des `answer_producer` et hors exclus de la calibration ; moins de 2 = refus. Règle propre au Filtre closed-book. Un Juge note tous ses Critères en un seul appel.
- **AD-15 Gel.** Empreinte sans `freeze` ni `contaminated_by`. `split` stratifié et déterministe. Le runner refuse un fichier non gelé ou modifié et n'utilise que `validated` et `corrected`.
- **AD-16 Tests.** `pytest-socket` (`--disable-socket --allow-unix-socket`), marqueurs `real_api`, `real_local` et `slow`, profil `test` (`fake-llm-a/b/c`, `fake-embedder`, tokenizer `approx`, énergie `fake`, `WL_HOME` dans `tmp_path`). `tests/conformance/test_architectures.py` est paramétré sur tout le registre ; `tests/e2e/test_sm3.py` et `tests/real/test_sm4.py`. La première story vérifie que `--disable-socket` fonctionne sous Windows. `wl installer --profil cpu|gpu` télécharge les modèles.
- **AD-17 Traces et énergie.** `opentelemetry-sdk` avec un `JsonlSpanExporter` maison, attributs de `contracts.md` §6, OTLP en option désactivée. EcoLogits pour l'API Anthropic. codecarbon `OfflineEmissionsTracker` par phase, réparti au prorata de la latence, `measured` seulement avec un compteur matériel. Jamais de somme entre `measured` et `estimated`.
- **AD-18** Agent et PageIndex fonctionnent par un protocole JSON (`agent_step`, `select_nodes`), sans tool calling natif. Bornes vérifiées avant chaque appel.
- **AD-19 Secrets.** `python-dotenv` lu dans `llm/providers/` seulement, clés en `SecretStr`, jamais tracées. `WL_HOME` (`./.wl`) et `results` dans `.gitignore`. Un Corpus `publishable: false` dans le dépôt est refusé s'il n'est pas ignoré (`git check-ignore`).
- **AD-20 Déterminisme.** `ctx.rng(*clés)` ou `default_rng(sha16(...))`, `temperature: 0` et `seed`, itérations sur des listes triées, égalités départagées par id.
- **AD-21 Profils.** `cpu` (défaut), `gpu` et `test` dans `defaults/profiles/`, lus par `ctx.profile` ; nom écrit au manifeste et au Rapport.
- **AD-22 Grandeurs du Rapport** (`contracts.md` §7). `scoring/` produit les verdicts, `stats/` des fonctions pures, `report/` agrège par (config_id, condition, tier, phase) à partir des seuls fichiers de l'Exécution. Paliers tirés par `corpus/tiers.py` avec `required_paths`.
- **Conventions.** Identifiants et clés en anglais ; messages CLI, Rapport et docstrings en français. Un Composant par module ; nom au registre = nom du module. Exceptions de `core/errors.py` seulement. Codes de sortie 0, 1, 2, 3, 4. `logging` (pas de `print` hors `cli.py`). JSONL en UTF-8 avec LF. Prompts en constantes `str.format` dans le module. Arborescence de tests `tests/unit/<couche>/`, `conformance/`, `e2e/`, `real/`, avec les fixtures `fake_ctx`, `minicorpus` et `wl_home`.
- **Données livrées.** `defaults/models.yaml` (Haiku 5.5, modèles Ollama CPU et GPU, embedders, `fake-*`), `defaults/costs.yaml`, `defaults/profiles/*.yaml`, `experiments/mini-test.yaml`, `mini-cpu.yaml` et `mini-real-haiku.yaml`. `scripts/make_minicorpus_pdfs.py` (fpdf2) produit les PDF, qui sont commités.
- **Ordre de construction imposé.** `core` et `ports`, puis `registry` et `config`, puis `llm` avec le Faux LLM et `measure/tracing`, puis `corpus` et le Mini-corpus, puis `runner`, `scoring`, `stats` et `report` avec les Baselines. Enfin les Architectures, dans l'ordre du PRD §7.1. La suite de conformité existe avant la première Architecture du niveau 1.
- **Enchaînement par story.** `agent-cost-kit:dev-story` → `second-avis` → `reviewer` → intégration. Chaque story est livrable seule ; le contrôle rapide et `pytest` passent sans réseau.

### Contraintes du run autonome du 17 au 18 octobre 2026

Un autre banc (slm-quality-bench) occupe la machine jusqu'au 18/10 vers 10 h, avec Ollama sur le GPU. Ces règles s'ajoutent aux stories pendant ce run. Elles ne changent pas leurs critères, qui restent vérifiables sans réseau.

- **Ollama local interdit.** Aucune requête au service hors `/api/version`, `/api/ps` et `/api/tags`, aucune commande `ollama`, aucun second serveur de modèles. Les tests `real_local` (stories 1.11 et 1.12) sont écrits mais **pas exécutés** : ne jamais lancer `pytest -m real_local`. Pas de `wl run` sur `mini-cpu.yaml`, qui appellerait Ollama. Le préflight se limite à `/api/tags`.
- **GPU interdit.** `CUDA_VISIBLE_DEVICES=-1` avant tout code de ML. Après chaque exécution d'un code de ML, vérifier que le PID n'apparaît pas dans `nvidia-smi --query-compute-apps=pid,process_name --format=csv`.
- **Pas d'extra lourd, pas de téléchargement de plus de 1 Go.** Ne pas installer les extras `local` (torch) ni `docling`, et ne pas lancer `wl installer`. Les tests par défaut n'en ont pas besoin (profil `test`).
- **Ressources.** `OMP_NUM_THREADS=4`, `MKL_NUM_THREADS=4` et `OPENBLAS_NUM_THREADS=4` dans l'environnement du run. Au plus 6 Go de RAM, priorité `BelowNormal` pour les processus du run, aucun pytest parallèle.
- **API autorisée.** SM-4 (story 4.15) ne sollicite que l'API Anthropic, avec des Juges et un embedder factices (story 4.14), sous le plafond de 5 $.
- **Surveillance par l'orchestrateur.** Avant de commencer, puis toutes les 10 minutes environ : débit du banc (réponses des 10 dernières minutes dans `wavelocalai/data/quality_bench/campaigns/pilot-20261017/log-generate.log`, à comparer sur le même modèle et la même piste), CPU total, RAM libre, et consommation propre du run (temps CPU, RSS de pointe, threads), consignée dans le projet.
- **Pause ou arrêt** si le débit du banc baisse de plus de 15 %, si le CPU dépasse 80 % de façon soutenue, ou si la RAM libre passe sous 6 Go. Si une ligne `ERROR` ou « campagne arrêtée » apparaît dans le log du banc : ne rien toucher et prévenir Anaël. Le travail lourd attend `pilot-report.md`.
- **Après le pilote.** Le run peut continuer en journée. Dès que `pilot-report.md` existe, les tests `real_local` et `mini-cpu.yaml` redeviennent possibles, sur le profil CPU (`num_gpu: 0`).
- **Reprise après `/clear`.** L'orchestrateur tient à jour un `RUN-STATUS.md` : story en cours, stories livrées, dépense, dernière mesure du banc, blocages. Une session neuve doit pouvoir reprendre le run en ne relisant que ce fichier et le sprint status.

### Exigences de design UX

Sans objet : le produit n'a qu'une interface en ligne de commande (NFR-9), sans document UX.

### Carte de couverture des FR

Une FR qui court sur plusieurs epics est rattachée à l'epic qui la livre en entier. Les epics précédents n'en posent que les fondations, notées entre parenthèses.

| FR | Epic | Objet |
| --- | --- | --- |
| FR-1 | 4 (1 : schémas et chargement) | Expérience exécutée par une seule commande |
| FR-2 | 1 | Registre et `wl registre` |
| FR-3 | 1 (contrôles statiques), 4 (`check()` et inapplicable) | Matrice de compatibilité |
| FR-4 | 4 | Reproductibilité, rejeu sans appel payant |
| FR-5 | 2 | Déclaration d'un Corpus |
| FR-6 | 2 | Ingestion avec Ancrages, cache de parsing |
| FR-7 | 2 | Profil de corpus |
| FR-8 | 2 (Documents, extras, scénario), 3 (Jeu de référence gelé) | Mini-corpus fictif |
| FR-9 | 3 | Format des Questions |
| FR-10 | 3 | Génération de Questions |
| FR-11 | 3 | Contrôle des Questions |
| FR-12 | 3 | Filtre closed-book |
| FR-13 | 3 | Gel et séparation dev / test |
| FR-14 | 4 | Contrat d'Architecture et suite de conformité |
| FR-15 | 4 | Abstention |
| FR-16 | 4 | Trois Baselines |
| FR-17 | 4 | Condition contexte parfait |
| FR-18 | 6 | RAG naïf |
| FR-19 | 6 | RAG hybride |
| FR-20 | 6 | HyDE |
| FR-21 | 6 | Corrective RAG |
| FR-22 | 6 | CAG |
| FR-23 | 7 | RAPTOR |
| FR-24 | 7 | PageIndex |
| FR-25 | 7 | LLM Wiki |
| FR-26 | 7 | Recherche agentique |
| FR-27 | 7 | GraphRAG, LazyGraphRAG, LightRAG |
| FR-28 | 4 | Cache d'index |
| FR-29 | 1 | Traces OpenTelemetry |
| FR-30 | 1 | Grille tarifaire datée |
| FR-31 | 4 (1 : `measure/tco.py`) | Postes de coût, coût par requête, point mort |
| FR-32 | 1 (mesure), 4 (restitution) | Énergie mesurée ou estimée |
| FR-33 | 1 (registre, réservation), 4 (arrêt propre et reprise) | Plafond de dépense |
| FR-34 | 1 | Cache de réponses LLM |
| FR-35 | 4 | Métriques de recherche |
| FR-36 | 4 | Métriques de réponse |
| FR-37 | 4 (1 : règle de famille à la validation) | Panel de juges |
| FR-38 | 5 | Calibration des juges |
| FR-39 | 4 | Statistiques appariées |
| FR-40 | 4 | Rapport d'exécution |
| FR-41 | 4 | Export du front de Pareto |
| FR-52 | 1 | Faux LLM et faux embedder |
| FR-53 | 2 (fichier et application au Corpus), 4 (phase `after_update`, Fraîcheur) | Scénario de mise à jour |
| FR-54 | 2 (tirage), 4 (exécution et Rapport par Palier) | Paliers de volume |
| FR-55 | 1 | Catalogue de modèles |

Couverture : les 45 FR du MVP sont rattachées à un epic.

## Liste des epics

### Epic 1 : Un banc configurable, mesuré et testable sans réseau
Anaël valide une Expérience YAML avant tout appel et liste ce que le banc sait faire (`wl registre`). Tout appel de modèle, réel ou factice, passe par une passerelle unique qui applique le Plafond de dépense et le Cache de réponses, et qui trace coût, tokens et énergie. Un agent de développement ajoute un Composant enregistré et le teste avec le Faux LLM et le faux embedder, sans réseau ni clé.
**FR couvertes :** FR-2, FR-3 (statique), FR-29, FR-30, FR-32 (mesure), FR-33 (registre), FR-34, FR-52, FR-55 ; fondations de FR-1, FR-31 et FR-37.
**Notes :** squelette `uv` et pile épinglée, `import-linter` (AD-1), `pytest-socket` vérifié sous Windows (AD-16), profils `cpu`, `gpu` et `test` (AD-21), providers `anthropic`, `ollama` et `fake` (AD-3, AD-4), `wl installer`.

### Epic 2 : Déclarer, ingérer et profiler un Corpus
Anaël déclare un Corpus, l'ingère avec ses Ancrages (Markdown, texte, HTML, PDF) et obtient son Profil (`wl corpus profiler`). Il tire des Paliers de volume emboîtés et applique un Scénario de mise à jour. Le dépôt livre le Mini-corpus fictif : Documents, extras et scénario.
**FR couvertes :** FR-5, FR-6, FR-7, FR-8 (Documents), FR-53 (fichier et application), FR-54 (tirage).
**Notes :** AD-5 (identités), AD-10 (cache de parsing), AD-19 (`git check-ignore`), `scripts/make_minicorpus_pdfs.py`.

### Epic 3 : Construire et geler un Jeu d'évaluation
Anaël génère des Questions candidates, les corrige dans le YAML, contrôle les Ancrages, passe le Filtre closed-book et gèle le jeu avec sa séparation dev / test (UJ-1). Le Jeu de référence du Mini-corpus (40 Questions ou plus) est livré gelé.
**FR couvertes :** FR-8 (Jeu de référence), FR-9, FR-10, FR-11, FR-12, FR-13.
**Notes :** AD-14 (Juge du Filtre closed-book), AD-15 (Gel). Le Composant Juge LLM naît ici ; l'epic 4 le réutilise pour le Panel.

### Epic 4 : Comparer les Baselines de bout en bout et lire le Rapport
Anaël lance `wl run` sur une Expérience qui compare les trois Baselines, en Condition standard et contexte parfait. Il peut appliquer un Scénario et des Paliers, s'arrêter au plafond et reprendre sans repayer. Il obtient un Rapport complet : scores par Critère avec IC, comparaisons appariées, coûts et énergie par Poste, fronts de Pareto exportables (UJ-2). La suite de conformité commune est en place pour toute Architecture future (UJ-4).
**FR couvertes :** FR-1, FR-3 (inapplicable), FR-4, FR-14, FR-15, FR-16, FR-17, FR-28, FR-31, FR-32 (restitution), FR-33 (arrêt et reprise), FR-35, FR-36, FR-37, FR-39, FR-40, FR-41, FR-53 (phase `after_update`, Fraîcheur), FR-54 (exécution par Palier).
**Notes :** AD-6, AD-8, AD-9, AD-10, AD-11, AD-13, AD-14, AD-22. Sortie : `tests/conformance/test_architectures.py`, `tests/e2e/test_sm3.py` sur les Baselines, `tests/real/test_sm4.py` (marqué `real_api`).

### Epic 5 : Calibrer les juges sur des annotations humaines
Anaël annote des Réponses dans des fichiers YAML, lance `wl calibrer`, obtient les kappas juge-humain et inter-annotateurs et le taux d'instabilité sur 5 passes. Les Juges sous le seuil sont exclus des Rapports suivants (UJ-3).
**FR couvertes :** FR-38.
**Notes :** AD-14 (exclusion par `calibration.json`), FR-34 (passes hors cache par `pass_id`).

### Epic 6 : Architectures à recherche : du RAG naïf au CAG
Anaël compare aux Baselines cinq Architectures du niveau 1 : RAG naïf, RAG hybride, HyDE, Corrective RAG et CAG, chacune sélectionnable par Expérience et validée par la suite de conformité. Cet epic atteint le minimum de SM-3 (quatre Architectures du niveau 1 en plus des Baselines).
**FR couvertes :** FR-18, FR-19, FR-20, FR-21, FR-22.
**Notes :** une story par Architecture, dans l'ordre du PRD §7.1 ; chaque story livre aussi les Composants qui lui manquent (chunker, embedders, store, retrievers, reranker, decider, rewriter).

### Epic 7 : Architectures à structure dérivée : de RAPTOR à GraphRAG
Anaël ajoute au comparatif les Architectures qui construisent une structure à l'indexation : RAPTOR, PageIndex, LLM Wiki, recherche agentique, puis GraphRAG, LazyGraphRAG et LightRAG. L'Expérience `mini-test.yaml` couvre alors tout le registre.
**FR couvertes :** FR-23, FR-24, FR-25, FR-26, FR-27.
**Notes :** AD-7 (Citations des nœuds de résumé), AD-18 (protocole JSON). Une story par Architecture ; si le run s'arrête, chaque Architecture livrée passe la conformité.

## Epic 1 : Un banc configurable, mesuré et testable sans réseau

Anaël valide une Expérience YAML avant tout appel et liste ce que le banc sait faire. Tout appel de modèle passe par une passerelle unique qui applique le Plafond de dépense et le Cache de réponses, et qui trace coût, tokens et énergie. Un agent de développement ajoute un Composant et le teste avec le Faux LLM et le faux embedder, sans réseau ni clé.

Règle commune à toutes les stories du document : la suite par défaut (`uv run pytest -q`) et le contrôle rapide (`py .claude/cost-kit/controle_rapide.py`) passent sans réseau, avec le profil `test`. Un test qui exige le réseau porte le marqueur `real_api` ou `real_local`.

### Story 1.1 : Squelette du projet et garde-fous sans réseau

As a agent de développement,
I want un projet `uv` dont la pile, les couches et l'interdiction du réseau sont vérifiées automatiquement,
So that chaque story suivante démarre sur un socle qui refuse les imports interdits et les tests qui touchent le réseau.

**Exigences :** NFR-1, NFR-6, AD-1, AD-16, AD-19 (`.gitignore`), conventions de cohérence ; pile technique du spine.

**Acceptance Criteria:**

**Given** le `pyproject.toml` existant
**When** la story est livrée
**Then** il déclare les dépendances de la pile technique du spine épinglées en `>=x.y,<x+1`, les extras `local` (sentence-transformers, torch CPU par l'index `https://download.pytorch.org/whl/cpu` dans `[tool.uv.sources]`), `energy` (codecarbon, ecologits) et `docling`, et le groupe dev (pytest, pytest-socket, ruff, pyright, import-linter, fpdf2)
**And** `uv sync` puis `uv run pytest -q` passent sans installer d'extra, et `uv.lock` est commité
**And** l'index PyTorch est déclaré `explicit = true` et n'est associé qu'à `torch` dans `[tool.uv.sources]`, pour qu'aucun autre paquet ne puisse en provenir (risque de confusion de dépendances)

**Given** les paquets vides `core`, `ports`, `config`, `llm`, `llm/providers`, `measure`, `stats`, `corpus`, `scoring`, `evalset`, `components`, `architectures`, `runner`, `report` et les modules `registry.py` et `cli.py` créés selon le germe structurel
**When** on lance `uv run lint-imports`
**Then** le contrat `layers` (`root_package = "wavelibrarian"`) reprend mot pour mot l'ordre d'AD-1, modules indépendants compris, et passe
**And** un contrat `forbidden` interdit `anthropic` et `httpx` hors de `llm.providers`, `sentence_transformers` hors de `components.embedders`, et `opentelemetry`, `codecarbon` et `ecologits` hors de `measure` (sauf `llm.providers.anthropic` pour `ecologits`)
**And** un second contrat `forbidden` interdit d'importer `wavelibrarian.llm.providers` ailleurs que dans `llm.gateway` et `llm.preflight`, pour que le plafond de dépense ne puisse pas être contourné (AD-3)
**And** `lint-imports` est ajouté aux `COMMANDES` de `.claude/cost-kit/controle_rapide.py`, avec `ruff check`, `ruff format --check` et `pyright`

**Given** `addopts = "--disable-socket --allow-unix-socket -m 'not real_api and not real_local'"` et les marqueurs `real_api`, `real_local` et `slow` déclarés
**When** un test tente `socket.create_connection(("127.0.0.1", 9))` sous Windows comme sous Linux
**Then** il lève l'erreur de pytest-socket, et un test unitaire le vérifie
**And** un test marqué `real_api` est désélectionné par défaut

**Given** `core/errors.py` et `core/ids.py`
**When** les tests unitaires de `tests/unit/core/` s'exécutent
**Then** `WlError`, `ConfigError(path, message)`, `ValidationFailed(errors)`, `BudgetExceeded`, `Inapplicable(reason)`, `ProviderError(retryable)` et `NonConformantOutput` existent, avec `WlError` pour racine
**And** `canonical_json` trie les clés, utilise `separators=(",", ":")` et sérialise un `Decimal` en chaîne ; `sha16` renvoie 16 caractères hexadécimaux stables ; `slug("Éléments d'histoire")` vaut `elements-d-histoire` ; `new_run_id` suit `YYYYMMDD-HHMMSS-<6 hex>` en UTC

**Given** la commande `wl` déclarée en script du projet (typer)
**When** on lance `uv run wl --help`
**Then** l'aide s'affiche en français et la commande sort en 0
**And** `.gitignore` contient `.wl/`, `results/` et `.env`, et `tests/conftest.py` fournit la fixture `wl_home` (dossier dans `tmp_path`, variable `WL_HOME` positionnée)

### Story 1.2 : Types du domaine et ports publiés

As a agent de développement,
I want les types du domaine et les Protocols des ports tels que `contracts.md` les fixe,
So that tous les modules suivants partagent les mêmes formes sans les réinventer.

**Exigences :** FR-14, FR-15 (formes), FR-52 (formes) ; AD-5, AD-6, AD-9 ; `contracts.md` §1, §2, §2.1, §2.2, §2.4.

**Acceptance Criteria:**

**Given** `core/types.py`
**When** on importe ses modèles
**Then** on trouve tous les types de `contracts.md` §1 (`Anchor`, `Block`, `ParsedDocument`, `ParsedCorpus`, `Passage`, `ScoredPassage`, `QuestionInput`, `Citation`, `ArchAnswer`, `Answer`, `AnchorRef`, `Question`, `CorpusProfile`, `Usage`, `Verdict`, `DocMeta`, `ModelRefMeta`, `ModelRef` et les `Literal`), avec les mêmes noms de champs et les mêmes défauts
**And** chacun a `frozen=True, extra="forbid"` : un champ inconnu lève une `ValidationError`, une affectation après construction échoue

**Given** un `ParsedCorpus` construit à la main avec un Markdown et un PDF de deux pages
**When** on appelle `resolve("docs/a.md", None, ("Histoire", "Fondation"))` puis `resolve("docs/b.pdf", 2, ())` et `anchor_text(...)`
**Then** les `anchor_id` renvoyés suivent AD-5 (`<doc_id>#h/histoire/fondation`, `<doc_id>#p2`), un ancrage absent renvoie `None`, et `anchor_text` concatène les Blocks de l'ancrage dans l'ordre

**Given** un `Answer` contenant un coût ou un `Decimal`
**When** on le sérialise par `model_dump(mode="json")`
**Then** les montants sortent en chaînes et la relecture redonne un objet égal

**Given** le paquet `ports/`
**When** on l'inspecte
**Then** `components.py`, `architecture.py`, `gateway.py`, `measure.py` et `context.py` exposent les Protocols, `ArchitectureBase`, `ArchCapabilities`, `Applicability`, `CorpusChange`, `LLMRole`, `Message`, `LLMRequest`, `LLMResult`, `ComponentSpec`, `SearchIndex`, `Context`, `GenerationResult`, `JudgeInput` et `RunContext` de `contracts.md` §2
**And** `ArchitectureBase.answer_with_context` a l'implémentation par défaut (`context_builder.build` puis `generator.generate`) et `update` réindexe par défaut dans `new_directory`
**And** `core` et `ports` ne font aucune entrée-sortie, et `lint-imports` passe

### Story 1.3 : Registre de Composants et commande `wl registre`

As a agent de développement,
I want enregistrer un Composant ou une Architecture par un décorateur et le voir listé,
So that ajouter un module suffise à le rendre sélectionnable, sans toucher à l'orchestration (UJ-4).

**Exigences :** FR-2 ; AD-2.

**Acceptance Criteria:**

**Given** une classe de test décorée `@register("chunker", "toy")` avec un `Params` pydantic (`extra="forbid"`, `frozen=True`) et une docstring
**When** on appelle `registry.get("chunker", "toy")` puis `list_components(kind="chunker")`
**Then** la classe est renvoyée, et la liste donne le nom, le `kind`, la description tirée de la docstring et les Params avec leurs types et leurs défauts

**Given** un `kind` hors de la liste fermée de `contracts.md` §2
**When** on décore une classe avec ce `kind`
**Then** une `ConfigError` est levée
**And** deux enregistrements du même `(kind, name)` lèvent aussi une `ConfigError`

**Given** les Composants `toy` et `toy2` enregistrés pour `chunker`
**When** on demande le nom `inconnu`
**Then** la `ConfigError` liste `toy` et `toy2`, seulement pour ce `kind`

**Given** un module ajouté sous `wavelibrarian.components` ou `wavelibrarian.architectures`
**When** on appelle `registry.discover()`
**Then** il est importé récursivement par `pkgutil` sans autre modification, et un second appel est sans effet

**Given** la CLI
**When** on lance `wl registre` puis `wl registre --kind chunker`
**Then** la sortie liste les entrées enregistrées (toutes, puis celles du `kind`), avec leur description et leurs Params, en français, et sort en 0

### Story 1.4 : Catalogue de modèles, paramètres de coût et profils d'exécution

As a Anaël,
I want un Catalogue de modèles daté, des paramètres de coût et trois profils livrés avec le code,
So that chaque modèle, chaque prix et chaque option CPU ou GPU soient déclarés une fois, hors du code.

**Exigences :** FR-30, FR-55, FR-31 (paramètres), FR-32 (intensité carbone) ; AD-9, AD-12, AD-21 ; `contracts.md` §2.3, §4.2, §4.2 bis, §4.3.

**Acceptance Criteria:**

**Given** `defaults/models.yaml` livré dans le paquet
**When** on le charge par `config/catalog.py`
**Then** il contient `claude-haiku-5-5` (prix, palier au-delà de 100 000 tokens, `token_factor: "1.5"`, `prompt_cache: true`, `min_cacheable_tokens: 512`), les modèles Ollama des profils CPU et GPU, `multilingual-e5-small`, `bge-m3`, `fake-llm-a/b/c` (familles `fake-a/b/c`, prix fictif) et `fake-embedder` (dim 64)
**And** un modèle `kind: api` sans `pricing` est refusé au chargement avec le chemin `models[i].pricing`

**Given** le Catalogue chargé
**When** on appelle `catalog.get("absent")`
**Then** une `ConfigError` nomme le modèle (FR-55)

**Given** `Usage(input_tokens=1_000_000, output_tokens=1_000_000)` pour `claude-haiku-5-5`
**When** on appelle `catalog.cost`
**Then** le résultat est `Decimal("0.60")`, en USD
**And** pour un prompt dont l'entrée plus les lectures et écritures de cache dépassent 100 000 tokens, le multiplicateur 5 s'applique à tous les postes de la requête, y compris le cache
**And** les tarifs `cache_read` et `cache_write` sont appliqués aux tokens correspondants

**Given** `defaults/costs.yaml`, un `<WL_HOME>/costs.yaml` qui ne surcharge que `kwh_price_eur` et un fichier `costs:` d'Expérience qui ne surcharge que `gco2e_per_kwh`
**When** on résout les `CostSettings`
**Then** la fusion clé par clé suit la précédence défauts, puis `WL_HOME`, puis Expérience, et les dates des valeurs sont conservées

**Given** `defaults/profiles/cpu.yaml`, `gpu.yaml` et `test.yaml`
**When** on les charge en `ProfileSettings`
**Then** `cpu` a `options: {num_gpu: 0}` et les modèles du PRD §7.3, `gpu` a `options: {}`, `cuda` et les modèles GPU, et `test` n'utilise que des modèles `fake-*`, `tokenizer: approx` et `energy: fake`
**And** chaque modèle cité par un profil existe au Catalogue (test de cohérence)

### Story 1.5 : Chargement et résolution d'une Expérience

As a Anaël,
I want qu'une Expérience YAML soit chargée strictement et résolue avec toutes ses valeurs par défaut,
So that une faute de frappe soit refusée avec son chemin et que l'Expérience exécutée soit enregistrée telle quelle.

**Exigences :** FR-1, FR-4 (graine et modèles datés), FR-9 (chargement strict) ; AD-12, AD-20 ; `contracts.md` §4.4.

**Acceptance Criteria:**

**Given** une Expérience qui contient `configurations[1].params.kk: 5`
**When** on la charge par `config/load.py`
**Then** une `ConfigError` porte le chemin `configurations[1].params.kk`
**And** une valeur mal typée (`seed: "abc"`) est refusée avec le chemin `seed`

**Given** un fichier YAML qui contient une balise Python (`!!python/object`)
**When** on le charge
**Then** il est refusé, puisque le chargement passe par `yaml.safe_load`

**Given** une Expérience qui ne nomme ni profil ni modèle de Generator, et un Composant de test avec un champ `model: ModelRef` (`role_default="generator_models[0]"`, `answer_producer=True`)
**When** on la résout par `config/resolve.py`
**Then** le profil `cpu` est retenu, le champ reçoit `claude-haiku-5-5` et la Configuration expose la liste de ses modèles et de ses `answer_producer`
**And** un `embedder` omis prend `profile.defaults.embedder`, avec le Composant `fake` ou `sentence_transformers` selon le fournisseur au Catalogue
**And** les chemins relatifs (`corpus`, `questions`, `scenario`, `costs`) sont résolus par rapport au fichier de l'Expérience

**Given** une Expérience résolue
**When** on la sérialise
**Then** `experiment.resolved.yaml` contient toutes les valeurs par défaut, les `CostSettings` résolues et `models_frozen_at`, et `experiment.sha256` est stable d'un appel à l'autre
**And** deux Expériences qui ne diffèrent que par l'ordre de leurs clés ont la même empreinte

**Given** deux identifiants de Configuration identiques, ou un identifiant hors de `[a-z0-9-]+`
**When** on charge l'Expérience
**Then** la `ConfigError` pointe le champ `configurations[i].id`

### Story 1.6 : Validation statique d'une Expérience et formation du Panel

As a Anaël,
I want que toutes les incohérences d'une Expérience soient signalées en une fois, avant tout appel,
So that je ne paie jamais un appel pour une Configuration qui aurait été refusée.

**Exigences :** FR-3 (contrôles statiques), FR-30, FR-37 (règle de famille), FR-55 ; AD-13, AD-14.

**Acceptance Criteria:**

**Given** une Expérience avec trois défauts : un Composant inconnu, un modèle absent du Catalogue et une Architecture de test `requires_hybrid_store` associée à un store `hybrid: false`
**When** on appelle `config/validate.py`
**Then** un seul `ValidationFailed` regroupe les trois `ConfigError`, chacune avec son chemin, sans aucun accès réseau

**Given** une Architecture de test `requires_prompt_cache: true` et un Generator dont le Catalogue déclare `prompt_cache: false`
**When** on valide
**Then** la Configuration est refusée avec un message qui cite le modèle

**Given** `reuse_index: <clé>` et un `manifest.json` de cet index dans `WL_HOME/index/<clé>/` avec `embedder_dim: 384`, et un embedder de dimension 64
**When** on valide
**Then** la Configuration est refusée pour dimension incompatible (FR-3)

**Given** le réservoir `[fake-llm-a, fake-llm-b, fake-llm-c]`, `panel_size: 2` et un Generator de famille `fake-a`
**When** on forme le Panel (`form_panel`)
**Then** le Panel vaut `[fake-llm-b, fake-llm-c]`, dans l'ordre déclaré
**And** si `calibration.json` exclut `fake-llm-c`, il ne reste qu'un Juge et la Configuration est refusée
**And** un Juge déclaré explicitement de la même Famille que le Generator est refusé

**Given** la fonction `closed_book_judge(model_testé, pool)`
**When** le modèle testé est de famille `fake-a`
**Then** elle renvoie le premier modèle du réservoir d'une autre famille (AD-14)

**Given** la CLI
**When** on lance `wl run <experience-invalide.yaml>`
**Then** les erreurs s'affichent en français, avec leur chemin, et la commande sort avec le code 2
**And** à ce stade, une Expérience valide affiche « validation réussie » ; le runner arrive à l'epic 4

### Story 1.7 : Traces OpenTelemetry, tokenizers, énergie et coût de possession

As a Anaël,
I want que chaque appel laisse une Trace complète dans un fichier local, avec son énergie et son coût de possession,
So that tout coût et tout kWh du Rapport se retrouvent ligne à ligne.

**Exigences :** FR-29, FR-31 (coût de possession), FR-32 ; AD-8, AD-11 (`SimpleSpanProcessor`), AD-17 ; `contracts.md` §2.2, §6.

**Acceptance Criteria:**

**Given** un `Tracer` de `measure/tracing.py` lié à un contexte de test (run_id, config_id, question_id, post `query`, condition, phase, tier 10)
**When** on appelle `record("generate", "llm", ...)` deux fois
**Then** `traces.jsonl` contient deux lignes avec `trace_id`, `span_id`, `name`, `start_time` et `end_time`, et tous les attributs de `contracts.md` §6 (types respectés, `wl.cost` en chaîne Decimal)
**And** `wl.tier` est absent quand le contexte n'a pas de palier, et `wl.post` est lu dans le contexte, pas passé par l'appelant

**Given** la configuration par défaut
**When** on crée le Tracer
**Then** l'export OTLP est désactivé, le processeur est un `SimpleSpanProcessor` synchrone et aucune connexion réseau n'est tentée

**Given** le tokenizer `approx` du profil `test`
**When** on compte un texte de 12 mots
**Then** il renvoie 12
**And** le tokenizer `reference` (`tiktoken` `o200k_base`) est chargé au premier usage, et lève `WlError("… wl installer …")` si l'encodage n'est pas installé localement, sans téléchargement
**And** `tokenizer_for(model)` applique `token_factor` (défaut 1,2) quand le Catalogue ne déclare pas `reference`

**Given** l'énergie `fake` du profil `test`
**When** on démarre et arrête une phase puis on répartit l'énergie sur trois spans locaux de latences 1, 1 et 2 s
**Then** la répartition se fait au prorata (25 %, 25 %, 50 %) et chaque span porte `wl.energy_method`
**And** les adaptateurs `codecarbon` et `ecologits` sont importés au premier usage et lèvent `WlError("installer l'extra energy")` s'ils manquent
**And** une énergie n'est `measured` que si le compteur est matériel, sinon `estimated`

**Given** `measure/tco.py` et des `CostSettings` connus
**When** on calcule le Coût de possession de 0,5 kWh, de 3 600 s de calcul local et de 2 Go d'index sur un mois
**Then** le résultat égale kWh × prix + prix du matériel ÷ durée de vie × heures + Go × prix du stockage, en `Decimal`, en euros

### Story 1.8 : Registre de dépense et Cache de réponses LLM

As a Anaël,
I want un registre de dépense persistant et un cache des réponses déjà payées,
So that aucun appel ne dépasse mon plafond et qu'aucun appel identique ne soit payé deux fois.

**Exigences :** FR-33, FR-34, FR-4 ; AD-9, AD-11 (`BEGIN IMMEDIATE`).

**Acceptance Criteria:**

**Given** un `ledger.sqlite` vide dans `WL_HOME`, un plafond par Exécution de 1,00 USD et un plafond de période de 2,00 USD pour `anthropic`
**When** on réserve 0,60, on règle à 0,40, puis on réserve 0,70
**Then** la seconde réservation est refusée par `BudgetExceeded` (0,40 + 0,70 > 1,00), et le solde affiché vaut 0,60
**And** chaque écriture se fait en transaction `BEGIN IMMEDIATE`

**Given** deux Exécutions successives de 1,50 USD réglés chacune dans le même mois civil UTC
**When** une troisième réserve 0,10
**Then** elle est refusée au titre du plafond de période ; au 1er du mois suivant (horloge injectée), elle est acceptée

**Given** une réservation non réglée laissée par un arrêt brutal
**When** le registre est rouvert
**Then** elle est réglée au montant estimé et le solde en tient compte
**And** une réservation libérée (appel en erreur) ne compte plus

**Given** des plafonds dans des devises différentes (`anthropic` en USD, `azure` en EUR)
**When** on réserve chez un fournisseur
**Then** seul son plafond, dans sa devise, est consulté

**Given** `llm/cache.py` et une clé `sha256(canonical_json(model, params, system, messages, pass_id))`
**When** on stocke puis relit une réponse
**Then** la relecture renvoie le texte et l'`Usage` d'origine
**And** changer `pass_id`, un message ou `temperature` change la clé, alors que changer `step` ne la change pas
**And** `inputs` n'entre pas dans la clé pour un provider réel (AD-4), mais y entre pour un modèle de provider `fake`, qui ne lit que `inputs` (écart reporté dans `contracts.md` §2.2)

### Story 1.9 : Passerelle mesurée

As a agent de développement,
I want une passerelle unique par laquelle passe tout appel de modèle,
So that aucun appel n'échappe au plafond, au cache, à la trace ni au registre de dépense.

**Exigences :** FR-29, FR-33, FR-34, FR-4 ; AD-3, AD-4 (marqueur, `complete_structured`), AD-9, AD-20 ; `contracts.md` §2.2.

**Acceptance Criteria:**

**Given** `MeteredGateway` (`llm/gateway.py`), un provider de test minimal qui renvoie un texte fixe et un `Usage` connu, le profil `test` et un `WL_HOME` temporaire
**When** un Composant appelle `complete` deux fois avec la même requête
**Then** le system reçu par le provider commence par `[[wl:role=<role>]]`, posé par la passerelle seule
**And** le premier appel réserve, appelle, règle au coût du Catalogue (prix fictif, en `Decimal`), stocke et trace un span `wl.llm_cache_hit=false`
**And** le second est servi depuis le cache, avec `cost` à 0, `cost_uncached` égal au premier coût et `wl.llm_cache_hit=true`, sans réservation

**Given** un solde insuffisant pour l'estimation (tokens × `token_factor` + `max_tokens`, palier compris)
**When** on appelle la passerelle
**Then** elle trace un span `wl.status=budget_refused` et lève `BudgetExceeded`, sans appeler le provider

**Given** un provider de test qui lève deux `ProviderError(retryable=True)` puis réussit
**When** on appelle la passerelle avec `retries: {max_attempts: 3}`
**Then** l'appel réussit au troisième essai, avec une attente exponentielle (horloge injectée) ; une erreur `retryable=False` n'est pas réessayée et libère la réservation

**Given** `complete_structured(request, Schema)` et un provider de test qui renvoie deux fois une sortie non conforme
**When** on l'appelle
**Then** l'appel est réessayé une fois puis lève `NonConformantOutput`, et le span porte `wl.status=non_conformant`

**Given** le contrat `import-linter` de la story 1.1
**When** on lance `lint-imports`
**Then** seuls `llm.gateway` et `llm.preflight` importent `llm.providers`. Un Composant ne peut donc pas appeler un provider directement en contournant le plafond (AD-3)

### Story 1.10 : Rôles LLM, Faux LLM et faux embedder

As a agent de développement,
I want les 15 rôles LLM avec leurs schémas, un Faux LLM qui répond à chacun et un faux embedder,
So that toute Architecture s'exécute et se mesure sans réseau, avec des sorties déterministes.

**Exigences :** FR-52, FR-34 ; AD-4, AD-16, AD-20 ; `contracts.md` §3.

**Acceptance Criteria:**

**Given** `llm/roles.py`
**When** on l'inspecte
**Then** chacun des 15 rôles de `LLMRole` déclare ses clés obligatoires d'`inputs` et son schéma pydantic de sortie, conformes à `contracts.md` §3
**And** une requête à laquelle manque une clé obligatoire d'`inputs` est refusée par la passerelle avant tout appel

**Given** le Faux LLM (`llm/providers/fake.py`) branché sur la passerelle de la story 1.9
**When** on l'appelle pour chacun des 15 rôles avec des `inputs` valides
**Then** il renvoie la sortie par défaut de `contracts.md` §3, valide pour le schéma du rôle, sans jamais lire le texte du prompt
**And** en `generate`, il répond par la première phrase du bloc `S1` en citant `S1`, et s'abstient si `blocks` est vide
**And** les tokens valent des nombres de mots, `cache_read_tokens` compte les mots d'un préfixe déjà vu (system mis en cache, messages `cache`), et la latence vaut 0
**And** `FakeProvider.script("grade_relevance", "crag.*", '{"scores":[0.1]}')` prime sur la sortie par défaut pour les étapes qui correspondent

**Given** deux appels au Faux LLM au prompt identique mais aux `inputs` différents
**When** le second passe par la passerelle
**Then** il n'est pas servi par le Cache de réponses : pour un modèle de provider `fake`, la clé inclut `inputs` (règle de la story 1.8), sinon la sortie en cache ne correspondrait pas aux `inputs` lus

**Given** le faux embedder `components/embedders/fake.py`, enregistré `("embedder", "fake")`
**When** on encode « orvane guilde fondation », « guilde d'orvane » et « recette de cuisine »
**Then** les vecteurs sont de dimension 64, de norme L2 égale à 1, et identiques d'un appel à l'autre
**And** les deux premiers textes sont plus proches entre eux que du troisième
**And** chaque appel d'`embed_*` émet un span `embed`

### Story 1.11 : Providers Anthropic et Ollama

As a Anaël,
I want brancher la passerelle sur l'API Anthropic et sur Ollama sans exposer mes clés,
So that les mêmes Composants tournent sur de vrais modèles, mesurés de la même façon.

**Exigences :** FR-29, FR-22 (cache de prompt), FR-32 (énergie API), NFR-3, NFR-5 ; AD-3, AD-17, AD-19, AD-21.

**Acceptance Criteria:**

**Given** l'adaptateur `llm/providers/anthropic.py` et un client du SDK branché sur un `httpx.MockTransport` qui renvoie une réponse enregistrée
**When** on envoie une `LLMRequest` avec `cache_system=True` et un `Message(cache=True)`
**Then** la requête native porte `cache_control` sur le system et sur ce message, `temperature: 0`, et le `model_id` du Catalogue
**And** l'`Usage` renvoyé reprend `input_tokens`, `output_tokens`, `cache_read_input_tokens` et `cache_creation_input_tokens`
**And** une réponse HTTP 429 ou 529 devient `ProviderError(retryable=True)`, une 400 `ProviderError(retryable=False)`

**Given** l'extra `energy` présent ou absent
**When** l'adaptateur lit les impacts EcoLogits de la réponse
**Then** l'énergie est `estimated` quand ils existent, `unknown` sinon, sans erreur

**Given** l'adaptateur `llm/providers/ollama.py` sur un `httpx.MockTransport`
**When** on envoie une requête avec le profil `cpu` et un schéma de sortie
**Then** le corps de `POST /api/chat` contient `options.num_gpu: 0`, `options.seed`, `keep_alive` et `format` égal au schéma JSON
**And** l'`Usage` reprend `prompt_eval_count` et `eval_count`, et le délai `call_timeout_s` du profil est appliqué

**Given** une clé `ANTHROPIC_API_KEY` dans un `.env` temporaire
**When** on charge les secrets dans `llm/providers/`
**Then** la clé est gardée en `SecretStr`
**And** après un appel réussi, puis un appel en erreur, ni la clé ni l'en-tête `x-api-key` n'apparaissent dans `traces.jsonl` ni dans les journaux capturés
**And** les loggers `anthropic`, `httpx` et `httpcore` sont forcés au niveau `WARNING` dans le gestionnaire de `run.log`, et un test qui passe le logging racine en `DEBUG` (et la variable de débogage du SDK, si elle existe) vérifie que la clé n'apparaît toujours dans aucun journal

**Given** un Ollama local et le modèle `minicpm5:1b-q4_k_m` présent
**When** on lance le test marqué `real_local`
**Then** un appel au profil `cpu` réussit et confirme que `num_gpu` est accepté par `/api/chat` ; sans Ollama, le test est sauté

### Story 1.12 : Préflight, `wl installer` et embedder sentence-transformers

As a Anaël,
I want installer les modèles locaux par une commande et que le banc vérifie ses dépendances avant de dépenser,
So that une Exécution n'échoue jamais au milieu pour un modèle ou une clé absents, et que les tests ne téléchargent jamais rien.

**Exigences :** NFR-1, NFR-5 ; AD-11 (préflight, code 4), AD-16 (`wl installer`), AD-21.

**Acceptance Criteria:**

**Given** `llm/preflight.py` et une liste de modèles (Ollama, Anthropic, sentence-transformers)
**When** Ollama ne répond pas (transport simulé)
**Then** le préflight renvoie un échec qui nomme `http://localhost:11434`
**And** un modèle absent de `/api/tags`, une clé `ANTHROPIC_API_KEY` manquante ou un embedder absent du cache local sont chacun signalés par leur nom
**And** les modèles `fake-*` ne demandent aucune vérification

**Given** la CLI et un préflight en échec
**When** on lance `wl run` sur une Expérience valide (le préflight s'insère après la validation de la story 1.6)
**Then** elle sort avec le code 4 et un message en français

**Given** `wl installer --profil cpu`
**When** on le lance avec les téléchargements simulés
**Then** il demande l'encodage tiktoken `o200k_base` et l'embedder `intfloat/multilingual-e5-small`, puis compare `ollama list` aux modèles du profil et liste ceux qui manquent
**And** `--profil gpu` vise `bge-m3` et les modèles Ollama GPU

**Given** le Composant `components/embedders/sentence_transformers.py`, enregistré `("embedder", "sentence_transformers")`
**When** on le construit sans l'extra `local`
**Then** il lève `WlError("installer l'extra local")` au premier usage, pas à l'import du module
**And** il applique `query_prefix` et `passage_prefix` du Catalogue, utilise `embedder_device` du profil, renvoie des vecteurs normalisés et émet un span `embed` par lot
**And** un test `real_local` encode deux phrases avec `multilingual-e5-small` ; sans modèle installé, il est sauté

## Epic 2 : Déclarer, ingérer et profiler un Corpus

Anaël déclare un Corpus, l'ingère avec ses Ancrages et obtient son Profil. Il tire des Paliers de volume emboîtés et applique un Scénario de mise à jour. Le dépôt livre le Mini-corpus fictif : Documents, extras et scénario.

### Story 2.1 : Déclaration d'un Corpus

As a Anaël,
I want déclarer un Corpus dans un `corpus.yaml` et que le banc identifie chaque Document par son contenu,
So that un renommage ne casse aucune référence et qu'un corpus sous droits ne puisse pas entrer dans le dépôt public.

**Exigences :** FR-5, NFR-4 ; AD-5, AD-12, AD-19 ; `contracts.md` §4.1.

**Acceptance Criteria:**

**Given** un `corpus.yaml` conforme à `contracts.md` §4.1 et un dossier `docs/` contenant `a.md`, `b.txt`, `c.html`, `d.pdf` et `e.docx`
**When** on le déclare par `corpus/declare.py`
**Then** quatre Documents sont retenus, triés par `source_path` POSIX relatif à la racine du Corpus, chacun avec `doc_id = sha256(octets)[:16]`
**And** `e.docx` est signalé dans le journal (format non pris en charge) et ignoré, sans arrêter la déclaration

**Given** le même fichier renommé de `a.md` en `z.md`
**When** on redéclare le Corpus
**Then** son `doc_id` est inchangé ; seul son `source_path` change

**Given** la clé `documents:` qui attribue `lang: en`, `sensitivity` et `rights_profiles` à un Document
**When** on déclare le Corpus
**Then** le Document porte ces métadonnées en `DocMeta` et sa langue surcharge la langue par défaut
**And** une clé inconnue dans `corpus.yaml` lève une `ConfigError` à son chemin, et `corpus_id` hors de `[a-z0-9-]+` est refusé

**Given** un Corpus `publishable: false` dont le `path` est dans le dépôt, dans un dossier non ignoré par git
**When** on le déclare
**Then** la déclaration échoue avec une `ConfigError` qui explique de placer le corpus hors du dépôt ou dans un dossier ignoré (vérification par `git check-ignore`)
**And** le même Corpus hors du dépôt, ou dans un dossier ignoré, est accepté ; hors d'un dépôt git, la vérification est sautée avec un avertissement

### Story 2.2 : Ingestion Markdown, texte et HTML avec Ancrages

As a Anaël,
I want que mes Documents textuels soient convertis en Blocks ancrés sur leur chemin de titres,
So that toute Question puisse citer un Ancrage stable, indépendant du Découpage.

**Exigences :** FR-6 ; AD-1 (parser obtenu par le registre), AD-5, AD-10 (cache de parsing) ; `contracts.md` §1, §2 (`Parser`).

**Acceptance Criteria:**

**Given** les Parsers `markdown` (markdown-it-py), `text` et `html` (beautifulsoup4), enregistrés au `kind` `parser` avec leurs `formats`
**When** on parse un Markdown à titres `# Histoire` puis `## Fondation`, avec un tableau et une image
**Then** chaque Block a un `anchor_id` `<doc_id>#h/histoire/fondation`, un `kind` (`text`, `table`, `heading`, `image`) et un texte non vide
**And** `anchors` liste les Ancrages dans l'ordre du Document, avec `heading_path` en titres bruts
**And** le texte avant le premier titre et un fichier `text` sans titre sont rattachés à `<doc_id>#h/`

**Given** un HTML avec `<h1>` à `<h3>` et un `<table>`
**When** on le parse
**Then** les Ancrages suivent la hiérarchie des titres et le tableau donne un Block `table`

**Given** deux titres frères identiques dans un même Document
**When** on le parse
**Then** leurs `anchor_id` restent distincts et déterministes (suffixe ordinal documenté)

**Given** `corpus/ingest.py`, un Corpus déclaré et `parser: auto`
**When** on ingère
**Then** `auto` est résolu en noms concrets par format (`markdown`, `text`, `html`, `pdf_text`), obtenus par le registre, sans import direct de `components`
**And** le résultat est un `ParsedCorpus` trié par `source_path`, avec `fingerprint = sha16` des couples `(source_path, doc_id)` triés
**And** chaque `ParsedDocument` est écrit dans `<WL_HOME>/parse_cache/<parser>/<doc_id>.json` ; une seconde ingestion le relit sans appeler le Parser (compteur d'appels dans le test)

**Given** un `ParsedCorpus` ingéré
**When** on appelle `resolve(source_path, None, headings)` avec les titres bruts d'une section
**Then** on obtient son `anchor_id`, et `anchor_text` renvoie le texte de la section (FR-6, utilisé par FR-11)

### Story 2.3 : Ingestion PDF avec Ancrages par page

As a Anaël,
I want que mes PDF soient ingérés page par page,
So that une Question puisse citer une page précise et que la validation la retrouve.

**Exigences :** FR-6 ; AD-5 ; pile : pypdfium2, fpdf2 (dev).

**Acceptance Criteria:**

**Given** le Parser `pdf_text` (pypdfium2), enregistré au `kind` `parser` avec `formats = {"pdf"}`
**When** on parse un PDF de trois pages généré dans le test par fpdf2
**Then** chaque Block porte l'`anchor_id` `<doc_id>#p<page>`, avec des pages numérotées à partir de 1, et le texte de chaque page est retrouvé
**And** `anchors` contient une entrée par page, avec `page` renseigné

**Given** une page sans texte extractible
**When** on la parse
**Then** son Ancrage existe, avec un texte vide, et aucune exception n'est levée

**Given** un PDF illisible (octets tronqués)
**When** on l'ingère dans un Corpus
**Then** le Document est signalé et ignoré, et l'ingestion des autres Documents continue

**Given** un `ParsedCorpus` qui contient ce PDF
**When** on appelle `resolve("docs/registre.pdf", 2, ())` puis `resolve("docs/registre.pdf", 9, ())`
**Then** la première renvoie `<doc_id>#p2` et la seconde `None`

### Story 2.4 : Profil de corpus et commande `wl corpus profiler`

As a Anaël,
I want obtenir par une commande le Profil d'un Corpus,
So that je le situe sur la Matrice de conviction et que le banc juge l'applicabilité des Architectures à contexte long.

**Exigences :** FR-7 ; AD-1, AD-17 (tokenizers) ; `contracts.md` §1 (`CorpusProfile`), §8.

**Acceptance Criteria:**

**Given** un petit `ParsedCorpus` de test aux valeurs connues (3 Documents, profondeurs de titres 1, 2 et 3, un tableau de 20 tokens sur 200, 2 images, 2 Documents en français et 1 en anglais)
**When** on appelle `corpus/profile.py`
**Then** `n_documents`, `n_tokens`, `mean_tokens_per_document`, `heading_depth_max` (3), `heading_depth_mean` (2,0), `table_share` (0,1), `images_per_document`, `dominant_lang` (`fr`), `langs` et `formats` valent les valeurs attendues
**And** `tokenizer` nomme le tokenizer de référence utilisé, et `volatility` reprend la valeur déclarée dans `corpus.yaml`

**Given** `corpus/entities.py` et trois Documents dont deux mentionnent « Guilde d'Orvane »
**When** on calcule la densité de liens
**Then** `link_density` vaut 2/3, avec une extraction heuristique (séquences capitalisées hors début de phrase), sans réseau ni LLM

**Given** un profil de 50 000 tokens de référence et deux modèles du Catalogue, l'un `tokenizer: reference` et l'autre à `token_factor: "1.5"`
**When** on appelle `profile.tokens_for(model_id, catalog)`
**Then** il renvoie 50 000 pour le premier et 75 000 pour le second ; un modèle sans `token_factor` explicite utilise 1,2

**Given** la CLI
**When** on lance `wl corpus profiler <corpus.yaml> --parser auto` avec le profil `test`
**Then** `corpus_profile.json` est écrit (sérialisation `model_dump(mode="json")`) et un résumé en français s'affiche, avec le code de sortie 0
**And** un `corpus.yaml` invalide sort avec le code 2

### Story 2.5 : Mini-corpus fictif

As a Anaël,
I want un Mini-corpus inventé et publiable livré dans le dépôt,
So that toute la chaîne se teste sans réseau sur un univers qu'aucun modèle n'a appris.

**Exigences :** FR-8 (Documents, extras, scénario), NFR-4 ; AD-16 (fixture `minicorpus`) ; germe structurel (`corpora/minicorpus/`, `scripts/make_minicorpus_pdfs.py`).

**Acceptance Criteria:**

**Given** `corpora/minicorpus/corpus.yaml` (`publishable: true`, licence CC-BY-4.0) et `docs/`
**When** on déclare et ingère le Corpus avec le profil `test`
**Then** il compte entre 18 et 22 Documents en Markdown et en PDF, dans un univers contrefactuel cohérent (noms, lieux et dates inventés)
**And** on y trouve au moins un long Document structuré à trois niveaux de titres avec au moins deux tableaux, un groupe d'au moins quatre Documents liés par des entités partagées, deux versions contradictoires d'un même Document et au moins deux Documents en anglais (`lang: en`), le reste en français

**Given** les PDF du Mini-corpus
**When** on lance `uv run python scripts/make_minicorpus_pdfs.py`
**Then** il régénère à l'identique (contenu textuel) les PDF commités à partir de leurs sources, avec fpdf2
**And** le script utilise une police TTF libre commitée avec sa licence (par exemple DejaVu Sans dans `scripts/fonts/`), car les polices intégrées de fpdf2 sont limitées au latin-1 ; un texte avec « œ », « Œ », guillemets « » et tirets typographiques est rendu et ré-extrait à l'identique par `pdf_text`
**And** au moins un PDF a plusieurs pages, et un autre n'a aucun titre

**Given** le Corpus de base ingéré
**When** on compte ses tokens
**Then** il reste sous 60 000 tokens de référence ; le test utilise le tokenizer `approx` avec une marge (au plus 40 000 mots) pour ne rien télécharger

**Given** `corpora/minicorpus/scenario/` et `extras/`, hors de `docs/`
**When** on les inspecte
**Then** `scenario.yaml` (`contracts.md` §4.7) contient au moins une opération `add`, une `modify` et une `delete`, et ses fichiers sources existent
**And** `extras/` contient un document sentinelle aux faits uniques et un document piégé qui contient une injection indirecte
**And** au moins deux Documents portent des `rights_profiles` dans `corpus.yaml`

**Given** `tests/conftest.py`
**When** un test demande la fixture `minicorpus`
**Then** il reçoit le `ParsedCorpus` ingéré avec le profil `test`, mis en cache pour la session

### Story 2.6 : Application d'un Scénario de mise à jour à un Corpus

As a Anaël,
I want appliquer un Scénario de mise à jour reproductible à un Corpus,
So that le runner puisse ensuite mesurer coût, durée et Fraîcheur après mise à jour.

**Exigences :** FR-53 (fichier et application) ; AD-5, AD-10 ; `contracts.md` §2.1 (`CorpusChange`), §4.7.

**Acceptance Criteria:**

**Given** `corpus/scenario.py` et le `scenario.yaml` du Mini-corpus
**When** on le charge
**Then** les opérations sont lues dans l'ordre, `source` est résolu par rapport au fichier du scénario et `target` est un `source_path` du Corpus
**And** une opération `modify` ou `delete` sur un `target` absent du Corpus, ou un `source` introuvable, lève une `ConfigError` au chemin `operations[i]`

**Given** le `ParsedCorpus` du Mini-corpus et son scénario
**When** on applique le scénario
**Then** on obtient un `CorpusChange` (`added`, `removed` en `doc_id`, `modified` en couples ancien `doc_id` et nouveau Document) et un `corpus_after`
**And** dans `corpus_after`, le Document supprimé est absent, le Document modifié garde son `source_path` avec un nouveau `doc_id`, et le Document ajouté est présent
**And** `corpus_after.fingerprint` diffère du `fingerprint` d'origine, et le `ParsedCorpus` d'origine est inchangé

**Given** le même scénario appliqué deux fois au même Corpus
**When** on compare les résultats
**Then** ils sont identiques (`CorpusChange` et `fingerprint`)
**And** aucun fichier du dossier `docs/` n'est modifié sur disque

### Story 2.7 : Paliers de volume et commande `wl corpus paliers`

As a Anaël,
I want tirer des Paliers de volume emboîtés et reproductibles,
So that je mesure l'effet du volume sans que les Documents des Ancrages de référence disparaissent d'un Palier.

**Exigences :** FR-54 (tirage) ; AD-20, AD-22 (`required_paths`) ; `contracts.md` §4.1 (`tiers`), §8.

**Acceptance Criteria:**

**Given** `corpus/tiers.py`, le Mini-corpus, `tiers: {seed: 42, sizes: [5, 10, 20]}` et une liste `required_paths` de trois Documents
**When** on tire les Paliers
**Then** le Palier 5 est inclus dans le Palier 10, lui-même inclus dans le Palier 20, et les trois `required_paths` figurent dans chacun
**And** un second tirage avec la même graine donne les mêmes Paliers, et une autre graine donne un tirage différent sur les Documents non requis

**Given** `required_paths` plus nombreux que la plus petite taille
**When** on tire les Paliers
**Then** une `ConfigError` explique que le Palier ne peut pas contenir tous les Documents requis

**Given** une taille supérieure au nombre de Documents du Corpus
**When** on tire les Paliers
**Then** une `ConfigError` signale la taille au chemin `tiers.sizes[i]`

**Given** un Palier tiré
**When** on construit le sous-corpus correspondant
**Then** c'est un `ParsedCorpus` restreint à ces Documents, avec sa propre `fingerprint`

**Given** la CLI
**When** on lance `wl corpus paliers <corpus.yaml>`
**Then** elle affiche chaque taille et ses `source_path`, en français, et sort en 0 ; sans clé `tiers`, elle l'indique et sort en 0

## Epic 3 : Construire et geler un Jeu d'évaluation

Anaël génère des Questions candidates, les corrige dans le YAML, contrôle leurs Ancrages, passe le Filtre closed-book et gèle le jeu avec sa séparation dev / test (UJ-1). Le Jeu de référence du Mini-corpus est livré gelé.

### Story 3.1 : Format des Questions et commande `wl questions controler`

As a Anaël,
I want un fichier de Questions éditable à la main et une commande qui le contrôle,
So that je valide, corrige ou rejette des Questions dans mon éditeur, et qu'aucun Ancrage faux ne passe.

**Exigences :** FR-9, FR-11 ; AD-5, AD-6 (lecture de la référence dans `evalset/` seulement), AD-12, AD-15 ; `contracts.md` §1 (`Question`, `AnchorRef`), §4.5, §8.

**Acceptance Criteria:**

**Given** `evalset/io.py` et un `questions.yaml` conforme à `contracts.md` §4.5
**When** on le charge
**Then** on obtient le `corpus_id`, `target_count`, `freeze` et un tuple de `Question`, dans l'ordre du fichier
**And** l'écriture par `io.save` puis une relecture redonne le même contenu, avec l'ordre des Questions et des clés préservé

**Given** un fichier dont l'enregistrement 12 a un `type` inconnu, et un autre dont deux Questions partagent un `id`
**When** on le charge
**Then** la `ConfigError` porte le chemin `questions[12].type`, puis `questions[j].id` pour le doublon

**Given** une Question `unanswerable` avec des `reference_anchors`, ou une Question d'un autre type sans Ancrage
**When** on contrôle le fichier
**Then** chacune est signalée avec son `id`

**Given** `evalset/check.py`, le `ParsedCorpus` d'un Corpus et une Question `validated` dont un Ancrage cite la page 9 d'un PDF de 3 pages
**When** on lance `wl questions controler <questions.yaml> --corpus <corpus.yaml>`
**Then** la commande affiche le nombre de Questions par statut et par Type, et l'écart à `target_count`
**And** elle liste la Question et l'Ancrage introuvables, puis sort avec le code 2
**And** une Question `generated` ou `rejected` à l'Ancrage introuvable est seulement signalée, sans faire échouer la commande

**Given** une Question `scenario_target: {operation: op-1, state: after}` dont l'Ancrage est dans un Document ajouté par le Scénario
**When** on lance `wl questions controler ... --scenario <scenario.yaml>` (option ajoutée à `contracts.md` §8, sans effet sur les autres options)
**Then** ses Ancrages sont résolus dans `corpus_after` (story 2.6), et les autres Questions dans le Corpus de base
**And** sans `--scenario`, ces Questions sont signalées comme non vérifiables, sans faire échouer la commande

**Given** une Question `answer_form: short` dont la Réponse de référence dépasse 5 mots et n'est ni un nombre ni une date
**When** on contrôle
**Then** elle est signalée comme incohérente avec la forme déclarée (FR-36)

### Story 3.2 : Contexte d'exécution concret

As a agent de développement,
I want un `RunContext` concret, utilisable par les commandes hors Exécution comme par le futur runner,
So that la génération de questions et le Filtre closed-book passent par la passerelle mesurée, avec un poste de coût fixé et un aléa contrôlé.

**Exigences :** FR-4, FR-29, FR-33 ; AD-2 (`ctx.build`), AD-8, AD-20, AD-21 ; `contracts.md` §2.4.

**Acceptance Criteria:**

**Given** `runner/context.py` construit à partir d'une Expérience résolue (ou d'un profil seul pour une commande hors Exécution), d'un `WL_HOME` et d'un `run_id`
**When** on l'instancie avec le profil `test`
**Then** il expose `gateway` (passerelle mesurée avec le provider de chaque modèle d'après le Catalogue), `tracer`, `tokenizer`, `catalog`, `profile`, `seed`, `condition`, `tier` et `phase`, et satisfait le Protocol `ports.context.RunContext` (vérifié par pyright)

**Given** le context manager du runner `ctx.scope(post="evalset", question_id="q-001")`
**When** un Composant appelle la passerelle dans ce bloc
**Then** le span porte `wl.post=evalset` et `wl.question_id=q-001`, et ces valeurs reprennent leurs valeurs précédentes à la sortie du bloc
**And** `post` et `question_id` sont en lecture seule pour les Composants

**Given** `ctx.build("embedder", ComponentSpec(name="fake"))`
**When** on l'appelle
**Then** le Composant est construit par `cls(params, ctx)` après validation de ses `Params`, et un paramètre inconnu lève une `ConfigError`

**Given** `ctx.rng("split", "factual")` appelé deux fois avec la même graine, puis avec une autre graine
**When** on tire dix nombres
**Then** les deux premiers tirages sont identiques et le troisième diffère

**Given** une Exécution déjà en cours qui détient `WL_HOME/run.lock`
**When** on crée un second contexte d'Exécution
**Then** il échoue avec le message « Exécution <run_id> en cours » ; un contexte de commande hors Exécution ne prend pas le verrou

### Story 3.3 : Génération de Questions candidates

As a Anaël,
I want générer des Questions candidates pour un Corpus selon une répartition par Type,
So that je parte d'un brouillon ancré au lieu d'une page blanche, sans dépasser mon plafond.

**Exigences :** FR-10, FR-33, FR-34 ; AD-3, AD-4 (rôle `question_gen`), AD-8 (poste `evalset`), AD-20 ; `contracts.md` §3, §8.

**Acceptance Criteria:**

**Given** `evalset/generate.py`, le Mini-corpus, le profil `test` et la répartition `factual=3,multi_hop=1,unanswerable=1`
**When** on lance `wl questions generer <corpus.yaml> --repartition factual=3,multi_hop=1,unanswerable=1`
**Then** les Questions ajoutées au fichier ont `status: generated`, `origin: {kind: model, name: <modèle>}`, un `id` neuf qui ne réutilise aucun identifiant existant, et `split: null`
**And** les Questions existantes du fichier sont conservées sans modification

**Given** une sortie du modèle (scénarisée) qui cite un `anchor_id` absent du Corpus
**When** on génère
**Then** la Question est écartée et comptée dans le résumé « rejetées à la génération », car chaque Question générée porte au moins un Ancrage vérifié, sauf `unanswerable`
**And** les Ancrages retenus sont écrits sous la forme `{doc, page}` ou `{doc, headings}` (AD-5)

**Given** l'appel de génération
**When** il passe par la passerelle
**Then** le rôle est `question_gen`, les `inputs` contiennent `anchors` et `types`, et le span porte `wl.post=evalset`
**And** une seconde génération identique est servie par le Cache de réponses, avec un coût nul

**Given** un plafond insuffisant
**When** on génère
**Then** aucune Question n'est écrite pour l'appel refusé, la commande sort avec le code 3, et les Questions déjà validées dans le fichier sont intactes

**Given** les Ancrages présentés au modèle
**When** on génère deux fois avec la même graine
**Then** l'échantillon d'Ancrages est le même (AD-20)

### Story 3.4 : Juge LLM et correspondance exacte normalisée

As a Anaël,
I want un Juge qui note plusieurs Critères en un appel, et une correspondance exacte pour les réponses courtes,
So that le Filtre closed-book puis le Panel notent les Réponses de façon reproductible et peu coûteuse.

**Exigences :** FR-36, FR-12 (critère de réussite), FR-34 (`pass_id`) ; AD-4 (rôle `judge`), AD-14 ; `contracts.md` §2 (`Judge`, `JudgeInput`), §3.

**Acceptance Criteria:**

**Given** le Composant `components/judges/llm.py`, enregistré `("judge", "llm")` avec un `model` en `ModelRef`
**When** on appelle `judge(item, ["correctness", "completeness", "faithfulness"], pass_id=0)` avec le Faux LLM
**Then** un seul appel au rôle `judge` est émis, et le résultat donne pour chaque Critère un verdict booléen et une justification courte
**And** une sortie non conforme après un nouvel essai lève `NonConformantOutput`

**Given** deux appels identiques avec `pass_id` 0 puis 1
**When** on juge
**Then** le second n'est pas servi par le Cache de réponses (FR-34)

**Given** `scoring/answer.py` et la fonction `exact_match(reference, answer)`
**When** la référence vaut « 1 412 » et la réponse « La guilde fut fondée en 1412. »
**Then** elle renvoie vrai, après normalisation de la casse, des accents, de la ponctuation et du format des nombres
**And** « Élodie Varn » correspond à « elodie varn », « 3,5 » à « 3.5 », et « 1413 » ne correspond pas à « 1412 »
**And** la fonction `is_short_form(reference)` reconnaît un nombre, une date ou une expression d'au plus 5 mots

**Given** le Critère `faithfulness`
**When** on construit le `JudgeInput`
**Then** `context_texts` reprend les textes fournis au Generator (AD-6), jamais une reconstruction

### Story 3.5 : Filtre closed-book et commande `wl questions closed-book`

As a Anaël,
I want poser chaque Question sans contexte à plusieurs modèles,
So that je sache quelles Questions un modèle connaît déjà et que leurs scores soient lus à part.

**Exigences :** FR-12 ; AD-8 (poste `judging`), AD-14 (Juge du Filtre closed-book), AD-15 ; `contracts.md` §3 (rôle `closed_book`), §8.

**Acceptance Criteria:**

**Given** `evalset/closed_book.py`, un fichier de Questions et les modèles `fake-llm-a` et `fake-llm-b`
**When** on lance `wl questions closed-book <questions.yaml> --modeles fake-llm-a,fake-llm-b`
**Then** chaque Question `validated` ou `corrected` est posée sans contexte à chaque modèle, au rôle `closed_book`, et les Questions `unanswerable` ne passent pas le filtre
**And** sans `--modeles`, la liste vient de `closed_book_models` du profil

**Given** une Question à réponse courte et un modèle dont la sortie scénarisée contient la Réponse de référence
**When** on applique le filtre
**Then** la Question reçoit `contaminated_by: [<modèle>]`, par correspondance exacte normalisée et sans Juge

**Given** une Question à réponse libre
**When** un modèle de famille `fake-a` y répond
**Then** le verdict de `correctness` vient du Juge `closed_book_judge` (premier modèle du réservoir d'une autre famille), et la Question est marquée contaminée si ce verdict est « oui »

**Given** le Faux LLM par défaut, qui renvoie la question inchangée
**When** on filtre le Jeu du Mini-corpus
**Then** aucune Question n'est contaminée

**Given** un Jeu déjà Gelé
**When** on relance le filtre
**Then** seul `contaminated_by` change, l'empreinte du Gel reste valide (AD-15), et les spans portent `wl.post=judging`

### Story 3.6 : Gel et séparation développement / test

As a Anaël,
I want geler un Jeu d'évaluation et le répartir en parties dev et test stratifiées,
So that aucune Exécution ne tourne sur un jeu modifié en douce et que la partie test reste réservée.

**Exigences :** FR-13, SM-C2 ; AD-15, AD-20 ; `contracts.md` §4.5, §8.

**Acceptance Criteria:**

**Given** `evalset/freeze.py` et un Jeu de 50 Questions `validated` réparties sur cinq Types
**When** on lance `wl questions geler <questions.yaml> --dev-ratio 0.4 --graine 42`
**Then** chaque Question participante reçoit `split: dev` ou `split: test`, stratifié par `type`, avec 40 % de dev dans chaque Type (arrondi documenté)
**And** `freeze` vaut `{sha256, at, seed, dev_ratio}`, où `sha256` est l'empreinte de `canonical_json` du document sans `freeze` ni `contaminated_by`
**And** un second Gel avec la même graine sur le même contenu produit la même répartition

**Given** un Jeu Gelé, puis une Question dont on modifie le texte
**When** on appelle `verify_frozen(questions)`, que le runner utilisera
**Then** elle lève une `ConfigError` qui signale une empreinte différente ; un Jeu non Gelé est refusé de même

**Given** un Jeu Gelé dont seul `contaminated_by` a changé
**When** on appelle `verify_frozen`
**Then** l'empreinte reste valide

**Given** `select_questions(questions, split="dev")`
**When** on l'appelle
**Then** elle ne renvoie que les Questions `validated` ou `corrected` de la partie dev ; la partie test n'est renvoyée que pour `split="test"` explicite

**Given** un Jeu contenant des Questions `generated`
**When** on le gèle
**Then** la commande les signale et refuse de geler tant qu'elles ne sont pas validées, corrigées ou rejetées

### Story 3.7 : Jeu d'évaluation de référence du Mini-corpus

As a Anaël,
I want un Jeu d'évaluation de référence gelé pour le Mini-corpus,
So that chaque Architecture se teste de bout en bout sur des Questions dont les Ancrages sont garantis.

**Exigences :** FR-8 (Jeu de référence), FR-9, FR-11, FR-13 ; AD-15, AD-16.

**Acceptance Criteria:**

**Given** `corpora/minicorpus/questions.yaml`
**When** on lance `wl questions controler` sur le Mini-corpus, avec `--scenario` pointant son scénario
**Then** la commande sort en 0, avec au moins 40 Questions `validated`, `origin: {kind: model, name: claude-code-dev-agent}` et `target_count: 40`
**And** tous les Types de question sont couverts sauf `visual` et `numeric_aggregation`, avec au moins deux `follow_up` (historique renseigné), deux `cross_lingual` et trois Questions avec `scenario_target` qui renvoient à des opérations du scénario
**And** au moins une Question `unanswerable` porte sur un fait absent du Corpus, et au moins une `knowledge_trap` contredit une connaissance générale

**Given** les Questions de type `factual`
**When** on les inspecte
**Then** au moins cinq ont une Réponse de référence `short`, et au moins une cite une page de PDF

**Given** la Question de conformité, constante `CONFORMANCE_QUESTION_ID` de `tests/conftest.py`, de type `factual` et à un seul Ancrage
**When** un test applique les règles du Faux LLM (`contracts.md` §3) à son texte et au texte de son Ancrage
**Then** au moins 80 % des mots de la Question figurent dans l'Ancrage, si bien que `grade_relevance` dépasse le seuil de 0,5 (Corrective RAG, LazyGraphRAG) et que BM25, le faux embedder et `select_nodes` la retrouvent
**And** la suite de conformité (story 4.14) pose cette Question pour vérifier la Citation valide, au lieu d'une Question factuelle quelconque

**Given** le fichier livré
**When** on appelle `verify_frozen`
**Then** le Jeu est Gelé avec la graine 42 et un ratio de 0,4, et l'empreinte est valide

**Given** un test de non-régression
**When** on modifie une Question du fichier dans une copie temporaire
**Then** `verify_frozen` refuse la copie, ce qui prouve que le fichier commité est bien protégé

## Epic 4 : Comparer les Baselines de bout en bout et lire le Rapport

Anaël lance `wl run` sur une Expérience qui compare les trois Baselines. Les Conditions standard et contexte parfait sont disponibles, ainsi qu'un Scénario de mise à jour et des Paliers. L'Exécution s'arrête au plafond et reprend sans repayer. Anaël obtient un Rapport complet (UJ-2). La suite de conformité commune est en place pour toute Architecture future (UJ-4).

### Story 4.1 : Découpage, contexte étiqueté et Generator LLM

As a agent de développement,
I want un chunker, un ContextBuilder à étiquettes et un Generator qui convertit les étiquettes en Citations,
So that toute Architecture produise des Réponses citées de la même façon, sans inventer son format.

**Exigences :** FR-15, FR-18 (Citations hors contexte retirées), FR-36 (Citations) ; AD-4 (rôle `generate`), AD-5 (`passage_id`), AD-6, AD-7 ; `contracts.md` §1 (`Passage`, `ArchAnswer`), §2 (`Chunker`, `ContextBuilder`, `Generator`).

**Acceptance Criteria:**

**Given** le chunker `fixed_tokens` (`size: 300`, `overlap: 50`), enregistré `("chunker", "fixed_tokens")`
**When** on découpe un Document du Mini-corpus avec le tokenizer du contexte
**Then** chaque Passage a `level: 0`, son `doc_id`, des `anchor_ids` non vides limités à ce Document, et `passage_id = sha16(doc_id, chunker_key, ordinal)`
**And** un Passage à cheval sur deux sections porte les deux Ancrages, et `key()` change quand `size` ou `overlap` change

**Given** le ContextBuilder `labeled` et trois Passages
**When** on construit le Contexte
**Then** `text` concatène des blocs `[S1] (<ancrage>) <texte>` dans l'ordre reçu, `blocks` contient un bloc par étiquette, et `labels` et `passage_ids` associent chaque étiquette à ses `anchor_ids` et à son `passage_id`

**Given** le Generator `llm` (`model` en `ModelRef` `answer_producer`, `max_tokens`) et une sortie qui cite `S1` et `S9`, absent du Contexte
**When** on génère
**Then** `GenerationResult.citations` ne contient que les Ancrages de `S1`, et `invalid_citations` vaut 1
**And** les `inputs` du rôle `generate` contiennent `question` et `blocks` ; avec un Contexte vide, le Faux LLM s'abstient et `abstained` est vrai, distinct du texte (FR-15)
**And** l'historique de conversation de `QuestionInput` est transmis en messages

**Given** l'utilitaire `build_arch_answer(context, result, retrieved, method)` de `components/context/`
**When** le Contexte dépasse 8 000 tokens
**Then** `context_texts` ne garde que les blocs cités et `context_truncated` est vrai ; sinon, `context_texts` reprend `Context.blocks`
**And** `context_anchor_ids` reprend l'union des Ancrages fournis au Generator

### Story 4.2 : Baselines sans contexte, contexte long et BM25 seul

As a Anaël,
I want trois Baselines de référence,
So that toute Architecture du niveau 1 se compare à « sans contexte », « tout le Corpus » et « BM25 ».

**Exigences :** FR-16, FR-3 (inapplicable), FR-14, FR-35 (méthode) ; AD-2, AD-10 (écriture dans le dossier reçu), AD-13 ; `contracts.md` §2.1.

**Acceptance Criteria:**

**Given** l'Architecture `no_context`
**When** on l'indexe puis on lui pose une Question du Mini-corpus avec le Faux LLM
**Then** le Generator reçoit un Contexte vide, la Réponse a `retrieval_method: none` et `retrieved` est vide, et aucun fichier d'index n'est requis hors `passages.jsonl` vide

**Given** l'Architecture `long_context` (`capabilities.full_corpus_in_prompt`), un Generator `fake-llm-a` et le Mini-corpus
**When** on l'indexe puis on répond
**Then** le prompt contient un bloc étiqueté par Ancrage de tout le Corpus, dans l'ordre des Documents, avec le system mis en cache (`cache_system`)
**And** la Réponse a `retrieval_method: cited` : un `ScoredPassage` par Ancrage cité, rang dans l'ordre de première citation, score 1,0

**Given** `long_context.check(profile)` avec un profil de 120 000 tokens et un modèle de fenêtre 100 000
**When** on vérifie l'applicabilité
**Then** elle renvoie `applicable: false` et une raison qui cite la fenêtre, sans exception
**And** pour `claude-haiku-5-5`, un prompt estimé (`tokens_for`) au-delà de 100 000 tokens renvoie `applicable: false`, avec une raison qui cite le palier tarifaire (FR-16)

**Given** le lexical index `bm25` (bm25s), enregistré `("lexical_index", "bm25")`, et le retriever `lexical`
**When** on indexe le Mini-corpus et on cherche « guilde Orvane fondation » avec `k: 5`
**Then** au plus 5 identifiants sont renvoyés, par score décroissant, ex æquo départagés par id, et `save` puis `load` dans un autre dossier redonnent les mêmes résultats
**And** `delete` retire un Passage des résultats

**Given** l'Architecture `bm25_only` (chunker, `bm25`, retriever `lexical`, ContextBuilder, Generator, `k: 5`)
**When** on l'indexe dans un dossier puis on construit une instance neuve qui fait `load` de ce dossier
**Then** `passages.jsonl` contient un Passage par ligne, et la Réponse expose les k Passages classés (`retrieval_method: ranked`) et au moins une Citation valide sur une Question factuelle
**And** `k` est déclaré dans `query_params`

### Story 4.3 : Cache d'index et dossier d'Exécution

As a Anaël,
I want que les index déjà construits soient réutilisés et que chaque Exécution ait son dossier,
So that je ne paie jamais deux fois la même indexation et que chaque résultat soit retrouvable.

**Exigences :** FR-28, FR-1 (Expérience résolue à côté des résultats), FR-4 ; AD-10, AD-11 ; `contracts.md` §2.1 (cycle de vie), §5.

**Acceptance Criteria:**

**Given** `runner/index_cache.py`, une Architecture `bm25_only` et le Mini-corpus
**When** on demande l'index une première fois
**Then** l'Architecture écrit dans `index/.tmp-<index_key>/`, le runner ajoute `manifest.json` (`index_key`, `architecture`, `corpus_fingerprint`, `created_at`, `embedder_dim` s'il y en a un), puis renomme par `os.replace` vers `index/<index_key>/`
**And** `index_key = sha16(canonical_json({corpus_fingerprint, architecture, index_key()}))`, et `index_key()` par défaut prend les Params résolus moins `query_params`, plus le parser résolu et le nom du tokenizer

**Given** l'index déjà présent
**When** on le redemande
**Then** `index` n'est pas appelé, une instance neuve fait `load`, et un span `local` `index` porte `wl.index_cache_hit=true`

**Given** une exception levée pendant `index`
**When** le cache la reçoit
**Then** aucun dossier `index/<index_key>/` n'existe, et le dossier temporaire est supprimé ou ignoré à la reprise

**Given** deux Configurations qui ne diffèrent que par `k`
**When** on calcule leurs clés
**Then** elles sont égales ; changer `size` du chunker change la clé

**Given** `runner/rundir.py` et un `run_id`
**When** on crée le dossier d'Exécution
**Then** `runs/<run_id>/` contient `experiment.resolved.yaml`, `experiment.sha256` et `manifest.json` (`status: running`, profil, `models_frozen_at`, liste des modèles), écrits avant tout appel
**And** les fichiers JSONL sont ouverts en ajout seulement, en UTF-8 avec LF, et seul le runner y écrit

### Story 4.4 : Exécution d'une Expérience par `wl run`

As a Anaël,
I want lancer une Expérience par une seule commande et obtenir une Réponse par Question et par Configuration,
So that la comparaison des Baselines tourne sans intervention, même si une Question échoue.

**Exigences :** FR-1, FR-3 (inapplicable), FR-13, FR-15, NFR-7 ; AD-6, AD-11, AD-13, AD-15 ; `contracts.md` §1 (`Answer`), §5.

**Acceptance Criteria:**

**Given** une Expérience au profil `test` sur le Mini-corpus, avec les trois Baselines et `split: dev`
**When** on lance `wl run <experience.yaml>`
**Then** le runner enchaîne, dans l'ordre d'AD-11, chargement, validation, préflight, ingestion, profilage (`corpus_profile.json`), `check()` par Configuration, index ou cache, puis `answer` par Question
**And** `answers.jsonl` contient un `Answer` par (config_id, condition, tier, phase, question_id), avec `answer_id` au format de `contracts.md` §1 (`tier = "all"` sans palier)
**And** le manifeste passe à `completed` et la commande sort en 0

**Given** le Jeu non Gelé, ou modifié après le Gel
**When** on lance `wl run`
**Then** l'Exécution est refusée avant tout appel, avec le code 2 (AD-15) ; seules les Questions `validated` et `corrected` de la partie demandée sont posées

**Given** une Configuration `long_context` inapplicable pour le Corpus
**When** on lance `wl run`
**Then** elle figure dans `applicability.json` avec sa raison, ses Questions ont `status: inapplicable`, et les autres Configurations s'exécutent

**Given** une Question dont l'appel lève `NonConformantOutput` (sortie scénarisée)
**When** on lance `wl run`
**Then** son `Answer` a `status: error` et un message, et l'Exécution continue sur les Questions suivantes

**Given** `max_questions: 3`
**When** on lance `wl run`
**Then** seules les trois premières Questions de la partie, dans l'ordre des `id`, sont posées

### Story 4.5 : Mesure de l'Exécution : postes, latence, énergie et rejeu

As a Anaël,
I want que chaque appel d'une Exécution soit imputé au bon Poste et que la latence et l'énergie de chaque Question soient relevées,
So that le Rapport s'appuie sur des Traces complètes et qu'un rejeu ne coûte rien.

**Exigences :** FR-4, FR-18 (Citations hors contexte comptées dans la Trace), FR-29, FR-31 (postes), FR-32 (énergie locale par phase) ; AD-3 (une Architecture ne trace pas), AD-8, AD-17, AD-20 ; `contracts.md` §1 (`Answer.latency_s`), §6.

**Acceptance Criteria:**

**Given** une Exécution des trois Baselines au profil `test`
**When** on lit `traces.jsonl`
**Then** les spans portent `wl.post=indexing` pendant `index` et `load`, et `wl.post=query` pendant `answer`, fixés par les context managers du runner (`ctx.scope`), jamais par un Composant
**And** chaque Question a un span `local` `answer` émis par le runner, qui porte `wl.invalid_citations` et le `wl.question_id`

**Given** les `Answer` écrits
**When** on les compare aux spans
**Then** `latency_s` de chaque `Answer` égale la somme des `wl.latency_s` des spans `query` de sa Question

**Given** l'énergie `fake` du profil `test`
**When** l'Exécution passe les phases index et query d'une Configuration
**Then** l'énergie locale est relevée par phase et par Configuration, puis répartie sur les spans locaux de la phase au prorata de leur latence (AD-17), avec `wl.energy_method`

**Given** la même Expérience relancée avec les mêmes caches
**When** on compare les deux `answers.jsonl`
**Then** les Passages retrouvés et les Réponses sont identiques, et aucun span n'a de coût non nul (FR-4)
**And** chaque index est servi par le cache (`wl.index_cache_hit=true`) et chaque appel LLM par le Cache de réponses (`wl.llm_cache_hit=true`)

### Story 4.6 : Condition contexte parfait et Paliers de volume

As a Anaël,
I want exécuter une Configuration en contexte parfait et sur chaque Palier de volume,
So that j'isole la qualité du Generator et que je mesure l'effet du volume.

**Exigences :** FR-17, FR-54 ; AD-6, AD-22 ; `contracts.md` §2.1 (`answer_with_context`), §4.4 (`conditions`, `tier`).

**Acceptance Criteria:**

**Given** `conditions: [standard, perfect_context]`
**When** on lance `wl run`
**Then** pour chaque Question, le runner construit un Passage par Ancrage de référence (`level 0`, texte de `ParsedCorpus.anchor_text`), dans l'ordre des `reference_anchors`, et appelle `answer_with_context`
**And** l'Architecture ne reçoit que `QuestionInput` et ces Passages, jamais la Réponse de référence (vérifié par un Generator espion du test)
**And** une Question `unanswerable` reçoit un Contexte vide, et les `Answer` portent `condition: perfect_context`

**Given** `tier: all` et `tiers.sizes: [5, 10, 20]`
**When** on lance `wl run`
**Then** les `required_paths` sont les Documents des Ancrages de référence des Questions posées, et chaque Palier est indexé sur son sous-corpus, avec sa propre `index_key`
**And** les `Answer` et les spans portent `tier`, et chaque Palier est une ligne distincte d'`answers.jsonl`

**Given** `tier: 10`
**When** on lance `wl run`
**Then** seul le Palier 10 s'exécute ; une taille non déclarée est refusée à la validation (code 2)

### Story 4.7 : Phase après mise à jour

As a Anaël,
I want appliquer un Scénario de mise à jour pendant l'Exécution,
So that je mesure coût, durée et Fraîcheur de chaque Architecture après une mise à jour.

**Exigences :** FR-53, FR-14 (réindexation des Architectures sans mise à jour incrémentale), FR-28 (nouvelle entrée de cache) ; AD-8, AD-10 ; `contracts.md` §2.1 (étape 5).

**Acceptance Criteria:**

**Given** `scenario: ../corpora/minicorpus/scenario/scenario.yaml`
**When** on lance `wl run`
**Then** après la phase `base`, le runner applique le scénario (story 2.6), appelle `update(change, corpus_after, old_dir, tmp_dir)`, renomme vers le dossier de la nouvelle clé, construit une instance neuve qui fait `load`, puis repose les Questions en phase `after_update`
**And** l'ancien dossier d'index est intact et toujours réutilisable par une autre Exécution

**Given** une Architecture `incremental_update: false`
**When** la mise à jour a lieu
**Then** l'implémentation par défaut réindexe tout `corpus_after`, et ses spans portent `wl.post=update`

**Given** les Questions liées au Scénario
**When** on lit les `Answer` de la phase `after_update`
**Then** aucun Passage retrouvé ni aucune Citation ne désigne le Document supprimé (doc_id ancien), et les Ancrages des Documents modifiés pointent vers leur nouveau `doc_id`

**Given** une Exécution relancée avec les mêmes caches
**When** la phase `after_update` démarre
**Then** l'index après mise à jour est servi par le cache (`wl.index_cache_hit=true`)

### Story 4.8 : Arrêt au plafond et reprise d'une Exécution

As a Anaël,
I want qu'une Exécution s'arrête proprement au plafond et reprenne sans repayer,
So that un run de nuit ne dépense jamais plus que prévu et ne perde jamais ce qui a été payé.

**Exigences :** FR-33, FR-34, NFR-8 ; AD-9, AD-11 ; `contracts.md` §5.

**Acceptance Criteria:**

**Given** une Expérience au profil `test` dont le plafond par Exécution ne couvre que les cinq premiers appels payants
**When** on lance `wl run`
**Then** le sixième appel est refusé avant émission, les `Answer` déjà produits restent dans `answers.jsonl`, les Questions non traitées sont `budget_exceeded`, le manifeste passe à `budget_exceeded`, et la commande sort avec le code 3

**Given** cette Exécution arrêtée et un plafond relevé
**When** on lance `wl run <experience.yaml> --reprendre <run_id>`
**Then** le runner relit `answers.jsonl`, saute les clés présentes et ne fait que les appels manquants (la reprise du jugement, par `verdicts.jsonl`, arrive avec la story 4.9)
**And** les appels déjà payés et refaits sortent du Cache de réponses à coût nul : la somme des `wl.cost` de `traces.jsonl` égale la dépense réelle du registre pour ce `run_id`
**And** `traces.jsonl` n'est jamais réécrit, seulement complété

**Given** une Exécution tuée brutalement au milieu d'un appel (simulée)
**When** on la reprend
**Then** la réservation orpheline a été réglée au montant estimé, et le manifeste repasse à `running` puis à `completed`

**Given** une reprise avec une Expérience dont l'empreinte diffère de `experiment.sha256`
**When** on lance la reprise
**Then** elle est refusée avec le code 2

**Given** une seconde commande `wl run` pendant une Exécution
**When** on la lance
**Then** elle sort avec le code 1 et le message « Exécution <run_id> en cours »

### Story 4.9 : Métriques de recherche, Critères automatiques et Panel de juges

As a Anaël,
I want que chaque Réponse soit notée sur chaque Critère, automatiquement ou par un Panel multi-familles,
So that je lise des verdicts fiables, Critère par Critère, sans score global.

**Exigences :** FR-35, FR-36, FR-37, FR-12 (contaminées) ; AD-6, AD-8 (poste `judging`), AD-14, AD-22 ; `contracts.md` §1 (`Verdict`), §5 (`verdicts.jsonl`, `panel.jsonl`), §7.

**Acceptance Criteria:**

**Given** `scoring/retrieval.py`, une Question à deux Ancrages de référence et cinq Passages classés dont les rangs 2 et 4 recouvrent un Ancrage de référence
**When** on calcule les métriques
**Then** rappel@5, MRR (0,5) et nDCG@5 valent les valeurs calculées à la main dans le test, et un Passage est pertinent dès que ses `anchor_ids` recoupent les Ancrages de référence, quel que soit le Découpage
**And** pour `retrieval_method` `provided`, `cited` ou `none`, la méthode est reportée, et `none` ne produit aucune métrique

**Given** `scoring/answer.py`
**When** on calcule les Critères automatiques
**Then** `citation_correctness` vaut oui si au moins une Citation désigne un Ancrage de référence et aucune n'est hors du Corpus ; pour une Question `unanswerable`, oui si la Réponse ne cite rien
**And** `abstention_correctness` vaut oui si `abstained` est vrai exactement quand la Question est `unanswerable`
**And** `correctness` est calculé par `exact_match` pour `answer_form: short`, avec `judge_model: "auto"`

**Given** `scoring/panel.py` et une Exécution au Panel `[fake-llm-b, fake-llm-c]` pour un Generator `fake-llm-a`
**When** le runner juge les `Answer` `ok`, au poste `judging`
**Then** chaque Juge note `correctness` (sauf réponse courte), `completeness` et `faithfulness` en un appel par Réponse, sur `JudgeInput` construit avec `context_texts`, et écrit un `Verdict` par (answer_id, judge_model, criterion, pass_id) dans `verdicts.jsonl`
**And** `panel.jsonl` donne le verdict majoritaire par (answer_id, criterion) et les Juges admissibles ; une égalité donne `no` et `tie: true`
**And** les Juges exclus par `judges.excluded_from` ne sont pas appelés

**Given** une Réponse `error`, `inapplicable` ou `budget_exceeded`
**When** le runner juge
**Then** aucun Juge n'est appelé pour elle

**Given** une Exécution reprise par `--reprendre` après un arrêt pendant le jugement
**When** le runner juge
**Then** il relit `verdicts.jsonl` et ne demande que les (answer_id, judge_model, criterion, pass_id) absents (AD-11)

### Story 4.10 : Statistiques : bootstrap, McNemar et fronts de Pareto

As a Anaël,
I want des intervalles de confiance et des comparaisons appariées reproductibles,
So that je sache si une différence entre deux Configurations est réelle.

**Exigences :** FR-39, FR-40 (fronts de Pareto) ; AD-20, AD-22 (`stats/` en fonctions pures) ; `contracts.md` §7.

**Acceptance Criteria:**

**Given** `stats/bootstrap.py` et un vecteur binaire de 100 valeurs avec 70 succès
**When** on calcule l'IC à 95 % avec 2 000 rééchantillons et la graine 42
**Then** l'IC par percentile reproduit, à 1e-9 près, celui de `scipy.stats.bootstrap(method="percentile")` avec le même générateur
**And** deux appels avec la même graine donnent le même IC

**Given** deux vecteurs appariés de scores continus
**When** on lance le bootstrap apparié
**Then** la différence moyenne, son IC et la p-valeur bilatérale sont renvoyés, et les valeurs se reproduisent sur des données synthétiques connues

**Given** `stats/mcnemar.py` et des paires discordantes b = 12 et c = 3
**When** on calcule le test exact
**Then** la p-valeur égale `scipy.stats.binomtest(3, 15, 0.5).pvalue`, et b = c = 0 donne une p-valeur de 1

**Given** `compare(a, b)` sur deux ensembles de Questions qui ne se recouvrent qu'en partie
**When** on compare
**Then** seules les Questions communes sont utilisées, et `n_common` est renvoyé

**Given** `stats/pareto.py` et cinq points (Qualité, coût), dont un dominé et deux à égalité
**When** on calcule le front
**Then** il contient les points non dominés (Qualité maximisée, coût minimisé), dans un ordre déterministe, ex æquo départagés par `config_id`

### Story 4.11 : Rapport : scores, recherche et comparaisons appariées

As a Anaël,
I want un Rapport Markdown et des CSV qui présentent scores, métriques de recherche et comparaisons,
So that je lise les résultats sans outil spécialisé et que je puisse tout réanalyser.

**Exigences :** FR-40, FR-12 (contaminées à part), FR-13 (partie indiquée), FR-17 (contexte parfait à part), FR-35, FR-36, FR-37, FR-39, FR-1 (comparaison deux à deux), FR-4 (modèles datés) ; AD-22 ; `contracts.md` §7, §8 (`wl rapport`).

**Acceptance Criteria:**

**Given** `report/` et une Exécution terminée sur les Baselines
**When** `wl run` termine, ou qu'on lance `wl rapport <run_id>` (c'est `cli.py` qui enchaîne le runner puis `report/` : AD-1 rend `runner` et `report` indépendants, et le runner n'importe jamais `report`, ce que `lint-imports` vérifie)
**Then** `report/report.md` contient l'Expérience résolue (lien et empreinte), le profil d'exécution, la partie utilisée, `models_frozen_at` et la liste des modèles, le Profil de corpus, le Panel admissible par Configuration, les Juges exclus et le nombre d'égalités
**And** toutes les grandeurs sont calculées à partir des seuls fichiers de l'Exécution, groupées par (config_id, condition, tier, phase)

**Given** les verdicts du Panel
**When** on produit `scores.csv`
**Then** il a les colonnes `config_id, condition, tier, phase, question_type, criterion, value, ci_low, ci_high, n`, par Critère et par Type de question, avec l'IC bootstrap de l'Expérience, et aucune colonne de score global
**And** la Qualité suit `contracts.md` §7 : `correctness` oui, ou `abstention_correctness` oui pour `unanswerable`

**Given** des Questions contaminées
**When** on produit le Rapport
**Then** elles sont exclues des scores principaux et rapportées dans une section à part ; les résultats en contexte parfait ont leur propre section étiquetée « contexte parfait »

**Given** `retrieval.csv` et `pairs.csv`
**When** on les produit
**Then** `retrieval.csv` donne rappel@k, MRR et nDCG@k par Configuration et par Type, avec la colonne `method` ; la Baseline `no_context` n'y figure pas
**And** `pairs.csv` donne pour chaque paire de Configurations `config_a, config_b, metric, diff, p_value, test, n_common` (McNemar pour la Qualité et les Critères, bootstrap apparié pour les métriques continues)

**Given** les Configurations inapplicables
**When** on produit le Rapport
**Then** elles sont listées avec leur raison, reprise d'`applicability.json`

**Given** une Exécution arrêtée au plafond
**When** on produit le Rapport
**Then** `wl run` le génère par `cli.py` sur les résultats partiels avant de sortir avec le code 3, et il l'indique en tête

### Story 4.12 : Rapport : coûts, énergie, latence et point mort

As a Anaël,
I want les coûts et l'énergie par Poste, la latence, le débit et le point mort,
So that je compare les Architectures sur ce qu'elles coûtent, consomment et font attendre, à Qualité comparable.

**Exigences :** FR-31, FR-32, FR-34, FR-29 (somme des Traces), FR-40, SM-C3 ; AD-9, AD-17, AD-22 ; `contracts.md` §4.2 bis, §7.

**Acceptance Criteria:**

**Given** `traces.jsonl` d'une Exécution
**When** on produit `costs.csv`
**Then** il a les colonnes `config_id, post, cost_eur_real, cost_eur_uncached, kwh_measured, kwh_estimated, co2e_g, n_calls`, et la conversion en euros utilise le taux daté de `CostSettings`, affiché avec sa date
**And** la somme des `wl.cost` des spans, convertie, égale le coût total affiché par le Rapport (FR-29)
**And** le coût local ajoute le Coût de possession (`measure/tco.py`), et `judging` et `evalset` sont affichés à part, hors coût d'une Configuration

**Given** des énergies `measured` et `estimated`
**When** on produit le Rapport
**Then** elles restent dans deux colonnes jamais additionnées, avec un avertissement que les deux périmètres ne se comparent pas, et le CO2e utilise l'intensité carbone déclarée

**Given** les `Answer` et les spans de la phase `query`
**When** on produit le Rapport
**Then** il affiche par Configuration la latence p50 et p95, le débit en Questions par minute (durée murale de la phase query, d'après les spans), le coût par requête et pour 1 000 requêtes

**Given** une Configuration A plus chère à l'indexation et moins chère à la requête que B
**When** A est de Qualité égale ou supérieure (`contracts.md` §7)
**Then** le point mort N* = (indexation_A − indexation_B) ÷ (requête_B − requête_A) est affiché
**And** si la Qualité de A est significativement inférieure, ou si requête_A ≥ requête_B, le Rapport écrit la raison au lieu d'un nombre

### Story 4.13 : Rapport : Fraîcheur, Paliers, fronts de Pareto et export du front

As a Anaël,
I want la Fraîcheur, les résultats par Palier, les fronts de Pareto en tête du Rapport et l'export d'un front,
So that je lise d'abord les Configurations non dominées et que je reparte du front dans une nouvelle Expérience.

**Exigences :** FR-40, FR-41, FR-53 (Fraîcheur), FR-54 (par Palier) ; AD-22 ; `contracts.md` §7, §8 (`--exporter-front`).

**Acceptance Criteria:**

**Given** une Exécution avec Scénario et Paliers
**When** on produit le Rapport
**Then** la Fraîcheur (part des Questions à `scenario_target` correctes en phase `after_update`) et les résultats par Palier ont leur section

**Given** les grandeurs par Configuration
**When** on produit `pareto.csv`
**Then** il donne les fronts Qualité × coût total, Qualité × énergie, Qualité × latence p95 et un front (taux du Critère, coût total) par Critère, au format `front, config_id, x, y`

**Given** le front Qualité × coût total
**When** on produit `report.md`
**Then** le Rapport s'ouvre, juste après son en-tête, sur un tableau de synthèse des Configurations de ce front : `config_id`, Qualité avec son IC, coût total en euros, latence p95. C'est le même front que dans `pareto.csv`, présenté en premier, sans score global ni pondération entre Critères (PRD §6)

**Given** `wl rapport <run_id> --exporter-front qualite-cout --vers <fichier>`
**When** on lance la commande
**Then** le fichier contient la liste `configurations:` des Configurations du front, que `config/load.py` accepte telle quelle dans une nouvelle Expérience (FR-41)

### Story 4.14 : Suite de conformité, Expériences livrées et test de bout en bout SM-3

As a agent de développement,
I want une suite de conformité paramétrée sur tout le registre et une Expérience de bout en bout,
So that toute Architecture ajoutée soit vérifiée automatiquement, sans réseau, avant d'être livrée.

**Exigences :** FR-14, FR-15, FR-17, FR-28, FR-53, SM-3, SM-C1 ; AD-10, AD-16 ; germe structurel (`experiments/`).

**Acceptance Criteria:**

**Given** `tests/conformance/test_architectures.py`, paramétré sur toutes les Architectures du registre après `discover()`, avec le profil `test` et le Mini-corpus
**When** on lance `uv run pytest -q tests/conformance`
**Then** il vérifie pour chaque Architecture :
- l'indexation ;
- une Réponse avec au moins une Citation valide sur la Question de conformité `CONFORMANCE_QUESTION_ID` (story 3.7), sauf pour `retrieval_method: none` ;
- toute Citation désigne un Ancrage existant du Corpus ;
- l'abstention par `answer_with_context` sur un contexte vide ;
- la mise à jour : le Document supprimé est absent des Passages retrouvés et des Citations ;
- la Condition contexte parfait ;
- des Réponses identiques avec et sans cache d'index ;
- un changement d'`index_key` quand on modifie un Param hors `query_params`.
**And** les trois Baselines passent

**Given** `experiments/mini-test.yaml` (profil `test`, toutes les Architectures du registre, `conditions: [standard, perfect_context]`, Scénario du Mini-corpus)
**When** on lance `tests/e2e/test_sm3.py`
**Then** `wl run` termine en `completed`, et le Rapport contient chacune des sections de FR-40 et les six fichiers CSV non vides
**And** un test vérifie que `mini-test.yaml` cite une Configuration par Architecture enregistrée : chaque story d'Architecture qui suit y ajoute la sienne

**Given** `experiments/mini-cpu.yaml` et `experiments/mini-real-haiku.yaml`
**When** on les charge et on les valide
**Then** ils sont valides sans réseau ; `mini-cpu` utilise le profil `cpu`, et `mini-real-haiku` le Generator `claude-haiku-5-5`, `max_questions: 5` et un plafond de 5,00 USD
**And** `mini-real-haiku` n'appelle aucun modèle local : réservoir de Juges `[fake-llm-b, fake-llm-c]`, embedder `fake`, pas de Filtre closed-book. Seule l'API Anthropic est sollicitée, pour pouvoir exécuter SM-4 pendant que l'Ollama local est réservé à un autre banc

### Story 4.15 : Test réel SM-4 sur Claude Haiku 5.5

As a Anaël,
I want un test réel borné sur l'API Anthropic,
So that je vérifie, au centime près, que le coût tracé égale le coût recalculé à partir des tokens renvoyés.

**Exigences :** SM-4, FR-29, FR-30, FR-33, NFR-2, NFR-3 ; AD-9, AD-16.

**Acceptance Criteria:**

**Given** `tests/real/test_sm4.py`, marqué `real_api`
**When** `ANTHROPIC_API_KEY` est absente
**Then** le test est sauté, et la suite par défaut ne le sélectionne jamais

**Given** une clé présente et `experiments/mini-real-haiku.yaml` (5 Questions, plafond de 5,00 USD)
**When** on lance `uv run pytest -m real_api tests/real/test_sm4.py`
**Then** l'Exécution termine sous le plafond
**And** pour chaque span payant, `wl.cost` égale `catalog.cost(model, usage)` calculé à partir des tokens renvoyés par l'API, et la somme des spans égale, au centime près, le coût total du Rapport et la dépense du registre pour ce `run_id`

**Given** les fichiers de l'Exécution réelle
**When** on y cherche la clé et l'en-tête `x-api-key`
**Then** on ne les trouve dans aucun fichier de `runs/<run_id>/`

## Epic 5 : Calibrer les juges sur des annotations humaines

Anaël annote des Réponses dans des fichiers YAML, lance `wl calibrer` et obtient les kappas juge-humain et inter-annotateurs, ainsi que le taux d'instabilité sur cinq passes. Les Juges sous le seuil sont exclus des Rapports suivants (UJ-3).

### Story 5.1 : Annotations humaines et kappa de Cohen

As a Anaël,
I want annoter des Réponses dans un fichier par annotateur et disposer d'un calcul de kappa fiable,
So that l'accord entre juges et humains se mesure sur des données que je contrôle.

**Exigences :** FR-38 (format et mesure) ; AD-5, AD-12, AD-22 (`stats/` en fonctions pures) ; `contracts.md` §4.6.

**Acceptance Criteria:**

**Given** `scoring/calibration.py` et un dossier `annotations/` contenant `anael.yaml` et `collegue.yaml` au format de `contracts.md` §4.6
**When** on charge les annotations
**Then** chaque annotation est indexée par (annotateur, `answer_id`, `criterion`), avec un verdict booléen
**And** un Critère hors de `correctness`, `completeness` et `faithfulness`, un verdict hors de `yes` et `no`, ou un doublon (même annotateur, `answer_id` et Critère) lève une `ConfigError` à son chemin (`annotations[3].criterion`)

**Given** des annotations dont l'`answer_id` est absent d'`answers.jsonl` de l'Exécution visée
**When** on les rapproche des Réponses
**Then** elles sont signalées par leur `answer_id` et ignorées ; l'`answer_id` est celui d'`Answer` (`contracts.md` §1), y compris `tier` et `phase`

**Given** `stats/kappa.py` et deux vecteurs binaires dont la table de contingence est connue (par exemple 20 oui-oui, 5 oui-non, 10 non-oui, 15 non-non)
**When** on calcule le kappa de Cohen
**Then** il égale la valeur calculée à la main dans le test, à 1e-12 près, soit 0,4
**And** deux vecteurs identiques donnent 1 ; un accord parfait sur une seule classe (kappa indéfini) renvoie `None` sans exception
**And** des vecteurs de longueurs différentes lèvent une `ValueError`

### Story 5.2 : Commande `wl calibrer` et exclusion des Juges

As a Anaël,
I want calibrer le Panel sur mes annotations et que les Juges trop peu fiables soient écartés,
So that les Rapports suivants ne reposent que sur des Juges qui s'accordent avec un humain et qui sont stables.

**Exigences :** FR-38, FR-37 (juge de calibration), FR-34 (`pass_id`), FR-12 (Filtre à relancer), SM-5 ; AD-8 (poste `judging`), AD-14 ; `contracts.md` §4.4 (`judges`), §4.6, §8.

**Acceptance Criteria:**

**Given** une Exécution terminée au profil `test`, un dossier d'annotations de deux annotateurs (dont 10 Réponses doublement annotées) et `judges.calibration_passes: 5`
**When** on lance `wl calibrer <experience.yaml> --annotations <dossier> --run <run_id>`
**Then** chaque Juge du réservoir admissible note chaque Réponse annotée au moins cinq fois, avec `pass_id` de 0 à 4, sans que les passes 1 à 4 soient servies par le Cache de réponses
**And** les spans portent `wl.post=judging`, et les verdicts sont écrits dans un fichier de calibration de l'Exécution, sans modifier `verdicts.jsonl`

**Given** les verdicts des passes
**When** la commande écrit `calibration.json`
**Then** il contient, par Juge et par Critère, le kappa juge-humain (verdict de la passe 0 contre l'annotation, chaque annotateur compté séparément), le taux d'instabilité (part des Réponses dont les verdicts diffèrent entre les passes), le nombre d'items et `excluded: bool`
**And** il contient le kappa entre les deux annotateurs, par Critère, sur les Réponses doublement annotées

**Given** `kappa_threshold: 0.6` et un Juge scénarisé dont le kappa vaut 0,4 sur `correctness`
**When** on calibre
**Then** ce Juge a `excluded: true`, avec la raison, et la commande l'affiche en français
**And** un kappa `None` (indéfini) n'exclut pas le Juge mais est signalé

**Given** `calibration_judge: fake-llm-c` déclaré dans l'Expérience
**When** on calibre
**Then** ce juge ne note que les Réponses doublement annotées, et ses résultats figurent à part dans `calibration.json`

**Given** une nouvelle Expérience avec `judges.excluded_from: <calibration.json>`
**When** on la valide puis on l'exécute
**Then** le Juge exclu ne fait plus partie du Panel (story 1.6), et le Rapport mentionne son exclusion avec la date du fichier de calibration
**And** si ce Juge avait servi au Filtre closed-book du Jeu, la commande `wl calibrer` avertit qu'il faut relancer `wl questions closed-book`

**Given** un dossier sans annotation valide, ou un `run_id` inconnu
**When** on lance la commande
**Then** elle sort avec le code 2 et un message en français

## Epic 6 : Architectures à recherche, du RAG naïf au CAG

Anaël compare aux Baselines cinq Architectures du niveau 1 : RAG naïf, RAG hybride, HyDE, Corrective RAG et CAG. Chacune est sélectionnable par Expérience et validée par la suite de conformité. L'epic atteint le minimum de SM-3.

Règle commune aux stories des epics 6 et 7 (FR-14, SM-C1, AD-2, AD-16) : chaque story livre une Architecture enregistrée sous son nom du registre (`contracts.md` §2.1), avec les défauts de Params du PRD §7.3, ainsi que les Composants qui lui manquent. Elle ajoute une Configuration à `experiments/mini-test.yaml`. La story n'est livrée que si `tests/conformance/test_architectures.py` et `tests/e2e/test_sm3.py` passent avec cette Architecture, sans réseau. Aucune story ne modifie le runner, la passerelle ou le Rapport.

### Story 6.1 : RAG naïf

As a Anaël,
I want une Architecture de recherche dense des k meilleurs Passages suivie d'une génération citée,
So that je dispose de la référence du niveau 1 à laquelle comparer toutes les autres.

**Exigences :** FR-18, FR-14, FR-28 ; AD-2, AD-7, AD-10, AD-20 ; `contracts.md` §2 (`VectorStore`, `Retriever`, `SearchIndex`).

**Acceptance Criteria:**

**Given** le VectorStore `numpy_exact`, enregistré `("vector_store", "numpy_exact")` avec `capabilities.hybrid = false`
**When** on ajoute 10 vecteurs normalisés, on en supprime 2, puis on cherche avec `k: 5`
**Then** les résultats sont classés par produit scalaire décroissant, ex æquo départagés par id, sans les vecteurs supprimés
**And** `save` puis `load` dans un autre dossier redonnent les mêmes résultats, et une dimension différente de `dim` est refusée

**Given** le Retriever `dense`, enregistré `("retriever", "dense")`
**When** `query_vector` vaut `None`
**Then** il appelle `index.embedder.embed_queries([query])` et renvoie des `ScoredPassage` de rangs 1 à k

**Given** l'Architecture `naive_rag` (chunker, embedder, store, retriever, ContextBuilder, Generator, `k: 5`) et le Mini-corpus
**When** on l'indexe avec le faux embedder puis on répond à une Question factuelle
**Then** la Réponse expose exactement 5 Passages retrouvés, classés par score décroissant (`retrieval_method: ranked`), et le prompt de génération contient ces 5 Passages avec leurs Ancrages
**And** une Citation scénarisée hors de ces 5 Passages est retirée et comptée dans `invalid_citations`
**And** le manifeste d'index porte `embedder_dim: 64`

**Given** `k: 3` dans une seconde Configuration
**When** on l'exécute après la première
**Then** l'index est réutilisé (`k` dans `query_params`) et la Réponse expose 3 Passages

**Given** une mise à jour du Mini-corpus
**When** `naive_rag` l'applique (`incremental_update: true`)
**Then** seuls les Passages des Documents ajoutés ou modifiés sont réencodés (compteur d'appels du faux embedder), et les Passages des Documents supprimés ou remplacés sont retirés du store

### Story 6.2 : RAG hybride

As a Anaël,
I want combiner BM25 et recherche dense, puis un reranker optionnel, chaque étage s'activant séparément,
So that le Rapport isole l'effet de chaque étage (H1).

**Exigences :** FR-19, FR-3 (`requires_hybrid_store`) ; AD-2, AD-3 (span `rerank` émis par le Reranker), AD-13 ; `contracts.md` §2 (`Retriever` hybrid, `Reranker`).

**Acceptance Criteria:**

**Given** le Retriever `hybrid` (`fusion: rrf | weighted`, `rrf_k: 60`, `weight_dense: 0.5`) et deux listes classées connues
**When** on fusionne par RRF
**Then** chaque score vaut la somme de 1 ÷ (`rrf_k` + rang) sur les listes où le Passage apparaît, et l'ordre final reproduit le calcul à la main du test
**And** la fusion pondérée normalise chaque liste (min-max) avant de combiner `weight_dense` × dense + (1 − `weight_dense`) × lexical

**Given** l'Architecture `hybrid_rag` (index dense et index `bm25`, `fusion: rrf`, `reranker: null`)
**When** on répond à une Question
**Then** les Passages retrouvés viennent de la fusion, et la Réponse expose k Passages classés
**And** les étages se configurent séparément : dense seul, lexical seul, fusion, et reranker en plus, chaque combinaison étant une Configuration valide
**And** `fusion`, `weight_dense`, `reranker` et `k` sont dans `query_params` : changer d'étage de requête réutilise le même index

**Given** le reranker `fake`, enregistré `("reranker", "fake")` (score de recouvrement de mots, déterministe), et `reranker: {name: fake}`, `rerank_top_n: 20`
**When** on répond
**Then** les 20 meilleurs candidats de la fusion sont reclassés, les k premiers sont gardés, et un span `rerank` distinct apparaît dans la Trace, avec sa latence (FR-19)

**Given** une Architecture de test qui exige un store hybride
**When** on valide une Configuration `numpy_exact`
**Then** elle est refusée (story 1.6) ; `hybrid_rag` lui-même n'exige pas de store hybride, puisqu'il combine deux index

### Story 6.3 : HyDE

As a Anaël,
I want chercher avec l'embedding d'une réponse hypothétique,
So that je mesure si cette réécriture améliore la recherche dense, et à quel coût.

**Exigences :** FR-20 ; AD-4 (rôle `hyde`), AD-8 (poste `query`) ; `contracts.md` §2 (`Retriever.query_vector`), §2.1 (défaut `mix_question = false`).

**Acceptance Criteria:**

**Given** l'Architecture `hyde`, construite sur le même index dense que `naive_rag` (chunker, embedder, store)
**When** on répond à une Question
**Then** un appel au rôle `hyde` (step `hyde`) génère la réponse hypothétique au poste `query`, dans un span distinct de l'étape `generate`
**And** le vecteur passé au Retriever est celui de la réponse hypothétique, encodé par `embed_queries`

**Given** `mix_question: true`
**When** on répond
**Then** le vecteur de recherche est la moyenne, renormalisée, des vecteurs de la réponse hypothétique et de la Question
**And** `mix_question` est dans `query_params`

**Given** la Réponse produite
**When** on inspecte le Contexte et les Citations
**Then** la réponse hypothétique n'apparaît dans aucun bloc du Contexte, et aucune Citation ne peut la désigner

**Given** une réponse hypothétique scénarisée qui reprend les mots d'un Passage précis
**When** on répond
**Then** ce Passage est au rang 1 des Passages retrouvés, ce qui montre que le vecteur de la réponse hypothétique est bien utilisé

### Story 6.4 : Corrective RAG

As a Anaël,
I want qu'une Architecture juge la pertinence de ce qu'elle a retrouvé, reformule et cherche à nouveau, ou s'abstienne,
So that je mesure si cette boucle de correction vaut son coût en appels (H7 au niveau 3).

**Exigences :** FR-21, FR-15 ; AD-4 (rôles `grade_relevance` et `rewrite`), AD-18 (bornes vérifiées avant l'appel) ; `contracts.md` §2 (`Decider`, `QueryRewriter`), §2.1 (`threshold = 0.5`, `max_loops = 2`), §3.

**Acceptance Criteria:**

**Given** le Decider `llm` (rôle `grade_relevance`), enregistré `("decider", "llm")`, et le QueryRewriter `llm` (rôle `rewrite`), enregistré `("query_rewriter", "llm")`
**When** on note trois Passages
**Then** le Decider renvoie trois scores dans [0, 1], un par Passage, dans l'ordre reçu ; un score hors bornes est une sortie non conforme

**Given** l'Architecture `corrective_rag` et des scores par défaut du Faux LLM au-dessus du seuil pour au moins un Passage
**When** on répond
**Then** seuls les Passages notés à 0,5 ou plus entrent dans le Contexte, et la Réponse cite au moins un de ces Passages

**Given** `FakeProvider.script("grade_relevance", "crag.grade.*", '{"scores":[0.1, ...]}')`, qui note tous les Passages sous le seuil
**When** on répond avec `max_loops: 2`
**Then** la Question est reformulée et une nouvelle recherche est émise deux fois, puis l'Architecture s'abstient (`abstained: true`)
**And** les étapes `crag.grade.loop0`, `crag.rewrite.loop1`, `crag.grade.loop1`, `crag.rewrite.loop2` et `crag.grade.loop2` apparaissent dans la Trace, et aucun appel `generate` n'est émis

**Given** des scores sous le seuil à la première boucle et au-dessus à la deuxième (sortie scénarisée par étape)
**When** on répond
**Then** l'Architecture génère après une seule reformulation, avec les Passages de la deuxième recherche

**Given** `threshold` et `max_loops`
**When** on calcule l'`index_key`
**Then** ils sont dans `query_params`, et `corrective_rag` réutilise un index dense de mêmes paramètres

### Story 6.5 : CAG

As a Anaël,
I want précharger tout le Corpus dans le cache de prompt du fournisseur et poser les Questions dessus,
So that je mesure le coût et la qualité d'une approche sans recherche, avec un coût d'indexation explicite.

**Exigences :** FR-22, FR-16 (palier tarifaire), FR-3 (inapplicable), FR-29 (tokens en cache) ; AD-3 (`cache_system`), AD-8 (préchargement au poste `indexing`), AD-13 ; `contracts.md` §2.1 (`requires_prompt_cache`, `full_corpus_in_prompt`).

**Acceptance Criteria:**

**Given** l'Architecture `cag` (`requires_prompt_cache: true`, `full_corpus_in_prompt: true`) et un Generator `fake-llm-a` (`prompt_cache: true`)
**When** le runner l'indexe puis appelle `load`
**Then** `index` écrit le Corpus étiqueté (un bloc par Ancrage) dans le dossier reçu, et `load` émet un appel de préchargement dont le system contient tout le Corpus, avec `cache_system: true`, au poste `indexing`
**And** les deux chemins, index construit ou servi par le cache, préchargent de la même façon, puisque le runner appelle toujours `load`

**Given** deux Questions posées après le préchargement
**When** on lit leurs spans `query`
**Then** la seconde Question montre `wl.usage.cache_read_tokens` non nul, et ses tokens en cache sont tracés séparément des tokens d'entrée
**And** la Réponse a `retrieval_method: cited`

**Given** un Generator dont le Catalogue déclare `prompt_cache: false`
**When** on valide la Configuration
**Then** elle est refusée avant tout appel (story 1.6)

**Given** un Corpus dont l'estimation `tokens_for` dépasse la fenêtre du modèle, ou le seuil de palier de `claude-haiku-5-5` (100 000 tokens)
**When** le runner appelle `check(profile)`
**Then** la Configuration est `inapplicable`, avec une raison qui cite la fenêtre ou le palier, et aucun appel n'est émis

**Given** un Corpus plus court que `min_cacheable_tokens`
**When** on précharge
**Then** l'appel réussit sans erreur, et le Rapport montrera des tokens en cache nuls, conformément au contrat du Catalogue

## Epic 7 : Architectures à structure dérivée, de RAPTOR à GraphRAG

Anaël ajoute au comparatif les Architectures qui construisent une structure à l'indexation : RAPTOR, PageIndex, LLM Wiki, recherche agentique, puis GraphRAG, LazyGraphRAG et LightRAG. L'Expérience `mini-test.yaml` couvre alors tout le registre. La règle commune de l'epic 6 s'applique ; une story qui doit y déroger le dit explicitement.

### Story 7.1 : RAPTOR

As a Anaël,
I want un arbre de résumés construit par regroupement récursif, interrogé sur tous ses niveaux,
So that je mesure si des résumés hiérarchiques aident les questions globales et multi-sauts.

**Exigences :** FR-23, FR-35 ; AD-4 (rôle `summarize`), AD-7, AD-8 (résumés au poste `indexing`), AD-20 ; `contracts.md` §1 (`Passage` de `level` > 0), §2.1 (`group_min = 5`, `group_max = 10`, `max_depth = 3`).

**Acceptance Criteria:**

**Given** l'Architecture `raptor` et le Mini-corpus avec le Faux LLM et le faux embedder
**When** on l'indexe
**Then** `passages.jsonl` contient les feuilles et au moins un niveau de résumés ; chaque nœud de résumé a `level` ≥ 1, `child_ids` non vide, `doc_id: null` s'il couvre plusieurs Documents, `anchor_ids` égal à l'union des Ancrages de ses feuilles, et `passage_id = sha16("node", "raptor", level, *sorted(child_ids))`
**And** les groupes comptent entre `group_min` et `group_max` nœuds, sauf le dernier groupe d'un niveau quand il reste moins de `group_min` nœuds (règle documentée), et la profondeur ne dépasse pas `max_depth`
**And** le regroupement est déterministe : deux indexations donnent les mêmes nœuds (AD-20, départage par id)
**And** les appels `summarize` portent le step `raptor.summarize.level<n>` et le poste `indexing`

**Given** une Question
**When** `raptor` répond
**Then** la recherche dense porte sur tous les nœuds (arbre aplati), et chaque Passage retrouvé expose son `level`
**And** une Citation d'un nœud de résumé devient des Citations vers les Ancrages de ses feuilles, par la table `labels` (AD-7), et toutes ces Citations désignent des Ancrages existants

**Given** les métriques de recherche
**When** un nœud de résumé est retrouvé
**Then** il est pertinent si l'union de ses `anchor_ids` recoupe les Ancrages de référence, sans traitement particulier dans `scoring/`

**Given** une mise à jour
**When** `raptor` l'applique (`incremental_update: false`)
**Then** l'arbre est reconstruit sur `corpus_after` au poste `update`, et aucun nœud ne référence un Ancrage du Document supprimé

### Story 7.2 : PageIndex

As a Anaël,
I want qu'un LLM navigue dans la table des matières de chaque Document pour choisir les sections à lire, sans recherche vectorielle,
So that je mesure cette approche par raisonnement sur des documents longs et structurés.

**Exigences :** FR-24, FR-35 (`provided`) ; AD-3, AD-4 (rôles `summarize` et `select_nodes`), AD-10 (arbre persistant), AD-18 ; `contracts.md` §2.1 (`max_nodes_read = 8`), §3.

**Acceptance Criteria:**

**Given** l'Architecture `pageindex` et le Mini-corpus
**When** on l'indexe
**Then** chaque Document a un arbre qui suit sa hiérarchie de titres, ou ses pages pour un PDF sans titre ; chaque nœud porte un titre, un résumé court (rôle `summarize`, poste `indexing`) et son Ancrage
**And** les arbres sont écrits dans le dossier d'index, et une instance neuve qui fait `load` les retrouve sans aucun appel

**Given** une Question
**When** `pageindex` répond
**Then** il présente au rôle `select_nodes` les titres et résumés du niveau courant (`inputs`: `question`, `nodes`, `max`), descend dans les nœuds choisis et lit les sections retenues, sans aucun appel d'embedding
**And** chaque appel de sélection est un span distinct (`pageindex.select.<n>`), et les sections lues sont exposées dans `retrieved`, dans l'ordre de lecture, avec leurs Ancrages (`retrieval_method: provided`)
**And** le nombre de sections lues ne dépasse jamais `max_nodes_read` : la borne est vérifiée avant chaque lecture et chaque appel

**Given** le Faux LLM par défaut
**When** on pose une Question factuelle du Mini-corpus
**Then** la Réponse porte au moins une Citation valide (`contracts.md` §3)

**Given** une sortie de sélection scénarisée qui désigne un identifiant de nœud inconnu
**When** `pageindex` répond
**Then** le nœud inconnu est ignoré et compté dans un avertissement du journal ; si aucun nœud valide n'est choisi, l'Architecture s'abstient

### Story 7.3 : LLM Wiki

As a Anaël,
I want compiler le Corpus en pages de wiki par un LLM et répondre à partir de ce wiki,
So that je mesure la qualité, la fidélité et le coût de maintenance d'un savoir compilé.

**Exigences :** FR-25, FR-31 (poste `update` récurrent), FR-40 ; AD-4 (rôles `wiki_compile` et `wiki_fidelity`), AD-7, AD-8 ; `contracts.md` §2.1 (`fidelity_sample = 5`), §3, §5 (`wiki_fidelity.json`).

**Acceptance Criteria:**

**Given** l'Architecture `llm_wiki` et le Mini-corpus
**When** on l'indexe
**Then** les appels `wiki_compile` (poste `indexing`) produisent des pages ; chaque page devient un Passage de `level` 1 dont les `anchor_ids` sont les Ancrages déclarés par la page, filtrés sur ceux qui existent dans le Corpus
**And** une page dont aucun Ancrage déclaré n'existe est écartée et comptée dans le journal

**Given** une Question
**When** `llm_wiki` répond
**Then** les pages sont retrouvées par un index lexical sur le wiki, fournies au Generator, et les Citations remontent aux Ancrages des pages (`retrieval_method: provided`)

**Given** `fidelity_sample: 5` et la graine de l'Expérience
**When** l'indexation se termine
**Then** cinq pages tirées de façon déterministe sont vérifiées par le rôle `wiki_fidelity` contre le texte de leurs Ancrages, et `wiki_fidelity.json` (pages, `claims`, `supported`) est écrit dans le dossier d'index

**Given** une mise à jour (`incremental_update: true`)
**When** `llm_wiki` l'applique
**Then** seules les pages issues des Documents ajoutés, modifiés ou supprimés sont recompilées ou retirées, ces passes sont au poste `update`, et la fidélité est remesurée
**And** aucune page ne référence le Document supprimé

**Given** une Exécution qui contient une Configuration `llm_wiki`
**When** le runner a chargé l'index
**Then** il copie `wiki_fidelity.json` dans `runs/<run_id>/`, et le Rapport affiche par Configuration le taux `supported ÷ claims`
**And** cette story est la seule de l'epic qui touche au runner et au Rapport : la copie et l'affichage sont génériques (fichier présent ou absent), sans autre changement

### Story 7.4 : Recherche agentique

As a Anaël,
I want un agent qui cherche, lit et liste le Corpus jusqu'à répondre, sous des bornes strictes,
So that je mesure ce que l'agentique apporte et ce qu'elle coûte par Question.

**Exigences :** FR-26, FR-35 (`provided`), FR-4 ; AD-4 (rôle `agent_step`), AD-18 ; `contracts.md` §2.1 (`max_steps = 8`, `max_cost_per_question = 0.05 USD`), §3.

**Acceptance Criteria:**

**Given** l'Architecture `agentic` et ses outils `search` (BM25 sur les Passages), `read` (par `anchor_id`) et `list` (Documents du Corpus)
**When** on inspecte les outils
**Then** ce sont des fonctions Python en lecture seule, limitées au Corpus indexé ; un `read` d'un Ancrage inconnu renvoie un message d'erreur à l'agent au lieu de lever une exception

**Given** le Faux LLM par défaut et une Question factuelle du Mini-corpus
**When** `agentic` répond
**Then** l'agent enchaîne `search(question)`, `read` du premier résultat puis `answer`, et la Réponse porte au moins une Citation valide
**And** chaque appel est un span `agent.step<n>`, et les Passages retrouvés sont les extraits lus, dans l'ordre de lecture (`retrieval_method: provided`)

**Given** une sortie scénarisée qui ne choisit jamais `answer`
**When** `agentic` répond avec `max_steps: 8`
**Then** au plus 8 appels `agent_step` sont émis, puis l'agent s'abstient

**Given** `max_cost_per_question: {amount: "0.000010", currency: USD}` et un prix fictif qui le fait dépasser après deux étapes
**When** `agentic` répond
**Then** la borne est vérifiée avant chaque appel sur la somme des `cost_uncached` déjà engagés pour la Question, et l'agent s'abstient sans émettre l'appel suivant
**And** l'usage de `cost_uncached` rend le comportement identique avec et sans Cache de réponses (FR-4)

**Given** une action inconnue ou des `args` invalides
**When** l'agent les renvoie
**Then** la sortie est traitée comme non conforme (AD-4), réessayée une fois, puis la Question passe en `status: error`

### Story 7.5 : Graphe de connaissances : GraphStore, extraction, communautés et rapports

As a agent de développement,
I want les Composants de graphe que partagent GraphRAG et LightRAG,
So that chaque variante assemble les mêmes briques au lieu de réimplémenter l'extraction et le graphe.

**Exigences :** FR-27 (fondations) ; AD-2, AD-4 (rôles `extract_entities` et `community_report`), AD-7, AD-8, AD-20 ; `contracts.md` §2 (`GraphStore`), §3.

**Acceptance Criteria:**

**Given** le GraphStore `networkx`, enregistré `("graph_store", "networkx")`
**When** on ajoute des entités et des relations rattachées à des Passages, puis on appelle `remove_passages`
**Then** les entités et les relations qui n'ont plus de Passage sont retirées, et `save` puis `load` redonnent le même graphe
**And** deux mentions d'une entité dont les noms ne diffèrent que par la casse ou les accents sont fusionnées, par `slug`

**Given** l'extracteur d'entités LLM (rôle `extract_entities`), enregistré comme Composant réutilisable, et le Faux LLM
**When** on extrait trois Passages du Mini-corpus
**Then** chaque entité et chaque relation est rattachée aux `passage_id` d'où elle vient, et une sortie non conforme est réessayée une fois puis lève `NonConformantOutput` (AD-4)

**Given** un graphe construit sur le Mini-corpus
**When** on détecte les communautés puis on rédige leurs rapports
**Then** les communautés sont déterministes (Louvain de networkx avec une graine dérivée de l'Expérience, ex æquo départagés par id), et deux exécutions donnent les mêmes communautés
**And** chaque rapport (rôle `community_report`) devient un Passage de `level` 1 dont les `anchor_ids` sont l'union des Ancrages de ses Passages sources (AD-7)
**And** cette story n'enregistre aucune Architecture : la suite de conformité ne la concerne pas

### Story 7.6 : GraphRAG, recherche locale et globale

As a Anaël,
I want un GraphRAG maison, conforme à l'article, avec recherche locale et recherche globale,
So that je mesure H2 (questions globales) et H13 (coût d'indexation et de mise à jour) sur une implémentation que je maîtrise.

**Exigences :** FR-27, FR-31, FR-53 ; AD-2, AD-4 (rôles `global_map` et `generate`), AD-7, AD-8 ; `contracts.md` §2.1, §3.

**Acceptance Criteria:**

**Given** l'Architecture `graphrag`, assemblée à partir des Composants de la story 7.5, et le Mini-corpus
**When** on l'indexe
**Then** l'extraction, les communautés et leurs rapports sont produits, et tous les appels de l'indexation portent le poste `indexing`

**Given** `search: local` et la Question de conformité
**When** `graphrag` répond
**Then** les entités proches de la Question sont trouvées par l'embedding de leurs descriptions (store `numpy_exact`), puis le contexte réunit leurs relations, leurs Passages sources et leurs rapports de communauté, et la Réponse cite des Ancrages existants

**Given** `search: global` et une Question de type `global`
**When** `graphrag` répond
**Then** une étape map (rôle `global_map`, un appel par lot de rapports) précède une étape reduce (rôle `generate`), chacune tracée dans un span distinct, et les Citations remontent aux Ancrages des rapports
**And** `search` est dans `query_params` : les recherches locale et globale partagent le même index

**Given** une mise à jour (`incremental_update: true`)
**When** `graphrag` l'applique
**Then** seuls les Passages ajoutés ou modifiés sont extraits à nouveau, `remove_passages` retire ceux des Documents supprimés, et seuls les rapports des communautés dont la composition change sont régénérés, au poste `update`
**And** le Rapport ventile les résultats par Type de question et sépare les coûts d'indexation et de mise à jour, sans changement du Rapport (stories 4.11 et 4.12)

### Story 7.7 : LazyGraphRAG

As a Anaël,
I want une variante de GraphRAG qui n'appelle aucun LLM à l'indexation et reporte le travail à la requête,
So that je compare son coût d'indexation quasi nul et sa qualité à ceux de GraphRAG.

**Exigences :** FR-27 ; AD-2, AD-4 (rôles `grade_relevance` et `generate`), AD-20 ; `contracts.md` §2.1.

**Acceptance Criteria:**

**Given** l'Architecture `lazy_graphrag` et le Mini-corpus
**When** on l'indexe
**Then** aucun appel LLM n'est émis : les concepts sont extraits par l'heuristique hors ligne de `corpus/entities.py`, le graphe de cooccurrence est construit dans le GraphStore `networkx`, et les communautés sont détectées de façon déterministe
**And** la Trace d'indexation ne contient aucun span `llm`

**Given** une Question
**When** `lazy_graphrag` répond
**Then** il classe les communautés selon les concepts de la Question, note la pertinence des Passages des meilleures communautés (rôle `grade_relevance`) dans la limite de `relevance_budget` Passages (défaut 20, documenté dans le Params), puis génère avec les Passages pertinents
**And** la borne `relevance_budget` est vérifiée avant chaque appel, et elle est dans `query_params`

**Given** des scores de pertinence scénarisés tous nuls
**When** `lazy_graphrag` répond
**Then** il s'abstient sans appeler `generate`

**Given** l'Architecture enregistrée
**When** on consulte `wl registre --kind architecture`
**Then** `lazy_graphrag` y figure comme Architecture distincte de `graphrag`

### Story 7.8 : LightRAG

As a Anaël,
I want une variante de GraphRAG à recherche sur deux niveaux, entités et relations, avec une mise à jour incrémentale par union de graphes,
So that je mesure le compromis qualité, coût de mise à jour qu'elle revendique.

**Exigences :** FR-27, FR-53 ; AD-2, AD-4 (rôle `extract_entities`), AD-7 ; `contracts.md` §2.1.

**Acceptance Criteria:**

**Given** l'Architecture `lightrag`, l'extracteur et le GraphStore de la story 7.5, et le Mini-corpus
**When** on l'indexe
**Then** les entités et les relations sont extraites par Passage, et leurs descriptions sont encodées dans deux index denses séparés, l'un pour les entités et l'autre pour les relations
**And** aucun rapport de communauté n'est produit

**Given** une Question
**When** `lightrag` répond
**Then** la recherche bas niveau trouve les entités proches de la Question et la recherche haut niveau trouve les relations proches, et le contexte réunit les Passages sources des deux résultats, dédoublonnés
**And** la Réponse cite des Ancrages existants ; le mot-clé de la Question est son embedding direct, simplification documentée dans la docstring (FR-27)

**Given** une mise à jour (`incremental_update: true`)
**When** `lightrag` l'applique
**Then** seuls les Passages ajoutés ou modifiés sont extraits, leur sous-graphe est uni au graphe existant, les Passages supprimés sont retirés, et aucun appel ne porte sur un Passage inchangé (compteur d'appels du Faux LLM)

**Given** la fin de l'epic
**When** on lance `tests/e2e/test_sm3.py`
**Then** `mini-test.yaml` couvre les 15 Architectures du registre et le Rapport compare les Baselines et les 12 Architectures du niveau 1
