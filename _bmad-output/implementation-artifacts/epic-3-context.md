# Epic 3 Context: Construire et geler un Jeu d'évaluation

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Permettre à Anaël de produire un Jeu d'évaluation fiable : générer des Questions candidates ancrées, les valider ou corriger à la main dans un YAML, contrôler que chaque Ancrage existe dans le Corpus, écarter les Questions que des modèles connaissent déjà (Filtre closed-book), puis geler le jeu avec une séparation dev / test stratifiée. L'epic livre aussi le Jeu de référence du Mini-corpus (40 Questions ou plus), gelé, sur lequel toutes les Architectures se testent ensuite. Le Composant Juge LLM naît ici ; l'epic 4 le réutilise pour le Panel.

## Stories

- Story 3.1: Format des Questions et commande `wl questions controler`
- Story 3.2: Contexte d'exécution concret
- Story 3.3: Génération de Questions candidates
- Story 3.4: Juge LLM et correspondance exacte normalisée
- Story 3.5: Filtre closed-book et commande `wl questions closed-book`
- Story 3.6: Gel et séparation développement / test
- Story 3.7: Jeu d'évaluation de référence du Mini-corpus

## Requirements & Constraints

- Un fichier de Questions par Corpus, éditable à la main ; un fichier invalide est refusé avec l'indice de l'enregistrement et le champ (`questions[12].type`) ; un `id` n'est jamais réutilisé. Statuts : generated, validated, corrected, rejected ; seules validated et corrected servent aux Exécutions.
- Chaque Question porte au moins un Ancrage vérifié, sauf `unanswerable` (aucun Ancrage). Toute Question validée dont un Ancrage est introuvable fait échouer le contrôle (code 2) ; pour generated ou rejected, simple signalement. Une réponse `short` fait au plus 5 mots (ou nombre, date).
- Génération : répartition par Type, statut `generated`, jamais utilisée avant validation ; passe par le Plafond et le Cache de réponses ; plafond atteint = code 3 sans écriture partielle ni toucher aux Questions existantes.
- Closed-book : chaque Question est posée sans contexte à 2 ou 3 modèles ; réponse courte = correspondance exacte normalisée (casse, accents, ponctuation, format des nombres), sinon verdict d'un Juge d'une autre Famille ; les `unanswerable` sont exclues ; le modèle fautif va dans `contaminated_by`.
- Gel : empreinte enregistrée, répartition stratifiée par Type et déterministe par la graine (40 % dev par défaut), refus de geler s'il reste des Questions `generated`, test utilisable seulement sur demande explicite. Modifier `contaminated_by` ne casse pas l'empreinte.
- Jeu de référence : au moins 40 Questions validated, tous Types sauf `visual` et `numeric_aggregation`, dont 2 de suivi, 2 interlingues, 3 liées au Scénario, une `unanswerable` sur un fait absent, une `knowledge_trap`, 5 réponses courtes, une citant une page de PDF. Une Question de conformité (`CONFORMANCE_QUESTION_ID`, `factual`, un seul Ancrage) partage au moins 80 % de ses mots avec son Ancrage, pour que le Faux LLM, BM25 et le faux embedder la retrouvent.
- Suivis du run à traiter ici : `wl questions` doit contrôler `closed_book_models` et `question_gen_model` (modèles au Catalogue, hors réseau) ; `wl calibrer` écrit `calibration.json` au format retenu en 1.6 (par Juge et par Critère, kappa, instabilité, `excluded` booléen strict, `criteria`, plus kappa inter-annotateurs).
- Contraintes du run autonome :
  - Aucun réseau ni API dans les tests : Faux LLM seulement (`fake-llm-a/b/c`, profil `test`).
  - Pas d'Ollama avant le go d'Anaël (seuls `/api/version`, `/api/ps`, `/api/tags` tolérés), pas de GPU.
  - Pas d'extra lourd (`local`, `docling`), pas de téléchargement de plus de 1 Go ; `OMP_NUM_THREADS=4`, RAM ≤ 6 Go, pas de pytest parallèle.

## Technical Decisions

- Modules : `evalset/io.py` (chargement/écriture, ordre des Questions et des clés préservé), `check.py`, `generate.py`, `closed_book.py`, `freeze.py` ; `scoring/answer.py` (`exact_match`, `is_short_form`) ; `components/judges/llm.py` enregistré `("judge", "llm")` ; `runner/context.py` (`RunContext` concret). Respecter les couches : `evalset` ne dépend que de `scoring`, `corpus`, `llm`.
- Ancrages (AD-5) : écrits `{doc, page}` ou `{doc, headings}`, résolus par `ParsedCorpus.resolve` / `anchor_text` (epic 2). Avec `--scenario`, les Questions `scenario_target` se résolvent dans `corpus_after` (story 2.6), sinon elles sont « non vérifiables » sans échec.
- Passerelle et rôles (epic 1) : rôles `question_gen` (inputs `anchors`, `types` ; le Faux LLM produit une `factual` par Ancrage), `closed_book` (le Faux LLM renvoie la question inchangée, donc jamais contaminée) et `judge` (un seul appel pour tous les Critères, `complete_structured` réessaie une fois puis `NonConformantOutput`). Un Juge refait une passe hors cache via `pass_id` ; `faithfulness` utilise les `context_texts` réellement fournis au Generator.
- Postes de coût (AD-8) : génération = `evalset`, Filtre closed-book = `judging`, fixés par `ctx.scope(post=..., question_id=...)` ; les valeurs sont restaurées à la sortie et lues seules par les Composants.
- Juge du closed-book (AD-14) : `closed_book_judge` = premier modèle du réservoir `judges.pool` d'une autre Famille que le modèle interrogé ; liste des modèles par défaut = `closed_book_models` du profil ; modèle de génération = `question_gen_model`.
- Gel (AD-15) : `freeze = {sha256, at, seed, dev_ratio}`, empreinte = `canonical_json` du document sans `freeze` ni `contaminated_by`. `verify_frozen` (appelée par le runner) refuse un jeu non gelé ou modifié ; `select_questions(split=...)` ne rend que validated et corrected.
- Aléa (AD-20) : `ctx.rng(*clés)` ; même graine = même échantillon d'Ancrages et même répartition. `run.lock` pris seulement par un contexte d'Exécution, pas par les commandes hors Exécution.
- Commandes (`contracts.md` §8) : `wl questions generer|controler|closed-book|geler` ; option `--scenario` ajoutée à `controler`. Codes de sortie : 2 configuration ou Ancrage invalide, 3 plafond. Messages en français.

## Cross-Story Dependencies

- 3.1 (format, `io`) précède 3.3, 3.5, 3.6 et 3.7. 3.2 (`RunContext`) précède 3.3 et 3.5. 3.4 (Juge, `exact_match`) précède 3.5.
- 3.6 (`verify_frozen`, `select_questions`) est requise par 3.7 et par le runner de l'epic 4.
- 3.7 s'appuie sur le Mini-corpus et le scénario de l'epic 2 (stories 2.5, 2.6) ; la Question de conformité sert à la suite de conformité (story 4.14).
- Le Juge LLM (3.4) est réutilisé par le Panel (epic 4) et la calibration (epic 5).
