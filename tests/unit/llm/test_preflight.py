"""Story 1.12 : préflight (Ollama, clé Anthropic, embedder en cache), sans réseau réel."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.llm.local_models import embedder_installe, hf_cache_dir
from wavelibrarian.llm.preflight import preflight

URL = "http://localhost:11434"
CPU = load_profile("cpu")
CATALOGUE = load_catalog()


def _client(tags: list[str] | None, requetes: list[Any] | None = None) -> httpx.Client:
    """Transport factice : `/api/tags` répond `tags`, ou refuse la connexion si `tags` est None."""

    def handler(requete: httpx.Request) -> httpx.Response:
        if requetes is not None:
            requetes.append(requete)
        if tags is None:
            raise httpx.ConnectError("refusé", request=requete)
        return httpx.Response(200, json={"models": [{"name": t} for t in tags]})

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def environnement_vide(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))


def _installer_embedder(tmp_path: Path, repo: str) -> None:
    snap = tmp_path / "hf" / ("models--" + repo.replace("/", "--")) / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")


def test_ollama_injoignable_nomme_l_url() -> None:
    res = preflight(["minicpm5:1b-q4_k_m"], CATALOGUE, CPU, http_client=_client(None))
    assert not res.ok
    assert len(res.errors) == 1
    assert URL in res.errors[0] and "injoignable" in res.errors[0]


def test_modele_ollama_absent_signale_par_son_nom() -> None:
    client = _client(["minicpm5:1b-q4_k_m"])
    res = preflight(["minicpm5:1b-q4_k_m", "granite4.2:3b"], CATALOGUE, CPU, http_client=client)
    assert len(res.errors) == 1
    assert "granite4.2:3b" in res.errors[0] and "minicpm5:1b" not in res.errors[0]


def test_tout_present_est_ok_et_une_seule_requete() -> None:
    requetes: list[Any] = []
    client = _client(["minicpm5:1b-q4_k_m", "granite4.2:3b"], requetes)
    res = preflight(["minicpm5:1b-q4_k_m", "granite4.2:3b"], CATALOGUE, CPU, http_client=client)
    assert res.ok and res.errors == ()
    assert [r.url.path for r in requetes] == ["/api/tags"]


def test_cle_anthropic_manquante(tmp_path: Path) -> None:
    res = preflight(["claude-haiku-5-5"], CATALOGUE, CPU, env_file=tmp_path / "absent.env")
    assert len(res.errors) == 1
    assert "ANTHROPIC_API_KEY" in res.errors[0] and "claude-haiku-5-5" in res.errors[0]


def test_cle_anthropic_presente_dans_l_environnement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-xyz")
    res = preflight(["claude-haiku-5-5"], CATALOGUE, CPU, env_file=tmp_path / "absent.env")
    assert res.ok
    assert "sk-ant-secret-xyz" not in repr(res)


def test_embedder_absent_du_cache_puis_present(tmp_path: Path) -> None:
    res = preflight(["multilingual-e5-small"], CATALOGUE, CPU)
    assert len(res.errors) == 1 and "multilingual-e5-small" in res.errors[0]
    assert not embedder_installe("intfloat/multilingual-e5-small")
    _installer_embedder(tmp_path, "intfloat/multilingual-e5-small")
    assert embedder_installe("intfloat/multilingual-e5-small")
    assert preflight(["multilingual-e5-small"], CATALOGUE, CPU).ok


def test_modeles_fake_sans_verification(tmp_path: Path) -> None:
    def interdit(requete: httpx.Request) -> httpx.Response:
        raise AssertionError("aucune requête pour un modèle fake")

    client = httpx.Client(transport=httpx.MockTransport(interdit))
    res = preflight(
        ["fake-llm-a", "fake-llm-b", "fake-embedder"],
        CATALOGUE,
        load_profile("test"),
        http_client=client,
        env_file=tmp_path / "absent.env",
    )
    assert res.ok


def test_erreurs_cumulees(tmp_path: Path) -> None:
    res = preflight(
        ["claude-haiku-5-5", "multilingual-e5-small", "granite4.2:3b"],
        CATALOGUE,
        CPU,
        http_client=_client(None),
        env_file=tmp_path / "absent.env",
    )
    assert len(res.errors) == 3


def test_cache_hf_variables(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HF_HUB_CACHE")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "home"))
    assert hf_cache_dir() == tmp_path / "home" / "hub"
