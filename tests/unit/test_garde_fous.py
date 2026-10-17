"""Garde-fous du socle : réseau interdit, marqueurs, CLI, fixture wl_home, couches."""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_socket import SocketBlockedError
from typer.testing import CliRunner

from wavelibrarian.cli import app

RACINE = Path(__file__).resolve().parents[2]


def test_socket_tcp_bloque() -> None:
    with pytest.raises(SocketBlockedError):
        socket.create_connection(("127.0.0.1", 9))


@pytest.mark.real_api
def test_real_api_deselectionne() -> None:
    raise AssertionError("ne doit jamais être exécuté par défaut")


@pytest.mark.real_local
def test_real_local_deselectionne() -> None:
    raise AssertionError("ne doit jamais être exécuté par défaut")


def test_aide_cli_en_francais() -> None:
    resultat = CliRunner().invoke(app, ["--help"])
    assert resultat.exit_code == 0
    assert "banc de comparaison" in resultat.output


def test_wl_home(wl_home: Path) -> None:
    assert os.environ["WL_HOME"] == str(wl_home)
    assert wl_home.is_dir()


def test_gitignore() -> None:
    lignes = (RACINE / ".gitignore").read_text(encoding="utf-8").splitlines()
    for entree in (".wl/", "results/", ".env"):
        assert entree in lignes


def test_lint_imports_passe() -> None:
    resultat = subprocess.run(
        [sys.executable, "-m", "importlinter.cli"], cwd=RACINE, capture_output=True, text=True
    )
    assert resultat.returncode == 0, resultat.stdout[-1500:]
