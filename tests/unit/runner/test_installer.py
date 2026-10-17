"""Story 1.12 : `wl installer` et préflight de `wl run`, accès extérieurs simulés."""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

import wavelibrarian.cli as cli
from wavelibrarian.cli import app
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.core.errors import WlError
from wavelibrarian.llm.preflight import PreflightResult
from wavelibrarian.runner import installer as inst

LISTE = """NAME                     ID            SIZE     MODIFIED
minicpm5:1b-q4_k_m       aaaaaaaa      1.0 GB   2 days ago
granite4.2:3b            bbbbbbbb      2.0 GB   2 days ago
"""


@pytest.fixture
def appels(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Remplace les trois accès extérieurs ; `ollama list` répond `LISTE` (modifiable)."""
    journal: dict[str, Any] = {"encodage": [], "embedder": [], "liste": LISTE}
    monkeypatch.setattr(inst, "telecharger_encodage", lambda n: journal["encodage"].append(n))
    monkeypatch.setattr(inst, "telecharger_embedder", lambda r: journal["embedder"].append(r))
    monkeypatch.setattr(inst, "ollama_list", lambda: journal["liste"])
    return journal


def test_profil_cpu(appels: dict[str, Any]) -> None:
    res = inst.installer("cpu")
    assert appels["encodage"] == ["o200k_base"]
    assert appels["embedder"] == ["intfloat/multilingual-e5-small"]
    assert res.ollama_manquants == ("minicpm5:2b-q4_k_m",)


def test_profil_gpu_vise_bge_m3_et_les_modeles_gpu(appels: dict[str, Any]) -> None:
    res = inst.installer("gpu")
    assert appels["embedder"] == ["BAAI/bge-m3"]
    catalogue = load_catalog()
    attendus = {m for m in load_profile("gpu").model_ids() if catalogue.get(m).provider == "ollama"}
    assert set(res.ollama_manquants) == attendus  # LISTE ne contient aucun modèle GPU
    assert "qwen3.5:4b" in attendus and "ministral-3:8b" in attendus


def test_ollama_list_tag_latest() -> None:
    assert inst._noms("NAME ID\nfoo:latest x\n") >= {"foo", "foo:latest"}


def test_profil_inconnu() -> None:
    with pytest.raises(WlError, match="profil"):
        inst.installer("test")


def test_cli_installer_modeles_manquants(appels: dict[str, Any]) -> None:
    res = CliRunner().invoke(app, ["installer", "--profil", "cpu"])
    assert res.exit_code == 4
    assert "o200k_base" in res.output and "multilingual-e5-small" in res.output
    assert "ollama pull minicpm5:2b-q4_k_m" in res.output


def test_cli_installer_tout_present(appels: dict[str, Any]) -> None:
    appels["liste"] = LISTE + "minicpm5:2b-q4_k_m  cccccccc  1 GB  now\n"
    res = CliRunner().invoke(app, ["installer", "--profil", "cpu"])
    assert res.exit_code == 0
    assert "tous présents" in res.output


def test_cli_installer_echec_telechargement(
    appels: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def echec(_repo: str) -> None:
        raise WlError("installer l'extra local")

    monkeypatch.setattr(inst, "telecharger_embedder", echec)
    res = CliRunner().invoke(app, ["installer", "--profil", "cpu"])
    assert res.exit_code == 1
    assert "installer l'extra local" in res.output


def test_telecharger_embedder_sans_extra_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    with pytest.raises(WlError, match="installer l'extra local"):
        inst.telecharger_embedder("intfloat/multilingual-e5-small")


def test_ollama_list_commande_introuvable(monkeypatch: pytest.MonkeyPatch) -> None:
    def introuvable(*_a: Any, **_k: Any) -> Any:
        raise FileNotFoundError("ollama")

    monkeypatch.setattr(inst.subprocess, "run", introuvable)
    with pytest.raises(WlError, match="ollama list"):
        inst.ollama_list()


def _resultat(modeles: list[str], profil: str = "cpu") -> Any:
    conf = SimpleNamespace(models=tuple(modeles))
    resolu = SimpleNamespace(
        configurations=(conf,),
        judges=SimpleNamespace(pool=None),
        profile_settings=load_profile(profil),
    )
    return SimpleNamespace(resolved=resolu, catalog=load_catalog())


def test_wl_run_preflight_en_echec_code_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "validate_file", lambda _c: _resultat(["claude-haiku-5-5"]))
    monkeypatch.setattr(
        cli, "preflight", lambda *_a, **_k: PreflightResult(("Ollama injoignable à http://x",))
    )
    res = CliRunner().invoke(app, ["run", str(tmp_path / "e.yaml")])
    assert res.exit_code == 4
    assert "Préflight échoué" in res.output and "injoignable" in res.output


def test_wl_run_cle_manquante_code_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # pas de `.env`
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "validate_file", lambda _c: _resultat(["claude-haiku-5-5"]))
    res = CliRunner().invoke(app, ["run", "e.yaml"])
    assert res.exit_code == 4
    assert "ANTHROPIC_API_KEY" in res.output


def test_wl_run_preflight_reussi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "validate_file", lambda _c: _resultat(["fake-llm-a"], "test"))
    res = CliRunner().invoke(app, ["run", str(tmp_path / "e.yaml")])
    assert res.exit_code == 0
    assert "Préflight réussi" in res.output
