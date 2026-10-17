"""Story 3.2 : `RunContext` concret (scope, build, rng, verrou), profil `test` et Faux LLM."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian.config.defaults import load_profile
from wavelibrarian.config.experiment import (
    Amount,
    Budget,
    ResolvedConfiguration,
    ResolvedExperiment,
    RetrySettings,
)
from wavelibrarian.core.errors import ConfigError, WlError
from wavelibrarian.ports.components import ComponentSpec, Embedder
from wavelibrarian.ports.context import RunContext
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.ports.measure import Tokenizer
from wavelibrarian.runner.context import Context


@pytest.fixture
def ctx(wl_home: Path) -> Iterator[Context]:
    with Context.from_profile("test", wl_home=wl_home, run_id="run-a", seed=42) as c:
        yield c


def _req() -> LLMRequest:
    return LLMRequest(
        model_id="fake-llm-a",
        role="generate",
        step="generate",
        system="Réponds.",
        messages=(Message(role="user", content="Quelle est la capitale ?"),),
        max_tokens=100,
        inputs={"question": "q", "blocks": {}},
    )


def _spans(ctx: Context) -> list[dict[str, Any]]:
    chemin = ctx.run_dir / "traces.jsonl"
    return [json.loads(x) for x in chemin.read_text(encoding="utf-8").splitlines()]


# --- AC 1 : attributs et Protocol ----------------------------------------------------------


def test_expose_les_attributs_et_satisfait_le_protocol(ctx: Context) -> None:
    contexte: RunContext = ctx  # vérifié par pyright
    assert contexte.profile.profile == "test"
    assert contexte.seed == 42 and contexte.run_id == "run-a"
    assert (contexte.condition, contexte.tier, contexte.phase) == ("standard", None, "base")
    assert contexte.catalog.get("fake-llm-a").provider == "fake"
    tok: Tokenizer = contexte.tokenizer
    assert tok.count("un deux trois") > 0
    assert contexte.tokenizer_for("fake-llm-a").count("un deux") > 0
    assert contexte.gateway.complete(_req()).text
    assert contexte.tracer is not None


def test_passerelle_mesuree_avec_le_provider_du_catalogue(ctx: Context) -> None:
    ctx.gateway.complete(_req())
    (span,) = _spans(ctx)
    assert span["gen_ai.request.model"] == "fake-llm-a"
    assert span["gen_ai.provider.name"] == "fake"
    assert span["wl.run_id"] == "run-a"


def test_contexte_d_experience_reprend_graine_plafonds_et_parser(wl_home: Path) -> None:
    experience = ResolvedExperiment.model_construct(
        seed=7,
        profile_settings=load_profile("test"),
        catalog=None,
        budget=Budget(per_run={"anthropic": Amount(amount="1.00", currency="USD")}),  # pyright: ignore[reportArgumentType]
        retries=RetrySettings(),
        configurations=(
            ResolvedConfiguration(
                id="cfg-1",
                architecture="x",
                parser=ComponentSpec(name="markdown"),
                reuse_index=None,
                params={},
                models=(),
                answer_producers=(),
            ),
        ),
    )
    with Context.from_experiment(experience, wl_home=wl_home, run_id="run-e") as c:
        assert (c.seed, c.config_id, c.parser) == (7, "cfg-1", "markdown")
        assert (wl_home / "run.lock").exists()
        with pytest.raises(ValueError):
            Context.from_experiment(experience, wl_home=wl_home, run_id="r", config_id="zzz")


# --- AC 2 : scope ----------------------------------------------------------------------------


def test_scope_pose_les_valeurs_dans_le_span_puis_les_restaure(ctx: Context) -> None:
    avant = (ctx.post, ctx.question_id)
    with ctx.scope(post="evalset", question_id="q-001"):
        assert (ctx.post, ctx.question_id) == ("evalset", "q-001")
        ctx.gateway.complete(_req())
        with ctx.scope(post="judging"):  # imbriqué : question_id conservé
            assert (ctx.post, ctx.question_id) == ("judging", "q-001")
        assert (ctx.post, ctx.question_id) == ("evalset", "q-001")
    assert (ctx.post, ctx.question_id) == avant
    (span,) = _spans(ctx)
    assert span["wl.post"] == "evalset" and span["wl.question_id"] == "q-001"


def test_scope_restaure_meme_sur_exception(ctx: Context) -> None:
    with pytest.raises(RuntimeError), ctx.scope(post="judging", question_id="q-2"):
        raise RuntimeError("boum")
    assert ctx.question_id is None and ctx.post == "query"


def test_post_et_question_id_en_lecture_seule(ctx: Context) -> None:
    with pytest.raises(AttributeError):
        ctx.post = "evalset"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        ctx.question_id = "q"  # type: ignore[misc]


# --- AC 3 : build ----------------------------------------------------------------------------


def test_build_construit_par_cls_params_ctx(ctx: Context) -> None:
    emb = ctx.build("embedder", ComponentSpec(name="fake"))
    assert isinstance(emb, Embedder)
    assert emb.dim == ctx.catalog.get(emb.model_id).dim


def test_build_refuse_un_parametre_inconnu(ctx: Context) -> None:
    with pytest.raises(ConfigError) as exc:
        ctx.build("embedder", ComponentSpec(name="fake", params={"inconnu": 1}))
    assert "inconnu" in str(exc.value)


def test_build_refuse_un_composant_inconnu(ctx: Context) -> None:
    with pytest.raises(ConfigError):
        ctx.build("embedder", ComponentSpec(name="nexiste-pas"))


# --- AC 4 : rng ------------------------------------------------------------------------------


def test_rng_meme_graine_meme_suite_autre_graine_autre_suite(wl_home: Path) -> None:
    def tirage(seed: int) -> list[float]:
        with Context.from_profile("test", wl_home=wl_home, run_id=f"r{seed}", seed=seed) as c:
            r = c.rng("split", "factual")
            return [r.random() for _ in range(10)]

    assert tirage(1) == tirage(1)
    assert tirage(1) != tirage(2)


def test_rng_depend_des_cles(ctx: Context) -> None:
    assert ctx.rng("a").random() != ctx.rng("b").random()
    assert ctx.rng("a", "b").random() == ctx.rng("a", "b").random()


# --- AC 5 : run.lock -------------------------------------------------------------------------


def test_second_contexte_d_execution_echoue(wl_home: Path) -> None:
    with Context.from_profile("test", wl_home=wl_home, run_id="hors"):  # sans verrou
        assert not (wl_home / "run.lock").exists()
    prem = Context(
        profile=load_profile("test"), catalog=_catalogue(), wl_home=wl_home, run_id="run-1",
        execution=True,
    )  # fmt: skip
    try:
        with pytest.raises(WlError, match="Exécution run-1 en cours"):
            Context(
                profile=load_profile("test"), catalog=_catalogue(), wl_home=wl_home,
                run_id="run-2", execution=True,
            )  # fmt: skip
        # une commande hors Exécution ne prend pas le verrou et n'est pas gênée
        with Context.from_profile("test", wl_home=wl_home, run_id="hors-2") as c:
            assert c.gateway.complete(_req()).text
    finally:
        prem.close()
    # verrou libéré : une nouvelle Exécution peut démarrer
    with Context(
        profile=load_profile("test"), catalog=_catalogue(), wl_home=wl_home, run_id="run-3",
        execution=True,
    ):  # fmt: skip
        pass


def _catalogue() -> Any:
    from wavelibrarian.config.catalog import load_catalog

    return load_catalog()
