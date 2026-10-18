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


# `python -m importlinter.cli` n'a pas de garde `__main__` : il sortirait 0 sans rien vérifier.
LINT_IMPORTS = [
    sys.executable,
    "-c",
    "from importlinter.cli import lint_imports_command; lint_imports_command()",
]


def _lint_imports(dossier: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        LINT_IMPORTS, cwd=dossier, capture_output=True, text=True, encoding="utf-8", env=env
    )


def test_lint_imports_passe() -> None:
    resultat = _lint_imports(RACINE)
    assert resultat.returncode == 0, resultat.stdout[-1500:]
    assert "Contracts: 5 kept, 0 broken." in resultat.stdout


def test_lint_imports_detecte_une_rupture(tmp_path: Path) -> None:
    paquet = tmp_path / "paquet_test"
    (paquet / "bas").mkdir(parents=True)
    (paquet / "__init__.py").write_text("")
    (paquet / "haut.py").write_text("")
    (paquet / "bas" / "__init__.py").write_text("from paquet_test import haut\n")
    (tmp_path / ".importlinter").write_text(
        "[importlinter]\nroot_package = paquet_test\n\n"
        "[importlinter:contract:couches]\nname = Couches\ntype = layers\n"
        "layers =\n    paquet_test.haut\n    paquet_test.bas\n"
    )
    resultat = _lint_imports(tmp_path)
    assert resultat.returncode != 0
    assert "BROKEN" in resultat.stdout


def test_real_local_et_real_api_autorisent_les_sockets(request: pytest.FixtureRequest) -> None:
    """Le hook de `conftest.py` pose `enable_socket` sur les tests réels, pas sur les autres."""
    from conftest import pytest_collection_modifyitems

    class Item:
        def __init__(self, marque: str | None) -> None:
            self.marque, self.ajoutes = marque, []

        def get_closest_marker(self, nom: str) -> object | None:
            return object() if nom == self.marque else None

        def add_marker(self, marque: object) -> None:
            self.ajoutes.append(marque)

    items = [Item("real_local"), Item("real_api"), Item(None)]
    pytest_collection_modifyitems(items)  # type: ignore[arg-type]
    assert [len(i.ajoutes) for i in items] == [1, 1, 0]
