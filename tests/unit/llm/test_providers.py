"""Story 1.11 : providers Anthropic et Ollama sur transports HTTP factices (aucun réseau).

Les tests `real_api` et `real_local` en fin de fichier appellent de vrais services : ils sont
désélectionnés par défaut (`addopts`) et ne sont jamais lancés par le run autonome.
"""

import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import httpx2
import pytest
from pydantic import BaseModel, SecretStr

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.config.experiment import Budget, RetrySettings
from wavelibrarian.core.errors import ProviderError, WlError
from wavelibrarian.core.types import Condition, CostPost, Phase
from wavelibrarian.llm.budget import Ledger
from wavelibrarian.llm.cache import ResponseCache
from wavelibrarian.llm.gateway import MeteredGateway
from wavelibrarian.llm.providers import anthropic as ant_mod
from wavelibrarian.llm.providers.anthropic import AnthropicProvider
from wavelibrarian.llm.providers.logs import limiter_journaux
from wavelibrarian.llm.providers.ollama import OllamaProvider
from wavelibrarian.llm.providers.secrets import load_secret
from wavelibrarian.measure import energy
from wavelibrarian.measure.energy import FakeEstimator
from wavelibrarian.measure.tokenizers import ApproxTokenizer, ScaledTokenizer
from wavelibrarian.measure.tracing import Tracer
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.ports.measure import Tokenizer

CLE = "sk-ant-api03-CLE-DE-TEST-0123456789"
HAIKU = "claude-haiku-5-5"
MINICPM = "minicpm5:1b-q4_k_m"

REPONSE_ANTHROPIC: dict[str, Any] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": HAIKU,
    "content": [{"type": "text", "text": "Bonjour"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {
        "input_tokens": 12,
        "output_tokens": 5,
        "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 40,
    },
}


class Sortie(BaseModel):
    reponse: str


def _req(model: str = HAIKU, **kw: Any) -> LLMRequest:
    base: dict[str, Any] = {
        "model_id": model,
        "role": "generate",
        "step": "generate",
        "system": "Réponds en français.",
        "messages": (Message(role="user", content="Quelle est la capitale ?"),),
        "max_tokens": 100,
        "inputs": {"question": "q", "blocks": {}},
    }
    return LLMRequest(**{**base, **kw})


@dataclass
class Resp:
    status: int
    json: Any = None
    text: str = ""


@dataclass
class Exc:
    kind: str  # nom d'une exception de la bibliothèque HTTP (ReadTimeout, ConnectError...)
    msg: str = "x"


class Transport:
    """Transport factice (`MockTransport`) : garde les requêtes reçues, rejoue le script.

    Le SDK Anthropic 1.15 s'appuie sur `httpx2`, le provider Ollama sur `httpx` : `client(lib)`
    construit le client de la bibliothèque voulue.
    """

    def __init__(self, *script: Resp | Exc) -> None:
        self.script = list(script)
        self.requests: list[Any] = []

    def client(self, lib: Any) -> Any:
        def handler(request: Any) -> Any:
            self.requests.append(request)
            item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
            if isinstance(item, Exc):
                raise getattr(lib, item.kind)(item.msg, request=request)
            if item.json is not None:
                return lib.Response(item.status, json=item.json)
            return lib.Response(item.status, text=item.text)

        return lib.Client(transport=lib.MockTransport(handler))

    def body(self, i: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[i].content)


def _ok(corps: dict[str, Any] | None = None) -> Resp:
    return Resp(200, json=corps or REPONSE_ANTHROPIC)


def _erreur(code: int, type_: str = "api_error") -> Resp:
    return Resp(code, json={"type": "error", "error": {"type": type_, "message": "refusé"}})


def _anthropic(transport: Transport) -> AnthropicProvider:
    return AnthropicProvider(SecretStr(CLE), http_client=transport.client(httpx2))


# --- Anthropic : requête native et usage ------------------------------------------------------


def test_anthropic_cache_control_temperature_et_modele() -> None:
    t = Transport(_ok())
    msgs = (
        Message(role="user", content="contexte long", cache=True),
        Message(role="assistant", content="ok"),
        Message(role="user", content="question"),
    )
    rep = _anthropic(t).complete(_req(cache_system=True, messages=msgs), timeout_s=30)
    corps = t.body()
    assert corps["model"] == HAIKU and corps["temperature"] == 0 and corps["max_tokens"] == 100
    assert corps["system"] == [
        {"type": "text", "text": "Réponds en français.", "cache_control": {"type": "ephemeral"}}
    ]
    assert corps["messages"][0]["content"] == [
        {"type": "text", "text": "contexte long", "cache_control": {"type": "ephemeral"}}
    ]
    assert corps["messages"][1]["content"] == "ok"  # sans `cache` : aucun cache_control
    assert "cache_control" not in json.dumps(corps["messages"][1:])
    assert rep.text == "Bonjour"
    u = rep.usage
    assert (u.input_tokens, u.output_tokens) == (12, 5)
    assert (u.cache_read_tokens, u.cache_write_tokens) == (100, 40)
    assert t.requests[0].url.path == "/v1/messages"


def test_anthropic_sans_cache_ni_schema_n_envoie_ni_cache_ni_outil() -> None:
    t = Transport(_ok())
    _anthropic(t).complete(_req(), timeout_s=30)
    corps = t.body()
    assert corps["system"] == "Réponds en français."
    assert "cache_control" not in json.dumps(corps) and "tools" not in corps


def test_anthropic_cache_system_avec_system_vide_n_envoie_pas_de_bloc_vide() -> None:
    corps = AnthropicProvider.native_request(_req(system="", cache_system=True), None)
    assert "system" not in corps


def test_anthropic_usage_sans_champs_de_cache() -> None:
    corps = {**REPONSE_ANTHROPIC, "usage": {"input_tokens": 3, "output_tokens": 1}}
    rep = _anthropic(Transport(_ok(corps))).complete(_req(), timeout_s=30)
    assert (rep.usage.cache_read_tokens, rep.usage.cache_write_tokens) == (0, 0)


def test_anthropic_sortie_structuree_par_outil_impose() -> None:
    bloc = {"type": "tool_use", "id": "tu_1", "name": "emit_output", "input": {"reponse": "Paris"}}
    t = Transport(_ok({**REPONSE_ANTHROPIC, "content": [bloc], "stop_reason": "tool_use"}))
    schema = Sortie.model_json_schema()
    rep = _anthropic(t).complete(_req(), timeout_s=30, output_schema=schema)
    corps = t.body()
    assert corps["tools"][0]["input_schema"] == schema
    assert corps["tool_choice"] == {"type": "tool", "name": "emit_output"}
    assert Sortie.model_validate_json(rep.text).reponse == "Paris"


def test_anthropic_sortie_structuree_sans_outil_dans_la_reponse() -> None:
    with pytest.raises(ProviderError, match="aucune sortie d'outil"):
        _anthropic(Transport(_ok())).complete(
            _req(), timeout_s=30, output_schema=Sortie.model_json_schema()
        )


def test_anthropic_delai_applique_et_pas_d_essai_du_sdk() -> None:
    t = Transport(_erreur(529, "overloaded_error"))
    with pytest.raises(ProviderError):
        _anthropic(t).complete(_req(), timeout_s=7.0)
    assert len(t.requests) == 1  # max_retries=0 : les essais sont ceux de la passerelle
    assert t.requests[0].extensions["timeout"]["read"] == 7.0


# --- Anthropic : erreurs ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "retryable"),
    [(429, True), (529, True), (500, True), (400, False), (401, False), (404, False)],
)
def test_anthropic_erreurs_http(code: int, retryable: bool) -> None:
    with pytest.raises(ProviderError) as exc:
        _anthropic(Transport(_erreur(code))).complete(_req(), timeout_s=30)
    assert exc.value.retryable is retryable and not exc.value.sent
    assert str(code) in str(exc.value) and CLE not in str(exc.value)


def test_anthropic_delai_apres_envoi_et_connexion() -> None:
    with pytest.raises(ProviderError) as exc:
        _anthropic(Transport(Exc("ReadTimeout", "lent"))).complete(_req(), timeout_s=1)
    # Parti sans réponse : réglé à l'estimation, jamais relancé (peut-être déjà facturé).
    assert not exc.value.retryable and exc.value.sent
    with pytest.raises(ProviderError) as exc:
        _anthropic(Transport(Exc("ConnectError", "non"))).complete(_req(), timeout_s=1)
    assert exc.value.retryable and not exc.value.sent


def test_anthropic_sans_cle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # pas de `.env`
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY absente") as exc:
        AnthropicProvider().complete(_req(), timeout_s=1)
    assert not exc.value.retryable


# --- Anthropic : énergie EcoLogits ------------------------------------------------------------


class _Reponse(anthropic.types.Message):
    """Réponse du SDK telle que la rend `EcoLogits.init` : un `Message` avec `impacts`."""

    impacts: Any = None


def _avec_impacts(impacts: Any) -> anthropic.Anthropic:
    corps = {**REPONSE_ANTHROPIC, "impacts": impacts}
    msg = _Reponse.model_validate(corps)
    client = anthropic.Anthropic(api_key=CLE, http_client=Transport(_ok()).client(httpx2))
    client.messages.create = lambda **_: msg  # type: ignore[method-assign,assignment]
    return client


def test_energie_estimee_quand_les_impacts_existent() -> None:
    impacts = SimpleNamespace(energy=SimpleNamespace(value=0.002))
    rep = AnthropicProvider(client=_avec_impacts(impacts)).complete(_req(), timeout_s=1)
    assert rep.energy_kwh == 0.002
    fourchette = SimpleNamespace(energy=SimpleNamespace(value=SimpleNamespace(min=1.0, max=3.0)))
    assert ant_mod._energie_kwh(SimpleNamespace(impacts=fourchette)) == 2.0


@pytest.mark.parametrize(
    "reponse",
    [
        SimpleNamespace(),  # extra `energy` absent : le SDK n'est pas patché
        SimpleNamespace(impacts=None),
        SimpleNamespace(impacts=SimpleNamespace(energy=None, errors=["modèle inconnu"])),
        SimpleNamespace(impacts=SimpleNamespace(energy=SimpleNamespace(value=None))),
    ],
)
def test_energie_inconnue_sans_erreur(reponse: Any) -> None:
    assert ant_mod._energie_kwh(reponse) is None


def test_reponse_sdk_ordinaire_sans_impacts() -> None:
    rep = _anthropic(Transport(_ok())).complete(_req(), timeout_s=1)
    assert rep.energy_kwh is None


def test_init_ecologits(monkeypatch: pytest.MonkeyPatch) -> None:
    appels: list[dict[str, Any]] = []
    faux = SimpleNamespace(EcoLogits=SimpleNamespace(init=lambda **kw: appels.append(kw)))
    monkeypatch.setattr(energy, "_ecologits_initialise", False)
    monkeypatch.setitem(sys.modules, "ecologits", faux)
    energy.init_ecologits()
    energy.init_ecologits()  # une seule fois par processus
    assert appels == [{"providers": ["anthropic"], "electricity_mix_zone": None}]
    monkeypatch.setattr(energy, "_ecologits_initialise", False)
    monkeypatch.setitem(sys.modules, "ecologits", None)
    with pytest.raises(WlError, match="extra energy"):
        energy.init_ecologits()


# --- Secrets et journaux ----------------------------------------------------------------------


def test_cle_lue_dans_le_env_en_secretstr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={CLE}\n", encoding="utf-8")
    cle = load_secret("ANTHROPIC_API_KEY", env)
    assert isinstance(cle, SecretStr) and cle.get_secret_value() == CLE
    assert CLE not in repr(cle) and CLE not in str(cle)
    assert "ANTHROPIC_API_KEY" not in os.environ  # le fichier ne pollue pas l'environnement
    assert load_secret("AUTRE", env) is None


def test_cle_de_repli_dans_l_environnement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "depuis-l-env")
    cle = load_secret("ANTHROPIC_API_KEY", tmp_path / "absent.env")
    assert cle is not None and cle.get_secret_value() == "depuis-l-env"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert load_secret("ANTHROPIC_API_KEY", tmp_path / "absent.env") is None


class _Ctx:
    run_id = "run-1"
    config_id = "cfg-1"
    condition: Condition = "standard"
    tier: int | None = None
    phase: Phase = "base"
    post: CostPost = "query"
    question_id: str | None = "q-1"


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def passerelle(wl_home: Path, tmp_path: Path) -> Iterator[Callable[..., tuple[Any, Path]]]:
    fermer: list[Callable[[], None]] = []

    def fabrique(providers: dict[str, Any], **kw: Any) -> tuple[MeteredGateway, Path]:
        catalog = load_catalog()
        ledger = Ledger(Budget(per_run={}, period={}), "run-1", wl_home)
        cache = ResponseCache(wl_home)
        fermer.extend([ledger.close, cache.close])
        chemin = tmp_path / "traces.jsonl"
        ref = ApproxTokenizer()

        def tokenizer_for(model_id: str) -> Tokenizer:
            e = catalog.get(model_id)
            return ref if e.tokenizer == "reference" else ScaledTokenizer(ref, e.token_factor)

        gw = MeteredGateway(
            catalog=catalog,
            providers=providers,
            ledger=ledger,
            cache=cache,
            tracer=Tracer(_Ctx(), chemin),
            tokenizer_for=tokenizer_for,
            estimator=FakeEstimator(),
            retries=RetrySettings(max_attempts=2, backoff_s=0.0, max_backoff_s=0.0),
            sleep=lambda _: None,
            **kw,
        )
        return gw, chemin

    yield fabrique
    for f in fermer:
        f()


def test_la_cle_ne_fuit_ni_dans_les_traces_ni_dans_les_journaux(
    passerelle: Callable[..., tuple[Any, Path]],
) -> None:
    racine = logging.getLogger()
    capture = _Capture()
    avant = racine.level
    racine.addHandler(capture)
    racine.setLevel(logging.DEBUG)
    limiter_journaux(capture)
    try:
        t = Transport(_ok(), _erreur(400, "invalid_request_error"))
        gw, traces = passerelle({"anthropic": _anthropic(t)})
        gw.complete(_req())  # appel réussi
        with pytest.raises(ProviderError):  # puis appel en erreur
            gw.complete(_req(pass_id=1))
    finally:
        racine.removeHandler(capture)
        racine.setLevel(avant)
    assert t.requests[0].headers["x-api-key"] == CLE  # la clé part bien, vers le seul transport
    texte = traces.read_text(encoding="utf-8")
    journaux = "\n".join(r.getMessage() + repr(r.args) for r in capture.records)
    for lieu in (texte, journaux):
        assert CLE not in lieu and "x-api-key" not in lieu.lower()
    assert [
        r
        for r in capture.records
        if r.name.split(".")[0] in ("anthropic", "httpx", "httpcore", "httpx2", "httpcore2")
        and r.levelno < logging.WARNING
    ] == []
    assert len(texte.splitlines()) == 2  # un span par appel, succès puis erreur


_RESEAU = ("anthropic", "httpx", "httpcore", "httpx2", "httpcore2")

_SCRIPT_ANTHROPIC_LOG = """
import io, logging, sys
import httpx2
from pydantic import SecretStr
from wavelibrarian.llm.providers.anthropic import AnthropicProvider  # SDK importé ici
from wavelibrarian.llm.providers.logs import limiter_journaux
from wavelibrarian.ports.gateway import LLMRequest, Message

assert logging.getLogger("anthropic").level == logging.DEBUG  # ANTHROPIC_LOG lu à l'import
assert logging.getLogger("httpx2").level == logging.DEBUG
flux = io.StringIO()
capture = logging.StreamHandler(flux)
racine = logging.getLogger()
racine.addHandler(capture)
racine.setLevel(logging.DEBUG)
limiter_journaux(capture)
ok = {"id": "m", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
      "content": [{"type": "text", "text": "oui"}], "stop_reason": "end_turn",
      "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}
erreur = {"type": "error", "error": {"type": "invalid_request_error", "message": "non"}}
reponses = [httpx2.Response(200, json=ok), httpx2.Response(400, json=erreur)]
client = httpx2.Client(transport=httpx2.MockTransport(lambda r: reponses.pop(0)))
provider = AnthropicProvider(SecretStr(sys.argv[1]), http_client=client)
req = LLMRequest(model_id="claude-haiku-5-5", role="generate", step="generate", system="s",
                 messages=(Message(role="user", content="q"),), max_tokens=8)
provider.complete(req, timeout_s=5)
try:
    provider.complete(req, timeout_s=5)
except Exception as exc:
    print(type(exc).__name__)
logging.getLogger("wavelibrarian").debug("temoin-debug")
print(flux.getvalue())
"""


def test_anthropic_log_debug_pose_avant_l_import_sans_fuite(tmp_path: Path) -> None:
    """`ANTHROPIC_LOG=debug` est lu à l'import du SDK : sous-processus où il est posé avant."""
    env = {**os.environ, "ANTHROPIC_LOG": "debug", "PYTHONIOENCODING": "utf-8"}
    env.pop("ANTHROPIC_API_KEY", None)
    script = tmp_path / "script.py"
    script.write_text(_SCRIPT_ANTHROPIC_LOG, encoding="utf-8")
    fini = subprocess.run(
        [sys.executable, str(script), CLE],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
    )  # fmt: skip
    assert fini.returncode == 0, fini.stderr[-2000:]
    sortie = fini.stdout + fini.stderr  # stderr : gestionnaire posé par le SDK (`basicConfig`)
    assert "ProviderError" in sortie and "temoin-debug" in sortie  # appel en erreur, DEBUG actif
    assert CLE not in sortie and "x-api-key" not in sortie.lower()


def test_les_loggers_reseau_sont_forces_a_warning() -> None:
    for nom in _RESEAU:
        logging.getLogger(nom).setLevel(logging.DEBUG)
    limiter_journaux()
    assert all(logging.getLogger(n).level == logging.WARNING for n in _RESEAU)
    # Le filtre du gestionnaire tient même si un niveau est relevé après coup.
    capture = _Capture()
    limiter_journaux(capture)
    limiter_journaux(capture)  # idempotent
    assert len(capture.filters) == 1
    debug = logging.LogRecord("httpx", logging.DEBUG, "f", 1, "x-api-key", None, None)
    alerte = logging.LogRecord("httpcore.http11", logging.WARNING, "f", 1, "panne", None, None)
    autre = logging.LogRecord("wavelibrarian", logging.DEBUG, "f", 1, "ok", None, None)
    assert [bool(capture.filter(r)) for r in (debug, alerte, autre)] == [False, True, True]


# --- Ollama -----------------------------------------------------------------------------------

REPONSE_OLLAMA = {
    "model": MINICPM,
    "message": {"role": "assistant", "content": '{"reponse": "Paris"}'},
    "done": True,
    "prompt_eval_count": 31,
    "eval_count": 9,
}


def _ollama(transport: Transport, profil: str = "cpu") -> OllamaProvider:
    return OllamaProvider(load_profile(profil).ollama, http_client=transport.client(httpx))


def test_ollama_corps_du_profil_cpu_avec_schema() -> None:
    t = Transport(Resp(200, json=REPONSE_OLLAMA))
    schema = Sortie.model_json_schema()
    rep = _ollama(t).complete(_req(MINICPM, seed=7), timeout_s=120, output_schema=schema)
    corps = t.body()
    assert t.requests[0].method == "POST" and t.requests[0].url.path == "/api/chat"
    assert corps["options"]["num_gpu"] == 0 and corps["options"]["seed"] == 7
    assert corps["options"]["temperature"] == 0 and corps["options"]["num_predict"] == 100
    assert corps["keep_alive"] == load_profile("cpu").ollama.keep_alive
    assert corps["format"] == schema and corps["stream"] is False and corps["model"] == MINICPM
    assert [m["role"] for m in corps["messages"]] == ["system", "user"]
    assert (rep.usage.input_tokens, rep.usage.output_tokens) == (31, 9)
    assert Sortie.model_validate_json(rep.text).reponse == "Paris"


def test_ollama_num_ctx_du_catalogue_sauf_si_le_profil_le_fixe() -> None:
    t = Transport(Resp(200, json=REPONSE_OLLAMA))
    profil = load_profile("cpu").ollama
    p = OllamaProvider(profil, context_windows={MINICPM: 32768}, http_client=t.client(httpx))
    assert p.native_request(_req(MINICPM), None)["options"]["num_ctx"] == 32768
    assert "num_ctx" not in p.native_request(_req("autre:1b"), None)["options"]
    fixe = profil.model_copy(update={"options": {**profil.options, "num_ctx": 8192}})
    p2 = OllamaProvider(fixe, context_windows={MINICPM: 32768}, http_client=t.client(httpx))
    assert p2.native_request(_req(MINICPM), None)["options"]["num_ctx"] == 8192


def test_ollama_fenetre_remplie_journalisee(caplog: pytest.LogCaptureFixture) -> None:
    plein = {**REPONSE_OLLAMA, "prompt_eval_count": 4000, "eval_count": 96}
    t = Transport(Resp(200, json=plein), Resp(200, json=REPONSE_OLLAMA))
    p = OllamaProvider(
        load_profile("cpu").ollama, context_windows={MINICPM: 4096}, http_client=t.client(httpx)
    )
    with caplog.at_level(logging.WARNING, logger="wavelibrarian.llm.providers.ollama"):
        p.complete(_req(MINICPM), timeout_s=5)
        assert any("tronqué" in r.getMessage() for r in caplog.records)
        caplog.clear()
        p.complete(_req(MINICPM), timeout_s=5)
        assert caplog.records == []


def test_ollama_sans_schema_ni_graine() -> None:
    t = Transport(Resp(200, json=REPONSE_OLLAMA))
    _ollama(t).complete(_req(MINICPM), timeout_s=120)
    corps = t.body()
    assert "format" not in corps and "seed" not in corps["options"]


def test_ollama_delai_du_profil_applique_par_la_passerelle(
    passerelle: Callable[..., tuple[Any, Path]],
) -> None:
    profil = load_profile("cpu")
    t = Transport(Resp(200, json=REPONSE_OLLAMA))
    gw, _ = passerelle({"ollama": _ollama(t)}, default_timeout_s=profil.defaults.call_timeout_s)
    res = gw.complete(_req(MINICPM))
    assert t.requests[0].extensions["timeout"]["read"] == profil.defaults.call_timeout_s == 120
    assert res.usage.input_tokens == 31 and res.cost == Decimal(0)


@pytest.mark.parametrize(
    ("reponse", "retryable"),
    [
        (Resp(500, text="boum"), True),
        (Resp(503, text="charge"), True),
        (Resp(404, json={"error": "model not found"}), False),
        (Resp(400, json={"error": "mauvaise option"}), False),
        (Resp(200, text="pas du json"), False),
        (Resp(200, json={"done": True}), False),
    ],
)
def test_ollama_erreurs(reponse: Resp, retryable: bool) -> None:
    with pytest.raises(ProviderError) as exc:
        _ollama(Transport(reponse)).complete(_req(MINICPM), timeout_s=5)
    assert exc.value.retryable is retryable and not exc.value.sent


def test_ollama_delai_apres_envoi_et_injoignable() -> None:
    with pytest.raises(ProviderError) as exc:
        _ollama(Transport(Exc("ReadTimeout", "lent"))).complete(_req(MINICPM), timeout_s=5)
    assert exc.value.sent and not exc.value.retryable
    with pytest.raises(ProviderError) as exc:
        _ollama(Transport(Exc("ConnectError", "refusé"))).complete(_req(MINICPM), timeout_s=5)
    assert exc.value.retryable and not exc.value.sent


def test_delai_ollama_apres_envoi_regle_a_l_estimation_par_la_passerelle(
    passerelle: Callable[..., tuple[Any, Path]],
) -> None:
    gw, traces = passerelle({"ollama": _ollama(Transport(Exc("ReadTimeout", "x")))})
    with pytest.raises(ProviderError):
        gw.complete(_req(MINICPM))
    (span,) = [json.loads(x) for x in traces.read_text(encoding="utf-8").splitlines()]
    assert span["wl.status"] == "error"


# --- Tests réels : écrits, jamais exécutés par le run autonome ----------------------------------


@pytest.mark.real_local
def test_real_local_num_gpu_accepte_par_api_chat() -> None:  # pragma: no cover
    """Ollama local et `minicpm5:1b-q4_k_m` présents : un appel au profil `cpu` réussit."""
    profil = load_profile("cpu")
    try:
        tags = httpx.get(profil.ollama.base_url + "/api/tags", timeout=3).json()
    except httpx.HTTPError:
        pytest.skip("Ollama injoignable")
    if MINICPM not in {m.get("name") for m in tags.get("models", [])}:
        pytest.skip(f"modèle {MINICPM} absent")
    rep = OllamaProvider(profil.ollama).complete(
        _req(MINICPM, max_tokens=8, seed=1, messages=(Message(role="user", content="Dis oui."),)),
        timeout_s=profil.defaults.call_timeout_s,
    )
    assert rep.usage.output_tokens > 0


@pytest.mark.real_api
def test_real_api_anthropic_haiku() -> None:  # pragma: no cover
    """Un appel Haiku 5.5 minimal (clé `ANTHROPIC_API_KEY` requise, sinon saut)."""
    if load_secret("ANTHROPIC_API_KEY") is None:
        pytest.skip("ANTHROPIC_API_KEY absente")
    rep = AnthropicProvider().complete(
        _req(max_tokens=16, messages=(Message(role="user", content="Dis oui."),)), timeout_s=30
    )
    assert rep.text and rep.usage.output_tokens > 0
