"""Story 1.10 : faux embedder (déterministe, dimension 64, norme 1, span `embed`)."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from wavelibrarian import registry
from wavelibrarian.components.embedders.fake import FakeEmbedder
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.core.types import Condition, CostPost, Phase
from wavelibrarian.measure.tokenizers import ApproxTokenizer
from wavelibrarian.measure.tracing import Tracer
from wavelibrarian.ports.components import ComponentSpec, Embedder

TEXTES = ["orvane guilde fondation", "guilde d'orvane", "recette de cuisine"]


class _Ctx:
    run_id = "run-1"
    config_id = "cfg-1"
    condition: Condition = "standard"
    tier: int | None = None
    phase: Phase = "base"
    post: CostPost = "indexing"
    question_id: str | None = None

    def __init__(self, path: Path) -> None:
        self.catalog = load_catalog()
        self.profile = load_profile("test")
        self.tracer = Tracer(self, path)

    def tokenizer_for(self, _model_id: str) -> ApproxTokenizer:
        return ApproxTokenizer()

    def build(self, kind: str, spec: ComponentSpec) -> Any:
        cls = registry.get(kind, spec.name)
        return cls(cls.Params(**spec.params), self)


@pytest.fixture(autouse=True)
def decouverte_isolee() -> Iterator[None]:
    decouvert = registry._decouvert
    yield
    registry._decouvert = decouvert


@pytest.fixture
def ctx(tmp_path: Path) -> _Ctx:
    return _Ctx(tmp_path / "traces.jsonl")


def test_enregistre_et_construit_par_le_contexte(ctx: _Ctx) -> None:
    registry.discover()
    assert registry.get("embedder", "fake") is FakeEmbedder
    emb = ctx.build("embedder", ComponentSpec(name="fake"))
    assert isinstance(emb, Embedder)
    assert (emb.model_id, emb.dim) == ("fake-embedder", 64)


def test_vecteurs_dim_norme_et_determinisme(ctx: _Ctx) -> None:
    emb = ctx.build("embedder", ComponentSpec(name="fake"))
    v = emb.embed_passages(TEXTES)
    assert v.shape == (3, 64) and v.dtype == np.float32
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-6)
    assert np.array_equal(v, emb.embed_passages(TEXTES))
    assert np.array_equal(v, emb.embed_queries(TEXTES))
    autre = ctx.build("embedder", ComponentSpec(name="fake"))
    assert np.array_equal(v, autre.embed_passages(TEXTES))


def test_proximite_lexicale(ctx: _Ctx) -> None:
    emb = ctx.build("embedder", ComponentSpec(name="fake"))
    a, b, c = emb.embed_passages(TEXTES)
    assert float(a @ b) > float(a @ c)
    assert float(a @ b) > float(b @ c)


def test_texte_vide_et_liste_vide(ctx: _Ctx) -> None:
    emb = ctx.build("embedder", ComponentSpec(name="fake"))
    v = emb.embed_queries(["", "   "])
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-6)
    assert emb.embed_passages([]).shape == (0, 64)


def test_chaque_appel_emet_un_span_embed(ctx: _Ctx, tmp_path: Path) -> None:
    emb = ctx.build("embedder", ComponentSpec(name="fake"))
    emb.embed_passages(TEXTES)
    emb.embed_queries(TEXTES[:1])
    lignes = (tmp_path / "traces.jsonl").read_text("utf-8").splitlines()
    spans = [json.loads(x) for x in lignes]
    assert len(spans) == 2
    assert all(s["name"] == "embed" for s in spans)
    attrs = spans
    assert all(a["wl.kind"] == "embed" and a["wl.cost"] == "0" for a in attrs)
    assert attrs[0]["gen_ai.usage.input_tokens"] == 8  # mots des trois textes
    assert attrs[1]["gen_ai.usage.input_tokens"] == 3
    assert attrs[0]["gen_ai.request.model"] == "fake-embedder"
