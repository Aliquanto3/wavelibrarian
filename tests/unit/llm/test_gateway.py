"""Story 1.9 : passerelle mesurée (provider factice, aucun réseau, aucun GPU)."""

import json
from collections.abc import Callable, Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from wavelibrarian.config.catalog import ModelCatalog, load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.config.experiment import Amount, Budget, RetrySettings
from wavelibrarian.core.errors import BudgetExceeded, NonConformantOutput, ProviderError, WlError
from wavelibrarian.core.types import Condition, CostPost, Phase, Usage
from wavelibrarian.llm.budget import Ledger
from wavelibrarian.llm.cache import ResponseCache
from wavelibrarian.llm.gateway import MeteredGateway
from wavelibrarian.llm.providers.base import ProviderResponse
from wavelibrarian.measure.energy import FakeEstimator
from wavelibrarian.measure.tokenizers import ApproxTokenizer, ScaledTokenizer
from wavelibrarian.measure.tracing import Tracer
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.ports.measure import Tokenizer
from wavelibrarian.runner.wiring import build_gateway

D = Decimal
USAGE = Usage(input_tokens=1000, output_tokens=500)
COUT = D("0.002")  # fake-llm : 1,00 $/Mtok en entrée, 2,00 $/Mtok en sortie


class _Ctx:
    run_id = "run-1"
    config_id = "cfg-1"
    condition: Condition = "standard"
    tier: int | None = None
    phase: Phase = "base"
    post: CostPost = "query"
    question_id: str | None = "q-1"


class FauxProvider:
    """Renvoie, à chaque appel, le prochain élément de `script` (texte ou exception)."""

    def __init__(self, *script: str | Exception, usage: Usage = USAGE) -> None:
        self.script = list(script) or ["bonjour"]
        self.usage = usage
        self.requests: list[LLMRequest] = []
        self.timeouts: list[float] = []

    def complete(self, request: LLMRequest, *, timeout_s: float) -> ProviderResponse:
        self.requests.append(request)
        self.timeouts.append(timeout_s)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return ProviderResponse(text=item, usage=self.usage)


class Env:
    def __init__(self, wl_home: Path, tmp: Path, budget: Budget, provider: FauxProvider) -> None:
        self.catalog: ModelCatalog = load_catalog()
        self.ledger = Ledger(budget, "run-1", wl_home)
        self.cache = ResponseCache(wl_home)
        self.path = tmp / "traces.jsonl"
        self.tracer = Tracer(_Ctx(), self.path)
        self.provider = provider
        self.sleeps: list[float] = []
        self.reserved: list[Decimal] = []
        reserve = self.ledger.reserve

        def espion(p: str, amount: Decimal, currency: str) -> int:
            self.reserved.append(amount)
            return reserve(p, amount, currency)

        self.ledger.reserve = espion  # type: ignore[method-assign]
        ref = ApproxTokenizer()

        def tokenizer_for(model_id: str) -> Tokenizer:
            entry = self.catalog.get(model_id)
            return (
                ref if entry.tokenizer == "reference" else ScaledTokenizer(ref, entry.token_factor)
            )

        self.gw = MeteredGateway(
            catalog=self.catalog,
            providers={"fake": provider, "anthropic": provider, "ollama": provider},
            ledger=self.ledger,
            cache=self.cache,
            tracer=self.tracer,
            tokenizer_for=tokenizer_for,
            estimator=FakeEstimator(),
            retries=RetrySettings(max_attempts=3, backoff_s=1.0, max_backoff_s=30.0),
            sleep=self.sleeps.append,
        )

    def spans(self) -> list[dict[str, Any]]:
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]


def _budget(per_run: str | None = None) -> Budget:
    if per_run is None:
        return Budget(per_run={}, period={})
    return Budget(per_run={"fake": Amount(amount=D(per_run), currency="USD")}, period={})


@pytest.fixture
def make_env(wl_home: Path, tmp_path: Path) -> Iterator[Callable[..., Env]]:
    envs: list[Env] = []

    def fabrique(*script: str | Exception, budget: Budget | None = None, **kw: Any) -> Env:
        env = Env(wl_home, tmp_path, budget or _budget(), FauxProvider(*script, **kw))
        envs.append(env)
        return env

    yield fabrique
    for e in envs:
        e.ledger.close()
        e.cache.close()


def _req(model: str = "fake-llm-a", **kw: Any) -> LLMRequest:
    base: dict[str, Any] = {
        "model_id": model,
        "role": "generate",
        "step": "generate",
        "system": "Réponds.",
        "messages": (Message(role="user", content="Quelle est la capitale ?"),),
        "max_tokens": 100,
    }
    return LLMRequest(**{**base, **kw})


class Schema(BaseModel):
    reponse: str


# --- Marqueur, cache, coût -------------------------------------------------------------------


def test_deux_appels_identiques(make_env: Callable[..., Env]) -> None:
    env = make_env("Paris")
    r1 = env.gw.complete(_req())
    r2 = env.gw.complete(_req())
    assert env.provider.requests[0].system.startswith("[[wl:role=generate]]\n")
    assert len(env.provider.requests) == 1  # le second est servi par le cache
    assert (r1.cost, r1.cost_uncached, r1.from_cache, r1.currency) == (COUT, COUT, False, "USD")
    assert isinstance(r1.cost, Decimal)
    assert (r2.cost, r2.cost_uncached, r2.from_cache, r2.text) == (D(0), COUT, True, "Paris")
    assert len(env.reserved) == 1  # pas de réservation pour le hit
    s1, s2 = env.spans()
    assert s1["wl.llm_cache_hit"] is False and s1["wl.cost"] == "0.002"
    assert s1["wl.status"] == "ok"
    assert s2["wl.llm_cache_hit"] is True and s2["wl.cost"] == "0"
    assert s2["wl.cost_uncached"] == "0.002"
    assert s1["gen_ai.provider.name"] == "fake" and s1["wl.step"] == "generate"


def test_composant_qui_pose_le_marqueur_est_refuse(make_env: Callable[..., Env]) -> None:
    env = make_env()
    with pytest.raises(WlError, match="passerelle seule"):
        env.gw.complete(_req(system="[[wl:role=judge]]\nx"))
    assert env.provider.requests == []


def test_le_role_entre_dans_la_cle(make_env: Callable[..., Env]) -> None:
    env = make_env()
    env.gw.complete(_req())
    env.gw.complete(_req(role="judge"))
    assert len(env.provider.requests) == 2


def test_energie_estimee_par_appel(make_env: Callable[..., Env]) -> None:
    env = make_env()
    env.gw.complete(_req())
    env.gw.complete(_req())
    s1, s2 = env.spans()
    assert s1["wl.energy_method"] == "estimated"
    assert s1["wl.energy_kwh"] == pytest.approx(1500 * 1e-7)
    assert "wl.energy_method" not in s2  # un hit ne consomme rien


def test_modele_local_cout_nul_et_energie_inconnue(make_env: Callable[..., Env]) -> None:
    env = make_env("ok")
    r = env.gw.complete(_req("qwen3.5:4b"))
    assert (r.cost, r.cost_uncached, r.currency) == (D(0), D(0), "EUR")
    (s,) = env.spans()
    assert s["wl.energy_method"] == "unknown" and "wl.energy_kwh" not in s


def test_seuls_les_succes_sont_mis_en_cache(make_env: Callable[..., Env]) -> None:
    env = make_env(ProviderError("panne", retryable=False), "ok")
    with pytest.raises(ProviderError):
        env.gw.complete(_req())
    assert env.gw.complete(_req()).from_cache is False
    assert len(env.provider.requests) == 2


# --- Plafond ----------------------------------------------------------------------------------


def test_budget_refuse_sans_appel(make_env: Callable[..., Env]) -> None:
    env = make_env(budget=_budget("0.0001"))
    with pytest.raises(BudgetExceeded):
        env.gw.complete(_req(max_tokens=1000))  # 1000 tokens de sortie = 0,002 $
    assert env.provider.requests == []
    (s,) = env.spans()
    assert s["wl.status"] == "budget_refused" and s["wl.cost"] == "0"


def test_estimation_applique_token_factor(make_env: Callable[..., Env]) -> None:
    env = make_env("ok")
    # Haiku déclare `reference` : la passerelle applique le facteur 1,5.
    # "[[wl:role=generate]]" + "a b c" + 6 mots = 10 mots -> 15 tokens.
    msg = (Message(role="user", content="d e f g h i"),)
    env.gw.complete(_req("claude-haiku-5-5", system="a b c", messages=msg, max_tokens=7))
    attendu = env.catalog.cost("claude-haiku-5-5", Usage(input_tokens=15, output_tokens=7))
    assert env.reserved == [attendu]


def test_estimation_palier_tarifaire(make_env: Callable[..., Env]) -> None:
    env = make_env("ok")
    # 70 001 mots x 1,5 = 105 002 tokens > 100 000 : multiplicateur 5 sur toute l'estimation.
    msg = (Message(role="user", content="mot " * 70_000),)
    env.gw.complete(_req("claude-haiku-5-5", system="", messages=msg, max_tokens=0))
    assert env.reserved == [D(105_002) * D("0.10") / D(1_000_000) * 5]


def test_prompt_cacheable_estime_au_tarif_d_ecriture(make_env: Callable[..., Env]) -> None:
    env = make_env("ok")
    env.gw.complete(_req(system="a b c", cache_system=True, messages=(), max_tokens=0))
    # 2 mots (marqueur, 3 mots -> "a b c" = 4 mots) x 1,2 = 5 tokens (arrondi supérieur).
    assert env.reserved == [D(5) * D("1.25") / D(1_000_000)]


# --- Essais -----------------------------------------------------------------------------------


def test_deux_erreurs_retryables_puis_succes(make_env: Callable[..., Env]) -> None:
    env = make_env(ProviderError("a", retryable=True), ProviderError("b", retryable=True), "ok")
    r = env.gw.complete(_req())
    assert r.text == "ok" and len(env.provider.requests) == 3
    assert env.sleeps == [1.0, 2.0]  # attente exponentielle, horloge injectée
    assert env.provider.timeouts == [30.0] * 3
    assert len(env.reserved) == 1  # une seule réservation pour les trois essais


def test_erreur_non_retryable_libere_la_reservation(make_env: Callable[..., Env]) -> None:
    env = make_env(ProviderError("fatal", retryable=False), budget=_budget("1.00"))
    with pytest.raises(ProviderError):
        env.gw.complete(_req())
    assert len(env.provider.requests) == 1 and env.sleeps == []
    assert env.ledger.balance("fake").run_remaining == D("1.00")
    (s,) = env.spans()
    assert s["wl.status"] == "error"


def test_essais_epuises(make_env: Callable[..., Env]) -> None:
    env = make_env(ProviderError("x", retryable=True), budget=_budget("1.00"))
    with pytest.raises(ProviderError):
        env.gw.complete(_req())
    assert len(env.provider.requests) == 3 and env.sleeps == [1.0, 2.0]
    assert env.ledger.balance("fake").run_remaining == D("1.00")


def test_reglement_au_cout_reel(make_env: Callable[..., Env]) -> None:
    env = make_env(budget=_budget("1.00"))
    env.gw.complete(_req())
    assert env.ledger.balance("fake").run_remaining == D("1.00") - COUT


def test_delai_de_la_requete_prime(make_env: Callable[..., Env]) -> None:
    env = make_env()
    env.gw.complete(_req(timeout_s=5.0))
    assert env.provider.timeouts == [5.0]


# --- Sortie structurée ------------------------------------------------------------------------


def test_sortie_non_conforme_deux_fois(make_env: Callable[..., Env]) -> None:
    env = make_env("pas du json")
    with pytest.raises(NonConformantOutput):
        env.gw.complete_structured(_req(), Schema)
    assert len(env.provider.requests) == 2  # réessayé une fois
    assert [s["wl.status"] for s in env.spans()] == ["non_conformant"] * 2
    # La sortie invalide n'a pas été mise en cache.
    assert env.gw.complete(_req()).from_cache is False


def test_sortie_conforme_au_second_essai(make_env: Callable[..., Env]) -> None:
    env = make_env("n'importe quoi", '{"reponse": "Paris"}')
    valeur, res = env.gw.complete_structured(_req(), Schema)
    assert valeur == Schema(reponse="Paris") and res.text == '{"reponse": "Paris"}'
    assert [s["wl.status"] for s in env.spans()] == ["non_conformant", "ok"]
    valeur2, res2 = env.gw.complete_structured(_req(), Schema)
    assert valeur2 == valeur and res2.from_cache and len(env.provider.requests) == 2


def test_sortie_invalide_en_cache_est_contournee_au_second_essai(
    make_env: Callable[..., Env],
) -> None:
    env = make_env("invalide", '{"reponse": "ok"}')
    env.gw.complete(_req())  # met "invalide" en cache (complete ne valide pas)
    valeur, res = env.gw.complete_structured(_req(), Schema)
    assert valeur.reponse == "ok" and not res.from_cache


# --- Câblage ----------------------------------------------------------------------------------


def test_build_gateway_depuis_le_profil_test(wl_home: Path, tmp_path: Path) -> None:
    provider = FauxProvider("salut")
    ledger = Ledger(_budget(), "run-1", wl_home)
    cache = ResponseCache(wl_home)
    trace = tmp_path / "t.jsonl"
    gw = build_gateway(
        catalog=load_catalog(),
        profile=load_profile("test"),
        providers={"fake": provider},
        ledger=ledger,
        cache=cache,
        tracer=Tracer(_Ctx(), trace),
    )
    assert gw.complete(_req()).cost == COUT
    assert provider.timeouts == [30.0]  # call_timeout_s du profil
    (s,) = [json.loads(x) for x in trace.read_text(encoding="utf-8").splitlines()]
    assert s["wl.energy_method"] == "estimated"
    ledger.close()
    cache.close()
