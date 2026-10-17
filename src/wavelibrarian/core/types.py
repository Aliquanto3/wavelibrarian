"""Types du domaine (contracts.md §1). Aucune entrée-sortie."""

import math
from decimal import Decimal
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from wavelibrarian.core.ids import slug

QuestionType = Literal[
    "factual",
    "multi_hop",
    "global",
    "comparison",
    "numeric_aggregation",
    "temporal",
    "unanswerable",
    "knowledge_trap",
    "visual",
]
Criterion = Literal[
    "correctness", "completeness", "faithfulness", "citation_correctness", "abstention_correctness"
]
JUDGED_CRITERIA: tuple[Criterion, ...] = ("correctness", "completeness", "faithfulness")
# judging (Juges, Filtre closed-book en Exécution) et evalset (génération de questions) sont
# affichés à part et exclus du coût d'une Configuration dans le Rapport.
CostPost = Literal["indexing", "update", "query", "judging", "evalset"]
Condition = Literal["standard", "perfect_context"]
Phase = Literal["base", "after_update"]  # avant / après application du Scénario de mise à jour


class ModelRefMeta:
    """Marqueur `Annotated` : un champ de Params qui désigne un modèle du Catalogue.

    `role_default` : clé de `profil.defaults` utilisée si la valeur est None.
    `answer_producer` : True pour le modèle qui écrit le texte de la Réponse (règle de famille).
    """

    def __init__(self, role_default: str, answer_producer: bool = False) -> None:
        self.role_default = role_default
        self.answer_producer = answer_producer

    def __repr__(self) -> str:
        return f"ModelRefMeta({self.role_default!r}, answer_producer={self.answer_producer})"


ModelRef = Annotated[str | None, ModelRefMeta]


class _Modele(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _EntreeCatalogue(Protocol):
    @property
    def tokenizer(self) -> str: ...

    @property
    def token_factor(self) -> Decimal: ...


class _CatalogueTokens(Protocol):
    """Vue minimale du Catalogue (la classe réelle vit dans `config`, couche supérieure)."""

    def get(self, model_id: str) -> _EntreeCatalogue: ...


class DocMeta(_Modele):
    sensitivity: str | None = None
    rights_profiles: tuple[str, ...] = ()


class Anchor(_Modele):
    anchor_id: str  # "<doc_id>#p<page>" ou "<doc_id>#h/<slug>/<slug>"
    doc_id: str
    source_path: str  # chemin POSIX relatif à la racine du corpus
    page: int | None = None  # numérotée à partir de 1
    heading_path: tuple[str, ...] = ()  # titres bruts, du plus haut au plus bas


class Block(_Modele):
    text: str
    anchor_id: str
    kind: Literal["text", "table", "heading", "image"]


class ParsedDocument(_Modele):
    doc_id: str  # sha256(octets bruts)[:16]
    source_path: str
    format: Literal["markdown", "text", "html", "pdf"]
    lang: str  # ISO 639-1
    blocks: tuple[Block, ...]
    anchors: dict[str, Anchor]  # anchor_id -> Anchor, dans l'ordre du document
    meta: DocMeta = DocMeta()


class ParsedCorpus(_Modele):
    corpus_id: str
    fingerprint: str  # sha256 des (source_path, doc_id) triés, [:16]
    documents: tuple[ParsedDocument, ...]  # triés par source_path

    def anchor_text(self, anchor_id: str) -> str:
        """Concatène, dans l'ordre, les Blocks de l'ancrage (vide si l'ancrage est inconnu)."""
        doc_id = anchor_id.split("#", 1)[0]
        for doc in self.documents:
            if doc.doc_id == doc_id:
                return "\n\n".join(b.text for b in doc.blocks if b.anchor_id == anchor_id)
        return ""

    def resolve(self, source_path: str, page: int | None, headings: tuple[str, ...]) -> str | None:
        """Renvoie l'`anchor_id` (page prioritaire, sinon titres) ou None s'il n'existe pas.

        Les titres sont d'abord cherchés tels quels (espaces normalisés) dans les `heading_path`,
        dans l'ordre du Document : « Note 2 » désigne ce titre, pas le doublon suffixé `note-2`.
        À défaut, le chemin de slugs n'est essayé que si chaque titre est déjà un slug
        (`note-2`) : « Note 2 » sans titre de ce nom ne résout pas le doublon de « Note ».
        """
        for doc in self.documents:
            if doc.source_path != source_path:
                continue
            if page is not None:
                candidat = f"{doc.doc_id}#p{page}"
            elif headings:
                voulu = tuple(" ".join(h.split()) for h in headings)
                for anchor_id, ancre in doc.anchors.items():
                    if ancre.page is None and ancre.heading_path == voulu:
                        return anchor_id
                if any(h != slug(h) for h in headings):
                    return None
                candidat = f"{doc.doc_id}#h/" + "/".join(headings)
            else:
                return None
            return candidat if candidat in doc.anchors else None
        return None


class Passage(_Modele):
    passage_id: (
        str  # level 0 : sha16(doc_id, chunker_key, ordinal) ; level > 0 : sha16("node", ...)
    )
    doc_id: str | None  # obligatoire si level == 0 ; None pour un nœud multi-documents
    text: str
    anchor_ids: tuple[str, ...]  # non vide ; level > 0 : union des anchor_ids des feuilles (AD-7)
    level: int = 0  # 0 = feuille ; >0 = nœud de résumé
    child_ids: tuple[str, ...] = ()  # nœuds de résumé : passage_ids des enfants


class ScoredPassage(_Modele):
    passage: Passage
    score: float
    rank: int  # 1 = meilleur


class ConversationTurn(_Modele):
    role: Literal["user", "assistant"]
    text: str


class QuestionInput(_Modele):
    """Seule vue de la Question que voit une Architecture (AD-6)."""

    question_id: str
    text: str
    lang: str
    history: tuple[ConversationTurn, ...] = ()


class Citation(_Modele):
    anchor_id: str


class ArchAnswer(_Modele):
    """Ce que renvoie une Architecture ; le runner le complète en `Answer`."""

    text: str
    abstained: bool
    citations: tuple[Citation, ...] = ()
    retrieved: tuple[ScoredPassage, ...] = ()
    # "ranked" : liste classée du Retriever. "provided" : Passages fournis au Generator.
    # "cited" : un ScoredPassage par ancrage cité. "none" : vide.
    retrieval_method: Literal["ranked", "provided", "cited", "none"] = "ranked"
    context_anchor_ids: tuple[str, ...] = ()  # ancrages réellement fournis au Generator
    context_texts: tuple[str, ...] = ()  # Context.blocks fournis au Generator (fidélité)
    context_truncated: bool = False  # True si > 8 000 tokens : seuls les blocs cités sont gardés
    invalid_citations: int = 0


class Answer(ArchAnswer):
    """Écrit par le runner uniquement."""

    answer_id: str  # "<run_id>/<config_id>/<condition>/<tier>/<phase>/<question_id>"
    question_id: str
    config_id: str
    condition: Condition = "standard"
    tier: int | None = None
    phase: Phase = "base"
    status: Literal["ok", "error", "inapplicable", "budget_exceeded"]
    error: str | None = None
    latency_s: float = 0.0  # somme des latences des spans du poste query pour cette Question


class AnchorRef(_Modele):
    """Forme YAML d'un Ancrage de référence."""

    doc: str  # source_path
    page: int | None = None
    headings: tuple[str, ...] = ()


class Question(_Modele):
    """Enregistrement de `questions.yaml` (contracts §4.5)."""

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
    origin: dict[str, str]  # {"kind": "human"|"model", "name": ...}
    scenario_target: dict[str, str] | None = None  # {"operation": "op-2", "state": "after"}


class CorpusProfile(_Modele):
    """Profil du Corpus (FR-7), écrit en `corpus_profile.json`."""

    corpus_id: str
    fingerprint: str
    parser: str
    tokenizer: str  # nom du tokenizer de référence
    n_documents: int
    n_tokens: int  # tokenizer de référence
    mean_tokens_per_document: float
    heading_depth_max: int
    heading_depth_mean: float
    link_density: float  # part des Documents partageant >= 1 entité nommée avec un autre
    table_share: float  # part des tokens dans des Blocks "table"
    images_per_document: float
    dominant_lang: str
    langs: dict[str, int]  # langue -> nombre de Documents
    formats: dict[str, int]
    volatility: Literal["low", "medium", "high"]

    def tokens_for(self, model_id: str, catalog: _CatalogueTokens) -> int:
        """Tokens du Corpus pour un modèle : référence si le Catalogue le dit, sinon × facteur."""
        entree = catalog.get(model_id)
        if entree.tokenizer == "reference":
            return self.n_tokens
        return math.ceil(Decimal(self.n_tokens) * Decimal(entree.token_factor))


class Usage(_Modele):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class Verdict(_Modele):
    answer_id: str
    judge_model: str  # identifiant du Catalogue ; "auto" si calculé sans Juge
    criterion: Criterion
    pass_id: int = 0
    verdict: bool
    justification: str = ""
