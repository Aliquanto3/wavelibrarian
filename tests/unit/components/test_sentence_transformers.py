"""Story 1.12 : embedder sentence-transformers (double injecté, aucun modèle, aucun réseau)."""

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from wavelibrarian import registry
from wavelibrarian.components.embedders.sentence_transformers import SentenceTransformersEmbedder
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import Condition, CostPost, Phase
from wavelibrarian.measure.tokenizers import ApproxTokenizer
from wavelibrarian.measure.tracing import Tracer
from wavelibrarian.ports.components import ComponentSpec, Embedder


class _Ctx:
    run_id = "run-1"
    config_id = "cfg-1"
    condition: Condition = "standard"
    tier: int | None = None
    phase: Phase = "base"
    post: CostPost = "indexing"
    question_id: str | None = None

    def __init__(self, path: Path, profil: str = "cpu") -> None:
        self.catalog = load_catalog()
        self.profile = load_profile(profil)
        self.tracer = Tracer(self, path)

    def tokenizer_for(self, _model_id: str) -> ApproxTokenizer:
        return ApproxTokenizer()

    def build(self, kind: str, spec: ComponentSpec) -> Any:
        cls = registry.get(kind, spec.name)
        return cls(cls.Params(**spec.params), self)


class _DoubleModele:
    """Double de `SentenceTransformer` : garde ce qu'on lui demande, renvoie des vecteurs non
    normalisés pour vérifier la normalisation."""

    instances: list["_DoubleModele"] = []
    dim = 384

    def __init__(self, repo: str, **kwargs: Any) -> None:
        self.repo, self.kwargs = repo, kwargs
        self.lots: list[list[str]] = []
        _DoubleModele.instances.append(self)

    def encode(self, textes: list[str], **_kw: Any) -> Any:
        self.lots.append(list(textes))
        rng = np.random.default_rng(len(textes))
        return rng.normal(size=(len(textes), self.dim)) * 5.0


@pytest.fixture(autouse=True)
def decouverte_isolee() -> Iterator[None]:
    decouvert = registry._decouvert
    yield
    registry._decouvert = decouvert


@pytest.fixture
def double(monkeypatch: pytest.MonkeyPatch) -> type[_DoubleModele]:
    _DoubleModele.instances = []
    _DoubleModele.dim = 384
    faux: Any = type(sys)("sentence_transformers")
    faux.SentenceTransformer = _DoubleModele
    monkeypatch.setitem(sys.modules, "sentence_transformers", faux)
    return _DoubleModele


@pytest.fixture
def ctx(tmp_path: Path) -> _Ctx:
    return _Ctx(tmp_path / "traces.jsonl")


def _construire(ctx: _Ctx, **params: Any) -> Any:
    return ctx.build("embedder", ComponentSpec(name="sentence_transformers", params=params))


def test_enregistre_et_construit_sans_l_extra(ctx: _Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # import impossible
    registry.discover()
    assert registry.get("embedder", "sentence_transformers") is SentenceTransformersEmbedder
    emb = _construire(ctx)  # la construction ne lève pas
    assert isinstance(emb, Embedder)
    assert (emb.model_id, emb.dim) == ("multilingual-e5-small", 384)


def test_premier_usage_sans_l_extra_leve(ctx: _Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    emb = _construire(ctx)
    with pytest.raises(WlError, match="installer l'extra local"):
        emb.embed_queries(["bonjour"])


def test_prefixes_du_catalogue(ctx: _Ctx, double: type[_DoubleModele]) -> None:
    emb = _construire(ctx)
    emb.embed_queries(["a", "b"])
    emb.embed_passages(["c"])
    assert double.instances[0].lots == [["query: a", "query: b"], ["passage: c"]]


def test_bge_m3_sans_prefixe_et_device_cuda(tmp_path: Path, double: type[_DoubleModele]) -> None:
    double.dim = 1024
    emb = _construire(_Ctx(tmp_path / "g.jsonl", "gpu"))
    assert emb.model_id == "bge-m3"
    v = emb.embed_queries(["x"])
    assert v.shape == (1, 1024)
    modele = double.instances[0]
    assert modele.lots == [["x"]]  # préfixes vides au Catalogue
    assert modele.repo == "BAAI/bge-m3" and modele.kwargs["device"] == "cuda"


def test_forme_inattendue_refusee(tmp_path: Path, double: type[_DoubleModele]) -> None:
    emb = _construire(_Ctx(tmp_path / "g.jsonl", "gpu"))  # bge-m3 attend 1024, le double 384
    with pytest.raises(WlError, match="forme"):
        emb.embed_passages(["x"])


def test_device_du_profil_et_cache_local(double: type[_DoubleModele], ctx: _Ctx) -> None:
    _construire(ctx).embed_passages(["x"])
    modele = double.instances[0]
    assert modele.repo == "intfloat/multilingual-e5-small"
    assert modele.kwargs["device"] == "cpu" and modele.kwargs["local_files_only"] is True


def test_vecteurs_normalises_et_modele_charge_une_fois(
    ctx: _Ctx, double: type[_DoubleModele]
) -> None:
    emb = _construire(ctx)
    v = emb.embed_passages(["a", "b", "c"])
    assert v.shape == (3, 384) and v.dtype == np.float32
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5)
    emb.embed_queries(["d"])
    assert len(double.instances) == 1
    assert emb.embed_passages([]).shape == (0, 384)


def test_un_span_embed_par_lot(ctx: _Ctx, double: type[_DoubleModele], tmp_path: Path) -> None:
    emb = _construire(ctx, batch_size=2)
    emb.embed_passages(["un deux", "trois", "quatre cinq six"])
    assert [len(lot) for lot in double.instances[0].lots] == [2, 1]
    spans = [json.loads(x) for x in (tmp_path / "traces.jsonl").read_text("utf-8").splitlines()]
    assert len(spans) == 2 and all(s["name"] == "embed" for s in spans)
    assert all(s["wl.kind"] == "embed" and s["wl.cost"] == "0" for s in spans)
    assert spans[0]["gen_ai.request.model"] == "multilingual-e5-small"
    # mots comptés sur le texte préfixé ("passage:" compte pour un mot)
    assert [s["gen_ai.usage.input_tokens"] for s in spans] == [5, 4]


@pytest.mark.real_local
def test_real_local_encode_deux_phrases(tmp_path: Path) -> None:
    """Encode deux phrases avec le vrai `multilingual-e5-small` ; sauté sans modèle installé."""
    from wavelibrarian.llm.local_models import embedder_installe

    pytest.importorskip("sentence_transformers")
    if not embedder_installe("intfloat/multilingual-e5-small"):
        pytest.skip("multilingual-e5-small absent du cache local (wl installer)")
    emb = _construire(_Ctx(tmp_path / "t.jsonl"))
    v = emb.embed_passages(["Le chat dort sur le canapé.", "La recette demande deux oeufs."])
    assert v.shape == (2, 384)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)
    q = emb.embed_queries(["Où dort le chat ?"])
    assert float(q[0] @ v[0]) > float(q[0] @ v[1])
