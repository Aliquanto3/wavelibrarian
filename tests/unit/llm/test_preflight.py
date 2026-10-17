"""Story 1.12 : préflight (Ollama, clé Anthropic, embedder en cache), sans réseau réel."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.core.errors import ProviderError
from wavelibrarian.llm.local_models import embedder_installe, hf_cache_dir
from wavelibrarian.llm.preflight import preflight
from wavelibrarian.llm.providers.ollama import list_models

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


def _installer_embedder(
    tmp_path: Path,
    repo: str,
    fichiers: tuple[str, ...] = (
        "config.json",
        "model.safetensors",
        "tokenizer.json",
        "modules.json",
    ),
) -> None:
    snap = tmp_path / "hf" / ("models--" + repo.replace("/", "--")) / "snapshots" / "abc"
    snap.mkdir(parents=True, exist_ok=True)
    for nom in fichiers:
        (snap / nom).write_text("{}", encoding="utf-8")


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


def test_cache_hf_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HF_HUB_CACHE")
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert hf_cache_dir() == tmp_path / "xdg" / "huggingface" / "hub"


def test_instantane_incomplet_n_est_pas_installe(tmp_path: Path) -> None:
    """Téléchargement interrompu : config sans poids, puis poids sans tokenizer."""
    repo = "intfloat/multilingual-e5-small"
    _installer_embedder(tmp_path, repo, ("config.json", "modules.json"))
    assert not embedder_installe(repo)
    assert not preflight(["multilingual-e5-small"], CATALOGUE, CPU).ok
    _installer_embedder(tmp_path, repo, ("model.safetensors",))
    assert not embedder_installe(repo)
    _installer_embedder(tmp_path, repo, ("tokenizer_config.json",))
    assert embedder_installe(repo)


@pytest.mark.parametrize(
    "reponse",
    [
        httpx.Response(200, json={"models": None}),
        httpx.Response(200, json=["x"]),
        httpx.Response(200, text="pas du json"),
        httpx.Response(500),
    ],
)
def test_list_models_reponse_de_travers(reponse: httpx.Response) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _r: reponse))
    if reponse.status_code == 200 and reponse.content == b'{"models":null}':
        assert list_models(URL, http_client=client) == set()
        return
    with pytest.raises(ProviderError, match="Ollama ne répond pas"):
        list_models(URL, http_client=client)


def test_list_models_url_invalide() -> None:
    with pytest.raises(ProviderError):
        list_models("http://[::1", http_client=_client([]))


def test_list_models_ferme_son_client(monkeypatch: pytest.MonkeyPatch) -> None:
    fermes: list[bool] = []
    vrai_client = httpx.Client

    class Client(vrai_client):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__(transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})))

        def close(self) -> None:
            fermes.append(True)
            super().close()

    monkeypatch.setattr("wavelibrarian.llm.providers.ollama.httpx.Client", Client)
    assert list_models(URL) == set()
    assert fermes == [True]
