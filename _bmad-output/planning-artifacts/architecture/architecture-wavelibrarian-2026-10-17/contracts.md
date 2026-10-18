---
name: 'WaveLibrarian — contrats'
type: architecture-companion
companion_of: ARCHITECTURE-SPINE.md
status: final
created: '2026-10-17'
updated: '2026-10-17'
---

# Contrats WaveLibrarian (MVP)

Ce fichier accompagne `ARCHITECTURE-SPINE.md`. Il fixe les formes partagées : types du domaine, ports Python, rôles LLM, schémas YAML et formats de fichiers. Les signatures et les noms de champs **lient** les agents. Le code interne de chaque module reste libre. Un champ qui manque ici s'ajoute sous la forme d'un champ **optionnel avec valeur par défaut**, jamais en renommant un champ existant (AD-12).

Les identifiants du code et les clés YAML sont en anglais. Les messages pour l'utilisateur, les rapports et la documentation sont en français.

## 1. Types du domaine — `core/types.py`

Ce sont des modèles pydantic v2 avec `model_config = ConfigDict(frozen=True, extra="forbid")`. Les montants sont des `Decimal`, sérialisés en chaînes (AD-9).

```python
QuestionType = Literal["factual", "multi_hop", "global", "comparison", "numeric_aggregation",
                       "temporal", "unanswerable", "knowledge_trap", "visual"]
Criterion = Literal["correctness", "completeness", "faithfulness",
                    "citation_correctness", "abstention_correctness"]
JUDGED_CRITERIA: tuple[Criterion, ...] = ("correctness", "completeness", "faithfulness")
CostPost = Literal["indexing", "update", "query", "judging", "evalset"]
# judging (Juges, Filtre closed-book en Exécution) et evalset (génération de questions) sont
# affichés à part et exclus du coût d'une Configuration dans le Rapport.
Condition = Literal["standard", "perfect_context"]
Phase = Literal["base", "after_update"]       # avant / après application du Scénario de mise à jour

class ModelRefMeta:                    # marqueur Annotated : un champ de Params qui désigne un modèle du Catalogue
    def __init__(self, role_default: str, answer_producer: bool = False) -> None: ...
    # role_default : clé de profil.defaults utilisée si la valeur est None (ex. "generator_models[0]")
    # answer_producer : True pour le modèle qui écrit le texte de la Réponse (règle de famille, AD-14)
ModelRef = Annotated[str | None, ModelRefMeta]   # usage : model: Annotated[str | None, ModelRefMeta("generator_models[0]", True)] = None

class DocMeta(BaseModel):
    sensitivity: str | None = None
    rights_profiles: tuple[str, ...] = ()

class Anchor(BaseModel):
    anchor_id: str                    # AD-5 : "<doc_id>#p<page>" ou "<doc_id>#h/<slug>/<slug>"
    doc_id: str
    source_path: str                  # chemin POSIX relatif à la racine du corpus
    page: int | None = None           # numérotée à partir de 1
    heading_path: tuple[str, ...] = ()  # titres bruts, du plus haut au plus bas

class Block(BaseModel):
    text: str
    anchor_id: str
    kind: Literal["text", "table", "heading", "image"]

class ParsedDocument(BaseModel):
    doc_id: str                       # sha256(octets bruts)[:16]
    source_path: str
    format: Literal["markdown", "text", "html", "pdf"]
    lang: str                         # ISO 639-1
    blocks: tuple[Block, ...]
    anchors: dict[str, Anchor]        # anchor_id -> Anchor, dans l'ordre du document
    meta: DocMeta = DocMeta()

class ParsedCorpus(BaseModel):
    corpus_id: str
    fingerprint: str                  # sha256 des (source_path, doc_id) triés, [:16]
    documents: tuple[ParsedDocument, ...]   # triés par source_path
    def anchor_text(self, anchor_id: str) -> str: ...      # concatène les Blocks de l'ancrage
    def resolve(self, source_path: str, page: int | None,
                headings: tuple[str, ...]) -> str | None: ...  # -> anchor_id, ou None

class Passage(BaseModel):
    passage_id: str                   # level 0 : sha16(doc_id, chunker_key, ordinal)
                                      # level > 0 : sha16("node", architecture, level, *sorted(child_ids))
    doc_id: str | None                # obligatoire si level == 0 ; None pour un nœud multi-documents
    text: str
    anchor_ids: tuple[str, ...]       # non vide ; level 0 : ancrages d'un seul Document ;
                                      # level > 0 : union des anchor_ids des feuilles (AD-7)
    level: int = 0                    # 0 = feuille ; >0 = nœud de résumé (RAPTOR, page de wiki, rapport de communauté)
    child_ids: tuple[str, ...] = ()   # nœuds de résumé : passage_ids des enfants

class ScoredPassage(BaseModel):
    passage: Passage
    score: float
    rank: int                         # 1 = meilleur

class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str

class QuestionInput(BaseModel):       # seule vue de la Question que voit une Architecture (AD-6)
    question_id: str
    text: str
    lang: str
    history: tuple[ConversationTurn, ...] = ()

class Citation(BaseModel):
    anchor_id: str

class ArchAnswer(BaseModel):          # ce que renvoie une Architecture ; le runner le complète en Answer
    text: str
    abstained: bool
    citations: tuple[Citation, ...] = ()
    retrieved: tuple[ScoredPassage, ...] = ()
    # "ranked" : liste classée du Retriever. "provided" : Passages fournis au Generator, dans l'ordre du contexte.
    # "cited" : un ScoredPassage par ancrage cité, rang = ordre de première citation, score 1.0. "none" : vide.
    retrieval_method: Literal["ranked", "provided", "cited", "none"] = "ranked"
    context_anchor_ids: tuple[str, ...] = ()   # ancrages réellement fournis au Generator
    context_texts: tuple[str, ...] = ()        # Context.blocks fournis au Generator (pour la fidélité)
    context_truncated: bool = False            # True si > 8 000 tokens : seuls les blocs cités sont gardés
    invalid_citations: int = 0

class Answer(ArchAnswer):             # écrit par le runner uniquement
    answer_id: str                    # "<run_id>/<config_id>/<condition>/<tier>/<phase>/<question_id>", tier = "all" si aucun
    question_id: str
    config_id: str
    condition: Condition = "standard"
    tier: int | None = None
    phase: Phase = "base"
    status: Literal["ok", "error", "inapplicable", "budget_exceeded"]
    error: str | None = None
    latency_s: float = 0.0            # somme des latences des spans du poste query pour cette Question

class AnchorRef(BaseModel):           # forme YAML d'un Ancrage de référence
    doc: str                          # source_path
    page: int | None = None
    headings: tuple[str, ...] = ()

class Question(BaseModel):            # enregistrement de questions.yaml (contracts §4.5), lu par evalset/ et scoring/ uniquement
    id: str
    type: QuestionType
    follow_up: bool = False
    cross_lingual: bool = False
    text: str
    lang: str
    reference_answer: str = ""
    answer_form: Literal["short", "free"]
    reference_anchors: tuple[AnchorRef, ...] = ()
    status: Literal["generated", "validated", "corrected", "rejected"]
    split: Literal["dev", "test"] | None = None
    contaminated_by: tuple[str, ...] = ()
    history: tuple[ConversationTurn, ...] = ()
    origin: dict[str, str]            # {"kind": "human"|"model", "name": ...}
    scenario_target: dict[str, str] | None = None   # {"operation": "op-2", "state": "after"}

class CorpusProfile(BaseModel):       # FR-7, écrit en corpus_profile.json
    corpus_id: str
    fingerprint: str
    parser: str
    tokenizer: str                    # nom du tokenizer de référence
    n_documents: int
    n_tokens: int                     # tokenizer de référence
    mean_tokens_per_document: float
    heading_depth_max: int
    heading_depth_mean: float
    link_density: float               # part des Documents partageant >= 1 entité nommée avec un autre
    table_share: float                # part des tokens dans des Blocks "table"
    images_per_document: float
    dominant_lang: str
    langs: dict[str, int]             # langue -> nombre de Documents
    formats: dict[str, int]
    volatility: Literal["low", "medium", "high"]
    def tokens_for(self, model_id: str, catalog: "ModelCatalog") -> int: ...
        # tokenizer du Catalogue si « reference », sinon n_tokens × token_factor du modèle (défaut 1,2, FR-7)
        # (comptage du corpus ; l'estimation avant appel de la passerelle applique toujours token_factor une fois, majorant)

class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

class Verdict(BaseModel):
    answer_id: str
    judge_model: str                  # identifiant du Catalogue ; "auto" si calculé sans Juge
    criterion: Criterion
    pass_id: int = 0
    verdict: bool
    justification: str = ""
```

`core/errors.py` définit `WlError` comme racine. En dérivent `ConfigError(path: str, message)` (le chemin est en notation pointée, par exemple `configurations[2].params.k`), `ValidationFailed(errors: list[ConfigError])`, `BudgetExceeded`, `Inapplicable(reason)`, `ProviderError(retryable: bool)` et `NonConformantOutput`.

`core/ids.py` fournit `canonical_json(obj) -> str` (clés triées, `separators=(",", ":")`, Decimal sérialisé en chaîne), `sha16(*parts) -> str`, `slug(text) -> str` (minuscules, accents retirés, `[a-z0-9-]`) et `new_run_id(experiment_hash) -> str` au format `YYYYMMDD-HHMMSS-<6 hex>`, heure UTC.

## 2. Ports — `ports/`

Chaque Composant concret est une classe enregistrée (AD-2) :

```python
@register("chunker", "fixed_tokens")
class FixedTokenChunker:
    """Découpage en fenêtres de tokens fixes."""   # la docstring sert de description au registre
    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        size: int = 300
        overlap: int = 50
    def __init__(self, params: Params, ctx: RunContext) -> None: ...
```

Les `kind` forment une liste fermée : `parser`, `chunker`, `embedder`, `vector_store`, `lexical_index`, `graph_store`, `retriever`, `reranker`, `context_builder`, `decider`, `generator`, `judge`, `query_rewriter`, `architecture`.

```python
class ComponentSpec(BaseModel):            # forme YAML de toute référence à un Composant
    name: str
    params: dict[str, Any] = {}

# ports/components.py
class Parser(Protocol):
    formats: ClassVar[frozenset[str]]      # sous-ensemble de {"markdown","text","html","pdf"}
    def parse(self, source_path: str, raw: bytes, lang: str, meta: DocMeta) -> ParsedDocument: ...

class Chunker(Protocol):
    def key(self) -> str: ...              # nom + paramètres canoniques, entre dans passage_id
    def chunk(self, doc: ParsedDocument) -> list[Passage]: ...

class Embedder(Protocol):
    model_id: str                          # identifiant du Catalogue
    dim: int
    def embed_passages(self, texts: Sequence[str]) -> NDArray[np.float32]: ...  # (n, dim), norme L2 = 1
    def embed_queries(self, texts: Sequence[str]) -> NDArray[np.float32]: ...

class StoreCapabilities(BaseModel):
    hybrid: bool = False
    deletions: bool = True

class VectorStore(Protocol):
    capabilities: ClassVar[StoreCapabilities]
    dim: int
    def add(self, ids: Sequence[str], vectors: NDArray[np.float32]) -> None: ...
    def delete(self, ids: Sequence[str]) -> None: ...
    def search(self, query: NDArray[np.float32], k: int) -> list[tuple[str, float]]: ...  # score décroissant, ex æquo départagés par id
    def save(self, directory: Path) -> None: ...
    def load(self, directory: Path) -> None: ...

class LexicalIndex(Protocol):             # BM25
    def add(self, passages: Sequence[Passage]) -> None: ...
    def delete(self, ids: Sequence[str]) -> None: ...
    def search(self, text: str, k: int) -> list[tuple[str, float]]: ...
    def save(self, directory: Path) -> None: ...
    def load(self, directory: Path) -> None: ...

class GraphStore(Protocol):
    def upsert_entity(self, entity_id: str, name: str, kind: str, description: str,
                      passage_ids: Sequence[str]) -> None: ...
    def upsert_relation(self, source: str, target: str, description: str, weight: float,
                        passage_ids: Sequence[str]) -> None: ...
    def remove_passages(self, passage_ids: Sequence[str]) -> None: ...   # retire les entités et relations orphelines
    def graph(self) -> "networkx.Graph": ...
    def save(self, directory: Path) -> None: ...
    def load(self, directory: Path) -> None: ...

class SearchIndex(BaseModel):              # assemblé par l'Architecture, passé au Retriever
    model_config = ConfigDict(arbitrary_types_allowed=True)
    passages: dict[str, Passage]
    embedder: Embedder | None = None
    vectors: VectorStore | None = None
    lexical: LexicalIndex | None = None

class Retriever(Protocol):
    def retrieve(self, query: str, k: int, index: SearchIndex,
                 query_vector: NDArray[np.float32] | None = None) -> list[ScoredPassage]: ...
    # query_vector None : le Retriever appelle index.embedder.embed_queries([query]).
    # HyDE passe le vecteur de la réponse hypothétique (option mix_question : moyenne avec la question).
    # Retrievers enregistrés : dense, lexical, hybrid (fusion: rrf | weighted, rrf_k: 60, weight_dense: 0.5).

class Reranker(Protocol):
    def rerank(self, query: str, passages: Sequence[ScoredPassage], top_n: int) -> list[ScoredPassage]: ...

class Context(BaseModel):
    text: str                              # blocs "[S1] (ancrage) texte" concaténés
    blocks: tuple[str, ...]                # un bloc par étiquette, dans l'ordre
    labels: dict[str, tuple[str, ...]]     # "S1" -> anchor_ids (AD-7)
    passage_ids: dict[str, str]            # "S1" -> passage_id

class ContextBuilder(Protocol):
    def build(self, passages: Sequence[Passage]) -> Context: ...

class Generator(Protocol):
    model_id: str
    def generate(self, question: QuestionInput, context: Context) -> "GenerationResult": ...

class GenerationResult(BaseModel):
    text: str
    abstained: bool
    citations: tuple[Citation, ...]        # labels déjà convertis en ancrages, invalides retirés
    invalid_citations: int

class Decider(Protocol):
    model_id: str | None
    def grade(self, question: QuestionInput, passages: Sequence[Passage], loop: int = 0) -> list[float]: ...  # dans [0, 1] ; `loop` nomme l'étape `….loopN`

class QueryRewriter(Protocol):
    def rewrite(self, question: QuestionInput, loop: int = 1) -> str: ...

class JudgeInput(BaseModel):
    question: str
    reference_answer: str
    reference_texts: tuple[str, ...]       # texte des Ancrages de référence
    answer_text: str
    context_texts: tuple[str, ...]         # ce que le Generator a reçu (pour la fidélité)

class Judge(Protocol):
    model_id: str
    def judge(self, item: JudgeInput, criteria: Sequence[Criterion],
              pass_id: int) -> dict[Criterion, tuple[bool, str]]: ...
```

### 2.1 Architecture — `ports/architecture.py`

```python
class ArchCapabilities(BaseModel):
    incremental_update: bool = False       # False : update() = réindexation complète, au poste "update"
    retrieval_method: Literal["ranked", "provided", "cited", "none"] = "ranked"
    full_corpus_in_prompt: bool = False    # contexte long, CAG : contrôle de fenêtre et de palier
    requires_prompt_cache: bool = False    # CAG
    requires_hybrid_store: bool = False

class Applicability(BaseModel):
    applicable: bool
    reason: str | None = None

class CorpusChange(BaseModel):
    added: tuple[ParsedDocument, ...] = ()
    removed: tuple[str, ...] = ()          # doc_ids
    modified: tuple[tuple[str, ParsedDocument], ...] = ()   # (ancien doc_id, nouveau document)

class ArchitectureBase(ABC):
    name: ClassVar[str]
    Params: ClassVar[type[BaseModel]]      # extra="forbid" ; sous-Composants en ComponentSpec
    capabilities: ClassVar[ArchCapabilities]
    generator: Generator                   # requis : sert à la Condition contexte parfait
    context_builder: ContextBuilder

    query_params: ClassVar[frozenset[str]] = frozenset()   # Params sans effet sur l'index (k, seuils, bornes)

    def __init__(self, params: BaseModel, ctx: RunContext) -> None: ...  # sous-Composants via ctx.build(kind, spec)
    def check(self, profile: CorpusProfile) -> Applicability: ...       # défaut : applicable
    def index_key(self) -> dict[str, Any]: ...
        # défaut, à ne pas surcharger sauf besoin prouvé : Params résolus moins query_params,
        # plus parser résolu et ctx.tokenizer.name (AD-10)
    @abstractmethod
    def index(self, corpus: ParsedCorpus, directory: Path) -> None: ...   # écrit, ne garde pas d'état
    @abstractmethod
    def load(self, directory: Path) -> None: ...                         # seul moyen d'être prêt à répondre
    def update(self, change: CorpusChange, corpus_after: ParsedCorpus,
               old_directory: Path, new_directory: Path) -> None: ...   # défaut : index(corpus_after, new_directory)
    @abstractmethod
    def answer(self, question: QuestionInput) -> ArchAnswer: ...
    def answer_with_context(self, question: QuestionInput, passages: Sequence[Passage]) -> ArchAnswer: ...
        # défaut : context_builder.build -> generator.generate ; utilisé par la Condition contexte parfait
```

Les noms enregistrés des Architectures du MVP sont : `no_context`, `long_context`, `bm25_only`, `naive_rag`, `hybrid_rag`, `hyde`, `corrective_rag`, `cag`, `raptor`, `pageindex`, `llm_wiki`, `agentic`, `graphrag`, `lazy_graphrag`, `lightrag`.

Cycle de vie, piloté par le runner seul (AD-10, AD-11) :
1. Le runner parse le Corpus avec le `parser` de la Configuration et obtient un `ParsedCorpus`.
2. Il construit l'Architecture et calcule `index_key()`. Si l'index est absent, il appelle `index(corpus, tmp_dir)`, puis renomme `tmp_dir` vers le dossier final par `os.replace`.
3. Il construit une instance neuve et appelle `load(final_dir)`. Les chemins « cache absent » et « cache présent » sont donc identiques, et la conformité vérifie que leurs Réponses sont égales.
4. Pour chaque Question, il appelle `answer`.
5. Pour un Scénario de mise à jour, il appelle `update(..., old_dir, tmp_dir)`, renomme vers le dossier de la nouvelle clé, construit une instance neuve, appelle `load` et passe à la phase `after_update`.

Tout dossier d'index d'une Architecture à Passages contient `passages.jsonl` (un `Passage` par ligne, nœuds de résumé compris) et `manifest.json` (`index_key`, `architecture`, `corpus_fingerprint`, `created_at`, `embedder_dim` s'il y en a un).

Qui trace (AD-3, AD-17) : la passerelle pour les LLM, l'Embedder pour ses lots (un span `embed` par appel de `embed_*`), le Reranker pour ses appels (span `rerank`). Une Architecture ou un Retriever n'appellent jamais le Tracer.

Défauts des `Params` (PRD §7.3) : `k = 5` ; `corrective_rag` : `threshold = 0.5`, `max_loops = 2` ; `agentic` : `max_steps = 8`, `max_cost_per_question = {amount: "0.05", currency: USD}` ; `pageindex` : `max_nodes_read = 8` ; `raptor` : `group_min = 5`, `group_max = 10`, `max_depth = 3` ; `hyde` : `mix_question = false` ; `llm_wiki` : `fidelity_sample = 5` pages ; `hybrid_rag` : `fusion = rrf`, `reranker = null`.

### 2.2 Passerelle et mesure — `ports/gateway.py`, `ports/measure.py`

```python
LLMRole = Literal["generate", "judge", "rewrite", "hyde", "summarize", "extract_entities",
                  "select_nodes", "agent_step", "grade_relevance", "wiki_compile",
                  "wiki_fidelity", "community_report", "global_map",
                  "closed_book", "question_gen"]

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    cache: bool = False                    # point de cache de prompt après ce message (CAG)

class LLMRequest(BaseModel):
    model_id: str
    role: LLMRole
    step: str                              # nom d'étape de la Trace, ex. "generate", "crag.grade.loop1"
    system: str
    messages: tuple[Message, ...]
    max_tokens: int
    temperature: float | None = 0.0  # None : non envoyée (`accepts_temperature: false`, AD-20)
    seed: int | None = None
    cache_system: bool = False             # met le system en cache de prompt
    pass_id: int = 0                       # entre dans la clé du Cache de réponses (FR-34)
    timeout_s: float | None = None
    inputs: dict[str, Any] = {}            # données structurées du rôle (§3) ; lues par le Faux LLM seul,
                                           # hors clé de cache, sauf pour un modèle de provider fake ;
                                           # le prompt textuel reste libre

class LLMResult(BaseModel):
    text: str
    usage: Usage
    cost: Decimal                          # 0 si servi depuis le Cache de réponses
    cost_uncached: Decimal
    currency: str
    latency_s: float
    from_cache: bool

class ModelGateway(Protocol):
    def complete(self, request: LLMRequest, *, use_cache: bool = True) -> LLMResult: ...
        # use_cache=False : ne lit pas le Cache de réponses (préchargement CAG, story 6.5) ; un rejeu d'une Expérience CAG repaie donc le préchargement au Poste indexing
    def complete_structured(self, request: LLMRequest, schema: type[T]) -> tuple[T, LLMResult]: ...
        # lève NonConformantOutput après 1 nouvel essai si la sortie ne valide pas le schéma

class Tokenizer(Protocol):
    name: str
    def count(self, text: str) -> int: ...

class Tracer(Protocol):
    def record(self, step: str, kind: Literal["llm", "embed", "rerank", "local"], *,
               model_id: str | None, provider: str | None, usage: Usage, cost: Decimal,
               cost_uncached: Decimal, currency: str, latency_s: float, from_cache: bool,
               status: str = "ok", extra: Mapping[str, str | int | float | bool] = {}) -> None: ...
        # run_id, config_id, question_id, post et condition viennent du RunContext (AD-8)

class EnergyMeter(Protocol):              # local : mesuré par phase
    def start(self, phase: str) -> None: ...
    def stop(self) -> float | None: ...    # kWh, None si indisponible

class EnergyEstimator(Protocol):          # API : estimé par appel
    def estimate(self, model_id: str, usage: Usage, latency_s: float) -> float | None: ...
```

### 2.3 Catalogue et profil — `config/catalog.py`, `config/schemas.py`

```python
class Pricing(BaseModel):
    date: date
    currency: str
    per_mtok: dict[Literal["input", "output", "cache_read", "cache_write", "cache_write_1h"], Decimal]
    batch_per_mtok: dict[str, Decimal] | None = None
    tiers: tuple["PriceTier", ...] = ()    # PriceTier(above_prompt_tokens: int, multiplier: Decimal)

class ModelEntry(BaseModel):               # une entrée de models.yaml (§4.2)
    id: str; provider: Literal["anthropic", "ollama", "sentence_transformers", "fake"]
    family: str; kind: Literal["api", "local"]; modality: Literal["llm", "embedding", "reranker"]
    context_window: int | None = None; max_output_tokens: int | None = None
    tokenizer: Literal["reference", "approx"] = "reference"; token_factor: Decimal = Decimal("1.2")
    prompt_cache: bool = False; accepts_temperature: bool = True; min_cacheable_tokens: int | None = None
    pricing: Pricing | None = None; dim: int | None = None; hf_repo: str | None = None
    query_prefix: str = ""; passage_prefix: str = ""

class ModelCatalog(BaseModel):             # models.yaml entier
    catalog_date: date
    models: tuple[ModelEntry, ...]
    def get(self, model_id: str) -> ModelEntry: ...        # ConfigError si absent (FR-55)
    def cost(self, model_id: str, usage: Usage) -> Decimal: ...   # seul calcul de prix, palier compris

class CostSettings(BaseModel):             # costs.yaml (§4.2 bis), lu par report/ et measure/tco.py uniquement
    fx: FxRates                            # date, source, rates_to_eur
    owned_costs: OwnedCosts                # date, kwh_price_eur, hardware_name, hardware_price_eur,
                                           # hardware_life_hours, storage_eur_per_gb_month
    carbon: CarbonIntensity                # region, date, gco2e_per_kwh, note

class ProfileSettings(BaseModel):          # defaults/profiles/<nom>.yaml (§4.3)
    profile: Literal["cpu", "gpu", "test"]
    ollama: OllamaSettings; embedder_device: str; tokenizer: Literal["reference", "approx"]
    energy: EnergySettings                 # {local: codecarbon|fake, api: ecologits|fake, country_iso_code: "FRA"}
    defaults: RoleDefaults                 # generator_models, embedder, judge_pool, panel_size, closed_book_models,
                                           # question_gen_model, call_timeout_s
```

### 2.4 Contexte d'exécution — `runner/context.py` (Protocol publié dans `ports/context.py`)

```python
class RunContext(Protocol):
    run_id: str
    config_id: str
    seed: int
    condition: Condition                  # fixé par le runner
    tier: int | None
    phase: Phase
    gateway: ModelGateway
    tracer: Tracer
    tokenizer: Tokenizer                  # tokenizer de référence du profil
    parser: str                           # parser résolu de la Configuration (auto remplacé par les noms concrets), lu par index_key() (AD-10)
    catalog: ModelCatalog
    profile: ProfileSettings
    def build(self, kind: str, spec: ComponentSpec) -> Any: ...   # seule voie de construction (AD-2)
    def rng(self, *keys: str) -> random.Random: ...                # Random(sha16(seed, *keys))
    def tokenizer_for(self, model_id: str) -> Tokenizer: ...       # Catalogue, sinon référence × token_factor (défaut 1,2)
    @property
    def post(self) -> CostPost: ...                                 # fixé par le runner, lecture seule
    @property
    def question_id(self) -> str | None: ...
```

## 3. Rôles LLM et sorties — `llm/roles.py`

La passerelle préfixe toujours le system par `[[wl:role=<role>]]\n` (AD-4). Elle seule le fait. Les sorties structurées sont du JSON validé par le modèle pydantic du rôle. Le Faux LLM produit, pour chaque rôle, une sortie valide et déterministe.

Le Faux LLM ne lit jamais le texte du prompt : il lit `LLMRequest.inputs`, dont les clés sont fixées par rôle. Le Composant appelant les remplit toujours, avec le provider réel comme avec le faux.

| Rôle | `inputs` (clés obligatoires) | Schéma de sortie | Comportement du Faux LLM |
| --- | --- | --- | --- |
| `generate` | `question`, `blocks: {label: texte}` | `{"answer": str, "citations": ["S1", ...], "abstain": bool}` | Première phrase du bloc `S1` et citation `S1`. `blocks` vide : `abstain: true` |
| `judge` | `question`, `reference_answer`, `answer`, `criteria: [..]` | `{"verdicts": {"<criterion>": {"verdict": "yes"\|"no", "justification": str}}}` | `yes` si la réponse partage au moins 50 % des mots de la référence, sinon `no` |
| `rewrite`, `hyde`, `summarize`, `closed_book`, `community_report`, `global_map` | `text` (question, ou textes à résumer joints) | texte libre (`complete`) | `rewrite` et `closed_book` : renvoie `text` inchangé ; le Filtre closed-book retire de la réponse la question recopiée (`sans_question`), une question n'est donc jamais contaminée par le faux. Les autres : les 30 premiers mots de `text` |
| `extract_entities` | `text` | `{"entities": [{"name","kind","description"}], "relations": [{"source","target","description","weight"}]}` | Séquences de mots capitalisés, relation entre entités voisines |
| `select_nodes` | `question`, `nodes: [{id, title, summary}]`, `max` | `{"node_ids": [str], "done": bool}` | Les `max` premiers nœuds dont le titre ou le résumé partage un mot avec la question |
| `agent_step` | `question`, `step: int`, `last_results: [{id, text}]` | `{"action": "search"\|"read"\|"list"\|"answer", "args": {...}}` | Étape 1 `search(question)`, étape 2 `read` du premier résultat, puis `answer` avec la première phrase lue et sa citation |
| `grade_relevance` | `question`, `passages: [texte]` | `{"scores": [float, ...]}` (un score par Passage, dans [0, 1]) | Part des mots de la question présents dans le Passage |
| `wiki_compile` | `documents: [{source_path, blocks: [{anchor_id, text}]}]` | `{"pages": [{"title", "body", "anchor_ids": [str]}]}` | Une page par Document, corps = trois premiers Blocks |
| `wiki_fidelity` | `page`, `sources: [texte]` | `{"claims": int, "supported": int}` | `claims` = nombre de phrases de la page, `supported` = phrases dont la moitié des mots apparaît dans les sources |
| `question_gen` | `anchors: [{anchor_id, text}]`, `types: {type: nombre}` | `{"questions": [{"type","text","reference_answer","answer_form","anchor_ids"}]}` | Une question `factual` par Ancrage, dans l'ordre fourni |

Les Architectures `agentic` et `pageindex` doivent produire au moins une citation valide sur une question factuelle du Mini-corpus avec ce faux (suite de conformité).

Mode scénarisé (FR-52) : `FakeProvider.script(role: str, step_glob: str, output: str | Callable[[LLMRequest], str])`. La sortie scénarisée prime sur le comportement par défaut ; pour un modèle de provider fake, `step` entre donc dans la clé du Cache de réponses avec `inputs`. Tokens : nombre de mots. `cache_read_tokens` vaut le nombre de mots du préfixe déjà vu (system et messages marqués `cache`). La latence vaut 0 : le Faux LLM la déclare (`ProviderResponse.latency_s`) et la passerelle la reprend au lieu de la mesurer.

Protocole `Provider` (story 1.11) : `complete(request, *, timeout_s, output_schema=None) -> ProviderResponse(text, usage, latency_s?, energy_kwh?)`. `output_schema` est le schéma JSON de `complete_structured` (Anthropic : outil `emit_output` imposé ; Ollama : champ `format`). Un provider peut déclarer `schema_in_prompt` et `schema_prompt_overhead` : la passerelle ajoute alors le schéma (et le surcoût fixe) à l'estimation d'entrée. `ProviderError(sent=True)` : requête partie sans réponse, la réservation est réglée à l'estimation au lieu d'être libérée, et l'essai n'est jamais relancé (il a pu être facturé). Quand `output_schema` est donné, il entre dans la clé du Cache de réponses. Ollama pose `options.num_ctx` au `context_window` du Catalogue sauf si le profil le fixe. Les loggers `httpx2` et `httpcore2` (pile HTTP du SDK anthropic 1.15) sont limités comme `httpx` et `httpcore`.

## 4. Schémas YAML

Chaque schéma correspond à un modèle pydantic de `config/schemas.py` avec `extra="forbid"`. Les chemins relatifs se résolvent par rapport au fichier qui les contient.

### 4.1 Corpus — `corpus.yaml`

```yaml
corpus_id: minicorpus                 # [a-z0-9-]+
path: docs                            # dossier des Documents
lang: fr                              # langue par défaut ; un Document peut la surcharger
license: CC-BY-4.0
publishable: true                     # false ou licence restrictive : path hors dépôt ou ignoré par git (FR-5)
volatility: low                       # low | medium | high (déclarée au MVP)
documents:                            # optionnel, clé = source_path
  charte.md: {lang: fr, sensitivity: interne, rights_profiles: [rh]}
tiers:                                # optionnel (FR-54)
  seed: 42
  sizes: [5, 10, 20]
```

Les clés de `documents:` sont des `source_path`, relatifs à `path` (ici `docs`) ; la forme préfixée (`docs/charte.md`) est tolérée.

### 4.2 Catalogue de modèles — `defaults/models.yaml`

```yaml
catalog_date: 2026-10-17
models:
  - id: claude-haiku-5-5
    provider: anthropic                # anthropic | ollama | sentence_transformers | fake
    family: claude
    kind: api                          # api | local
    modality: llm                      # llm | embedding | reranker
    context_window: 1000000            # page Modèles Anthropic, relevée le 2026-10-17
    max_output_tokens: 128000
    tokenizer: reference               # reference | approx
    token_factor: "1.5"                # majoration du tokenizer de référence pour l'estimation (défaut 1.2) :
                                       # le tokenizer de Haiku 5.5 compte environ 30 % de tokens de plus que celui de Haiku 4.5
    prompt_cache: true
    min_cacheable_tokens: 512          # un préfixe plus court n'est pas mis en cache, sans erreur
    pricing:
      date: 2026-10-17                 # platform.claude.com/docs/en/about-claude/pricing
      currency: USD
      per_mtok: {input: "0.10", output: "0.50", cache_read: "0.01",
                 cache_write: "0.125", cache_write_1h: "0.20"}
      batch_per_mtok: {input: "0.05", output: "0.25"}
      tiers: [{above_prompt_tokens: 100000, multiplier: "5"}]
      # Le palier s'applique à toute la requête (tous les postes, y compris les tokens en cache)
      # dès que le prompt (entrée + lecture + écriture de cache) dépasse 100 000 tokens.
  - {id: "minicpm5:1b-q4_k_m", provider: ollama, family: minicpm, kind: local, modality: llm,
     context_window: 32768, max_output_tokens: 2048, tokenizer: reference, prompt_cache: false}
  - {id: "minicpm5:2b-q4_k_m", provider: ollama, family: minicpm, kind: local, modality: llm,
     context_window: 32768, max_output_tokens: 2048, tokenizer: reference, prompt_cache: false}
  - {id: "granite4.2:3b", provider: ollama, family: granite, kind: local, modality: llm,
     context_window: 32768, max_output_tokens: 2048, tokenizer: reference, prompt_cache: false}
  - {id: multilingual-e5-small, provider: sentence_transformers, hf_repo: intfloat/multilingual-e5-small,
     family: e5, kind: local, modality: embedding, dim: 384, query_prefix: "query: ", passage_prefix: "passage: "}
  # Le fichier livré contient aussi des entrées complètes pour :
  # - profil gpu : qwen3.5:4b (qwen), ministral-3:8b (mistral), bge-m3 (bge, dim 1024) ;
  # - profil test : fake-llm-a / fake-llm-b / fake-llm-c (provider fake, familles fake-a/b/c, kind api,
  #   prix fictif per_mtok {input: "1.00", output: "2.00", cache_read: "0.10", cache_write: "1.25"},
  #   prompt_cache: true, context_window: 100000, tokenizer: approx), fake-embedder (provider fake, dim 64).
```

Un modèle d'API sans `pricing` est refusé. Un modèle local n'a pas de `pricing` : son coût vient du Coût de possession (FR-31).

### 4.2 bis Paramètres de coût — `defaults/costs.yaml`

Ce petit fichier séparé regroupe tout ce qui dépend de la machine, du pays ou de la date de relevé. On le modifie sans toucher au code ni au Catalogue.

```yaml
fx:
  date: 2026-10-13
  source: "BCE, 1 EUR = 1,1188 USD"
  rates_to_eur: {USD: "0.8938"}
owned_costs:
  date: 2026-10-17
  kwh_price_eur: "0.2001"            # TRV EDF option Base 6 kVA TTC, depuis le 2026-08-01
  hardware_name: "PC de référence (RTX 3050 8 Go)"
  hardware_price_eur: "1200"         # hypothèse validée par Anaël le 2026-10-17, à remplacer par le prix réel
  hardware_life_hours: 20000         # hypothèse : environ 5 ans à 11 h par jour
  storage_eur_per_gb_month: "0.02"   # hypothèse
carbon:
  region: FR
  date: 2026-10-17
  gco2e_per_kwh: "19.6"              # RTE, bilan électrique 2025, émissions directes
  note: "≈ 29 g en analyse de cycle de vie"
```

Pour changer une valeur, deux voies :
- **Pour toutes les Exécutions** : copier `defaults/costs.yaml` vers `<WL_HOME>/costs.yaml` (ignoré par git) et l'éditer. Ce fichier local, s'il existe, remplace les valeurs par défaut clé par clé.
- **Pour une Expérience** : la clé `costs:` de l'Expérience désigne un autre fichier, au même schéma et fusionné de la même façon.

La précédence va de `defaults/costs.yaml` à `<WL_HOME>/costs.yaml`, puis au fichier `costs:` de l'Expérience. Les valeurs résolues sont écrites dans `experiment.resolved.yaml` et affichées avec leur date en tête du Rapport. Aucun de ces paramètres n'est écrit en dur dans le code.

### 4.3 Profils — `defaults/profiles/{cpu,gpu,test}.yaml`

```yaml
profile: cpu
ollama: {base_url: "http://localhost:11434", keep_alive: "5m", options: {num_gpu: 0}}
embedder_device: cpu
tokenizer: reference                   # test : approx (aucun téléchargement)
energy: {local: codecarbon, api: ecologits, country_iso_code: FRA}   # test : fake
defaults:
  generator_models: [claude-haiku-5-5, "minicpm5:1b-q4_k_m"]
  embedder: multilingual-e5-small
  judge_pool: ["minicpm5:2b-q4_k_m", "granite4.2:3b", claude-haiku-5-5]
  panel_size: 2
  closed_book_models: [claude-haiku-5-5, "minicpm5:1b-q4_k_m", "granite4.2:3b"]
  question_gen_model: claude-haiku-5-5
  call_timeout_s: 120
```

Le profil `gpu` remplace ces valeurs par `options: {}`, `embedder_device: cuda`, `qwen3.5:4b`, `ministral-3:8b` et `bge-m3` (PRD §7.3). Le profil `test` n'utilise que les modèles `fake-*`, `tokenizer: approx` et `energy: fake`.

### 4.4 Expérience — `experiments/*.yaml`

```yaml
experiment_id: mini-niveau1
seed: 42
profile: cpu                           # défaut cpu
corpus: ../corpora/minicorpus/corpus.yaml
questions: ../corpora/minicorpus/questions.yaml
split: dev                             # dev | test : test doit être explicite (FR-13)
tier: null                             # null = corpus entier ; sinon une taille déclarée dans tiers.sizes ; "all" = chaque palier
scenario: null                         # chemin d'un Scénario de mise à jour (FR-53)
conditions: [standard]                 # + perfect_context (FR-17)
catalog: null                          # null = defaults/models.yaml
costs: null                            # null = defaults/costs.yaml, puis <WL_HOME>/costs.yaml s'il existe (§4.2 bis)
models_frozen_at: 2026-10-17           # FR-4 : date affichée au Rapport
max_questions: null                    # tests réels : 5
budget:
  per_run: {anthropic: {amount: "5.00", currency: USD}}
  period:  {anthropic: {amount: "50.00", currency: USD}, azure: {amount: "50.00", currency: EUR}}   # mois civil UTC
judges:
  pool: null                           # null = profil.defaults.judge_pool
  panel_size: 2
  passes: 1                            # `wl calibrer` impose au moins calibration_passes
  calibration_passes: 5
  kappa_threshold: 0.6
  calibration_judge: null
  excluded_from: null                  # chemin d'un calibration.json (Juges exclus)
stats: {resamples: 2000, confidence: 0.95, alpha: 0.05}
retries: {max_attempts: 3, backoff_s: 1.0, max_backoff_s: 30.0}
configurations:
  - id: naive-haiku                    # [a-z0-9-]+, unique
    architecture: naive_rag
    parser: {name: auto}               # niveau Configuration : le runner parse (AD-10).
                                       # auto = markdown -> markdown, text -> text, html -> html, pdf -> pdf_text,
                                       # remplacé par les noms concrets avant le hachage
    reuse_index: null                  # index_key explicite à réutiliser (FR-3 : dimension vérifiée au manifeste)
    params:
      chunker: {name: fixed_tokens, params: {size: 300, overlap: 50}}
      embedder: {name: sentence_transformers, params: {model: multilingual-e5-small}}
      store: {name: numpy_exact}
      retriever: {name: dense}
      context_builder: {name: labeled}
      generator: {name: llm, params: {model: claude-haiku-5-5, max_tokens: 512}}
      k: 5
```

Ordre de priorité (AD-12) : valeurs par défaut du code, puis profil, puis Expérience. `config/resolve.py` parcourt récursivement les `Params` (les `ComponentSpec` imbriqués sont résolus par le registre). Il remplace chaque champ `ModelRef` resté `None` par la valeur de profil désignée par `role_default`, puis collecte la liste des modèles de la Configuration et ses modèles `answer_producer`. Un `embedder` omis prend `profile.defaults.embedder`, avec le Composant `sentence_transformers` ou `fake` selon le fournisseur au Catalogue. Le fichier `experiment.resolved.yaml` contient toutes les valeurs résolues.

### 4.5 Questions — `questions.yaml` (un fichier par Corpus)

```yaml
corpus_id: minicorpus
target_count: 150                      # D1 (le Mini-corpus : 40)
freeze: null                           # écrit par `wl questions geler`, jamais à la main
#  freeze: {sha256: "...", at: "2026-10-17T22:10:00Z", seed: 42, dev_ratio: 0.4}
questions:
  - id: q-001                          # stable, jamais réutilisé
    type: factual
    follow_up: false
    cross_lingual: false
    text: "En quelle année la guilde d'Orvane a-t-elle été fondée ?"
    lang: fr
    reference_answer: "1412"
    answer_form: short                 # short (<= 5 mots, nombre, date) | free
    reference_anchors:                 # vide pour unanswerable
      - {doc: docs/annales-orvane.md, headings: ["Histoire", "Fondation"]}
      - {doc: docs/registre.pdf, page: 3}
    status: validated                  # generated | validated | corrected | rejected
    split: null                        # dev | test, attribué au Gel
    contaminated_by: []                # identifiants de modèles (Filtre closed-book)
    history: []                        # [{role: user, text: ...}, {role: assistant, text: ...}]
    origin: {kind: model, name: claude-code-dev-agent}   # kind: human | model
    scenario_target: null              # {operation: op-2, state: after} pour les questions de mise à jour
```

L'empreinte du Gel est `sha256(canonical_json(document sans "freeze" ni "contaminated_by"))` (AD-15). Seules les questions `validated` et `corrected` participent à une Exécution.
Au Gel, chaque Type reçoit `round_half_up(n × dev_ratio)` Questions dev (10 × 0,4 = 4 ; 1 × 0,4 = 0, donc une Question seule de son Type va en test). Un re-Gel qui ferait changer de partie une Question déjà répartie est refusé sans `--forcer`. Les Questions contaminées restent dans leur partie : le Rapport les exclut des scores principaux (FR-12).

### 4.6 Annotations humaines — `annotations/<annotateur>.yaml`

```yaml
annotator: anael
annotations:
  - answer_id: "20261018-031500-a1b2c3/naive-haiku/standard/all/base/q-001"   # format complet de §1
    criterion: correctness             # correctness | completeness | faithfulness
    verdict: yes                       # yes | no
    note: ""
```

`wl calibrer` écrit `calibration.json` : par Juge et par Critère, kappa juge-humain, taux d'instabilité et `excluded: bool`. Il y ajoute le kappa entre annotateurs.

### 4.7 Scénario de mise à jour — `scenario.yaml`

```yaml
scenario_id: minicorpus-maj-1
corpus_id: minicorpus
operations:                            # appliquées dans l'ordre
  - {id: op-1, op: add,    source: updates/chronique-1415.md, target: chronique-1415.md}
  - {id: op-2, op: modify, source: updates/charte-v2.md,      target: charte.md}
  - {id: op-3, op: delete,                                    target: note-obsolete.md}
```

`target` est un `source_path` du Corpus, relatif à son `path` (ici `docs`). `source` se résout par rapport au fichier du scénario.

## 5. Fichiers d'une Exécution — `<WL_HOME>/runs/<run_id>/`

| Fichier | Contenu | Écrivain unique |
| --- | --- | --- |
| `experiment.resolved.yaml`, `experiment.sha256` | Expérience résolue et son empreinte | runner |
| `manifest.json` | `status` (`running`, `completed`, `budget_exceeded`, `failed`), profil, `models_frozen_at`, liste des modèles, empreinte du Gel | runner |
| `corpus_profile.json` | Profil de corpus (FR-7) | runner, via `corpus/profile.py` |
| `answers.jsonl` | un `Answer` par (config_id, condition, tier, phase, question_id) | runner |
| `panel.jsonl` | verdict agrégé par (answer_id, criterion) : `verdict`, `tie: bool`, juges admissibles | runner, via `scoring/panel.py` |
| `wiki_fidelity.json` | par Configuration `llm_wiki` : pages échantillonnées, `claims`, `supported` | Architecture `llm_wiki`, dans son dossier d'index, copié par le runner |
| `run.log` | journal `logging` de l'Exécution, sans secret | runner |
| `verdicts.jsonl` | un `Verdict` par (answer_id, judge_model, criterion, pass_id) | runner, via `scoring/panel.py` |
| `traces.jsonl` | une ligne par span OpenTelemetry (§6) | `measure/tracing.py` |
| `applicability.json` | Configurations inapplicables et leur raison | runner |
| `report/report.md`, `scores.csv`, `pairs.csv`, `pareto.csv`, `costs.csv`, `retrieval.csv` | Rapport (FR-40) | `report/` |

À la reprise (`wl run --reprendre <run_id>`), le runner relit `answers.jsonl` et `verdicts.jsonl` et ne refait que les clés absentes (AD-11). `traces.jsonl` n'est jamais réécrit. Les appels refaits sortent du Cache de réponses et coûtent 0, donc la dépense n'est pas comptée deux fois.

Le dossier `<WL_HOME>` (défaut `./.wl`, ignoré par git) contient aussi `ledger.sqlite` (registre de dépense), `llm_cache.sqlite`, `parse_cache/<parser>/<doc_id>.json`, `index/<index_key>/` (avec un `manifest.json`) et `run.lock`. Ce verrou tient une seule Exécution à la fois : un second `wl run` sort avec le code 1 et le message « Exécution <run_id> en cours ».

## 6. Attributs des traces

Chaque appel produit un span. Son `name` est l'étape, ses `start_time` et `end_time` sont en nanosecondes. L'exporteur `JsonlSpanExporter` écrit une ligne par span avec `trace_id`, `span_id`, `name`, `start_time`, `end_time` et les attributs suivants.

| Attribut | Type |
| --- | --- |
| `wl.run_id`, `wl.config_id`, `wl.question_id`, `wl.condition`, `wl.phase` | str (`question_id` vide hors requête) |
| `wl.tier` | int (absent si aucun palier) |
| `wl.post` | `indexing` \| `update` \| `query` \| `judging` \| `evalset` |
| `wl.index_cache_hit` | bool (sur le span `index` émis par le runner : un span `local` par index chargé ou construit) |
| `wl.step`, `wl.kind` | str ; `llm` \| `embed` \| `rerank` \| `local` |
| `gen_ai.provider.name`, `gen_ai.request.model` | str |
| `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | int |
| `wl.usage.cache_read_tokens`, `wl.usage.cache_write_tokens` | int |
| `wl.cost`, `wl.cost_uncached`, `wl.currency` | str (Decimal), str, str |
| `wl.llm_cache_hit` | bool |
| `wl.latency_s` | float |
| `wl.energy_kwh`, `wl.energy_method` | float (absent si inconnu) ; `measured` \| `estimated` \| `unknown` |
| `wl.status` | `ok` \| `error` \| `budget_refused` \| `non_conformant` |
| `wl.invalid_citations`, `wl.loop` | int (si pertinent) |

## 7. Rapport — `report/` (FR-31, FR-39, FR-40, FR-53, FR-54)

Toutes les grandeurs se calculent à partir de `answers.jsonl`, `panel.jsonl`, `verdicts.jsonl` et `traces.jsonl` uniquement. Elles sont groupées par (config_id, condition, tier, phase). Les Questions contaminées sont exclues des scores principaux et rapportées dans une section à part. La partie (`dev` ou `test`) est rappelée en tête du Rapport.

| Grandeur | Définition |
| --- | --- |
| Qualité | Part des Questions où `correctness` vaut oui. Pour `unanswerable`, la Question compte comme correcte si `abstention_correctness` vaut oui |
| Scores par Critère | Taux de oui par Critère et par Type de question, avec IC bootstrap (2 000 rééchantillons, 95 %, graine de l'Expérience) |
| Métriques de recherche | rappel@k, MRR et nDCG@k, par Question puis par Type ; un Passage est pertinent si `anchor_ids` ∩ Ancrages de référence ≠ ∅. La colonne `method` reprend `retrieval_method` |
| Comparaisons appariées | Pour chaque paire de Configurations, sur les Questions communes : McNemar exact (`scipy.stats.binomtest` sur les paires discordantes) pour les verdicts, bootstrap apparié pour les métriques continues ; `n_common` affiché |
| Qualité égale | p ≥ 0,05 sur la différence de Qualité, ou A significativement supérieure pour « égale ou supérieure » |
| Coût par poste | Somme de `wl.cost` des spans par `wl.post`, convertie en euros au taux du Catalogue. Le calcul local ajoute le Coût de possession : kWh × prix du kWh, plus prix du matériel ÷ durée de vie × durée des spans locaux, plus stockage de l'index. Les colonnes `cost_real` et `cost_uncached` (somme de `wl.cost_uncached`) sont séparées. `judging` et `evalset` sont affichés à part |
| Coût par requête, pour 1 000 requêtes | coût `query` ÷ nombre de Questions répondues ; × 1 000 |
| Latence p50, p95 | Quantiles de `Answer.latency_s` |
| Débit | Questions répondues ÷ durée murale de la phase query, en minutes |
| Point mort | Pour A (indexation plus chère) contre B : N* = (indexation_A − indexation_B) ÷ (requête_B − requête_A). Calculé seulement si la Qualité de A est égale ou supérieure à celle de B et si requête_A < requête_B. Sinon, le Rapport écrit la raison |
| Fraîcheur | Parmi les Questions dont `scenario_target` est défini, part des Questions correctes en phase `after_update` |
| Énergie | kWh par poste, en colonnes séparées `measured` et `estimated`, jamais additionnées. CO2e = kWh × intensité du Catalogue |
| Fronts de Pareto | Non dominés sur (Qualité ↑, coût total ↓), (Qualité ↑, énergie ↓), (Qualité ↑, latence p95 ↓), plus un front (taux du Critère ↑, coût total ↓) par Critère. Coût total = indexation + mise à jour + requête |
| Inapplicables | Reprises de `applicability.json`, avec leur raison |
| Juges | Panel admissible par Configuration, Juges exclus par la calibration, nombre d'égalités signalées |

Fichiers produits :
- `scores.csv` : config_id, condition, tier, phase, question_type, criterion, value, ci_low, ci_high, n.
- `retrieval.csv` : config_id, …, metric, k, value, ci_low, ci_high, method.
- `pairs.csv` : config_a, config_b, metric, diff, p_value, test, n_common.
- `costs.csv` : config_id, post, cost_eur_real, cost_eur_uncached, kwh_measured, kwh_estimated, co2e_g, n_calls.
- `pareto.csv` : front, config_id, x, y.
- `export.py` écrit le front choisi sous forme de liste `configurations:` réutilisable dans une nouvelle Expérience (FR-41).

## 8. Commandes `wl` — `cli.py` (typer)

Les noms des sous-commandes suivent le PRD (§5). Chaque commande a son aide `--help` en français. Les codes de sortie sont : 0 succès, 1 erreur, 2 configuration invalide, 3 plafond atteint, 4 préflight échoué (Ollama injoignable, modèle ou clé absents).

| Commande | Effet | FR |
| --- | --- | --- |
| `wl corpus profiler <corpus.yaml> [--parser auto]` | Ingestion et `corpus_profile.json` | FR-5 à FR-7 |
| `wl corpus paliers <corpus.yaml>` | Liste des Paliers de volume tirés | FR-54 |
| `wl questions generer <corpus.yaml> --repartition factual=40,multi_hop=20,… [--modele]` | Ajoute des questions `generated` | FR-10 |
| `wl questions controler <questions.yaml> --corpus <corpus.yaml> [--scenario <scenario.yaml>]` | Comptes par statut et par type, écart à `target_count`, ancrages introuvables (code 2) ; `--scenario` résout les Questions `scenario_target` dans le Corpus après mise à jour | FR-9, FR-11 |
| `wl questions closed-book <questions.yaml> [--modeles …]` | Remplit `contaminated_by` | FR-12 |
| `wl questions geler <questions.yaml> [--dev-ratio 0.4] [--graine 42]` | Attribue `split`, écrit `freeze` | FR-13 |
| `wl run <experience.yaml> [--reprendre <run_id>]` | Validation, préflight, Exécution, puis Rapport (`cli.py` enchaîne runner et `report/`, AD-1) | FR-1, FR-33 |
| `wl rapport <run_id> [--exporter-front <front> --vers <fichier>]` | Régénère le Rapport ; exporte un front | FR-40, FR-41 |
| `wl calibrer <experience.yaml> --annotations <dossier> --run <run_id>` | Écrit `calibration.json` | FR-38 |
| `wl registre [--kind …]` | Liste les Composants et les Architectures, leurs Params et leur description | FR-2 |
| `wl installer --profil cpu\|gpu` | Télécharge l'embedder et l'encodage tiktoken, vérifie `ollama list` | §5 |
