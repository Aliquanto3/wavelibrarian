# Epic 2 Context: Déclarer, ingérer et profiler un Corpus

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Permettre de déclarer un Corpus dans un `corpus.yaml`, de l'ingérer avec des Ancrages stables (chemin de titres pour Markdown, texte et HTML ; page pour PDF) et d'obtenir son Profil (`wl corpus profiler`). L'epic fournit aussi les Paliers de volume emboîtés, l'application d'un Scénario de mise à jour et le Mini-corpus fictif publiable (Documents, extras, scénario) sur lequel toute la chaîne se teste sans réseau.

## Stories

- Story 2.1: Déclaration d'un Corpus
- Story 2.2: Ingestion Markdown, texte et HTML avec Ancrages
- Story 2.3: Ingestion PDF avec Ancrages par page
- Story 2.4: Profil de corpus et commande `wl corpus profiler`
- Story 2.5: Mini-corpus fictif
- Story 2.6: Application d'un Scénario de mise à jour à un Corpus
- Story 2.7: Paliers de volume et commande `wl corpus paliers`

## Requirements & Constraints

- Un Corpus déclare identifiant (`[a-z0-9-]+`), chemin, langue par défaut, licence, `publishable`, volatilité déclarée et métadonnées optionnelles par Document (langue, sensibilité, profils de droits, sans effet au MVP). Clé inconnue ou mal typée : `ConfigError` au chemin pointé.
- `doc_id` dérivé du contenu (insensible au renommage) ; Documents triés par `source_path` POSIX relatif à la racine du Corpus. Format non pris en charge (ex. `.docx`) : signalé au journal et ignoré, sans arrêter. PDF illisible : signalé et ignoré, les autres Documents continuent.
- Un Ancrage de référence doit se retrouver dans le texte parsé (`resolve`, `anchor_text`), car la validation des Questions (epic 3) en dépend.
- Le parsing est mis en cache par Document et par Parser ; une seconde ingestion n'appelle pas le Parser.
- Profil : nombre de Documents, tokens (tokenizer de référence unique), longueur moyenne, profondeur de titres (max, moyenne), densité de liens (entités nommées partagées, heuristique sans réseau ni LLM), part tabulaire, images par Document, langue dominante, volatilité déclarée. Comparaison à la fenêtre d'un modèle : tokens de référence × `token_factor` du Catalogue (défaut 1,2).
- Mini-corpus : 18 à 22 Documents (Markdown et PDF), univers contrefactuel, moins de 60 000 tokens, au moins 2 Documents en anglais, deux versions contradictoires, un long Document à trois niveaux de titres avec tableaux, un groupe de Documents liés. Hors `docs/` : scénario, sentinelle, document piégé (injection indirecte). Au moins 2 Documents avec `rights_profiles`.
- Paliers emboîtés (5 ⊂ 10 ⊂ 20), déterministes par graine, contenant toujours les `required_paths`.
- Contraintes du run autonome :
  - Aucun réseau dans les tests (profil `test`, tokenizer `approx`, rien à télécharger).
  - Aucun extra lourd : ni `docling`, ni extra `local` (torch) ; seuls pypdfium2 et fpdf2 (dev) servent aux PDF.
  - Un corpus sous licence restrictive n'entre jamais dans le dépôt public ; seul le Mini-corpus fictif (`publishable: true`, CC-BY-4.0) y est commité.
  - Pas d'Ollama ni de GPU ; `OMP_NUM_THREADS=4`, RAM ≤ 6 Go, pas de pytest parallèle.

## Technical Decisions

- Identités (AD-5) : `source_path`, `doc_id = sha256(octets)[:16]` via `core/ids.py` ; `anchor_id` = `<doc_id>#p<page>` (pages dès 1) ou `<doc_id>#h/<slug>/<slug>` ; texte avant le premier titre ou fichier sans titre : `<doc_id>#h/`. Titres frères identiques : suffixe ordinal documenté, déterministe. `heading_path` conserve les titres bruts.
- Modules : `corpus/declare.py`, `ingest.py`, `profile.py`, `entities.py`, `scenario.py`, `tiers.py`. Parsers `markdown` (markdown-it-py), `text`, `html` (beautifulsoup4), `pdf_text` (pypdfium2), enregistrés au `kind` `parser` avec leurs `formats` ; `ingest.py` les obtient par le registre, sans importer `components` (AD-1).
- Suite du suivi `parser: auto` : 2.1 et 2.2 doivent exposer les formats du Corpus et les parsers enregistrés par format, pour que le runner remplace `auto` par des noms concrets (`markdown`, `text`, `html`, `pdf_text`) avant d'écrire `RunContext.parser` et `index_key`. 2.2 résout `auto` dans `ingest.py` ; le runner (epic 4) doit disposer du même résultat.
- Cache de parsing : `<WL_HOME>/parse_cache/<parser>/<doc_id>.json`. `ParsedCorpus` trié par `source_path`, `fingerprint = sha16` des couples `(source_path, doc_id)` triés.
- Déjà posé par l'epic 1 et à réutiliser sans le redéfinir : registre `@register` avec `Params` forbid + frozen, types `Document`, `Anchor`, `Passage`, `CorpusProfile`, `ParsedCorpus` (`resolve`, `anchor_text`), `CorpusChange`, `ConfigError` avec chemin, `tokens_for` sans facteur (le facteur ne vient que de l'estimation de la Passerelle), fixtures `wl_home` et `fake_ctx`.
- Droits (AD-19) : un Corpus `publishable: false` dont le chemin est dans le dépôt est refusé s'il n'est pas ignoré (`git check-ignore`) ; hors dépôt git, vérification sautée avec avertissement.
- Scénario (`scenario.yaml`) : opérations `add`, `modify`, `delete` appliquées dans l'ordre ; `source` relatif au fichier du scénario, `target` = `source_path` du Corpus ; erreurs au chemin `operations[i]`. L'application est pure : `CorpusChange` + `corpus_after`, original inchangé, rien d'écrit dans `docs/`.
- Paliers (AD-20) : tirage par `ctx.rng` ou `default_rng(sha16(...))`, listes triées ; sous-corpus = `ParsedCorpus` restreint avec sa propre `fingerprint`. Erreurs `ConfigError` si `required_paths` dépasse la plus petite taille, ou taille > nombre de Documents (`tiers.sizes[i]`).
- PDF du Mini-corpus générés par `scripts/make_minicorpus_pdfs.py` (fpdf2) avec une police TTF libre commitée (ex. DejaVu Sans) pour « œ », « », tirets typographiques ; les PDF sont commités. Fixture `minicorpus` : `ParsedCorpus` du profil `test`, cache de session.
- CLI : `wl corpus profiler <corpus.yaml> --parser auto` écrit `corpus_profile.json` (`model_dump(mode="json")`) ; `wl corpus paliers`. Messages en français, `corpus.yaml` invalide = code de sortie 2.

## Cross-Story Dependencies

- 2.1 (déclaration) précède 2.2 et 2.3 (ingestion) ; 2.2 pose `ingest.py`, le cache de parsing et `resolve`, que 2.3 complète avec `pdf_text`.
- 2.4 dépend de 2.2/2.3 ; 2.5 dépend de 2.1 à 2.3 (déclare et ingère le Mini-corpus) et fournit la fixture `minicorpus` ; 2.6 et 2.7 s'appuient sur 2.5.
- Vers les autres epics : l'epic 3 construit le Jeu d'évaluation sur le Mini-corpus et valide ses Ancrages par `resolve`/`anchor_text` ; l'epic 4 (runner) consomme `corpus_profile.json`, Paliers, Scénario (phase `after_update`, Fraîcheur) et remplace `parser: auto`.
