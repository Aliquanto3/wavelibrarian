"""Registre de Composants et commande `wl registre` (story 1.3)."""

import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict
from typer.testing import CliRunner

import wavelibrarian.components as paquet_components
from wavelibrarian import registry
from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError


@pytest.fixture(autouse=True)
def registre_isole() -> Iterator[None]:
    sauve = dict(registry._REGISTRE)
    decouvert = registry._decouvert
    yield
    registry._REGISTRE.clear()
    registry._REGISTRE.update(sauve)
    registry._decouvert = decouvert


def _toy() -> type:
    @registry.register("chunker", "toy")
    class Toy:
        """Découpeur jouet."""

        class Params(BaseModel):
            model_config = ConfigDict(extra="forbid", frozen=True)
            size: int = 300
            nom: str = "x"

    return Toy


def test_get_et_list_components() -> None:
    toy = _toy()
    assert registry.get("chunker", "toy") is toy
    [info] = registry.list_components(kind="chunker")
    assert (info.name, info.kind, info.description) == ("toy", "chunker", "Découpeur jouet.")
    assert [(p.name, p.type, p.default) for p in info.params] == [
        ("size", "int", "300"),
        ("nom", "str", "'x'"),
    ]


def test_kind_inconnu_et_doublon() -> None:
    with pytest.raises(ConfigError):
        registry.register("inexistant", "x")
    _toy()
    with pytest.raises(ConfigError):
        _toy()


def test_nom_inconnu_liste_le_meme_kind() -> None:
    _toy()
    registry.register("chunker", "toy2")(type("Toy2", (), {}))
    registry.register("parser", "autre")(type("Autre", (), {}))
    with pytest.raises(ConfigError) as exc:
        registry.get("chunker", "inconnu")
    assert "toy, toy2" in str(exc.value)
    assert "autre" not in str(exc.value)


def test_discover_recursif_et_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sous = tmp_path / "sous"
    sous.mkdir()
    (sous / "__init__.py").write_text("")
    (sous / "module_decouvert.py").write_text(
        textwrap.dedent(
            """
            from wavelibrarian.registry import register

            @register("reranker", "decouvert")
            class Decouvert:
                \"\"\"Trouvé par pkgutil.\"\"\"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(paquet_components, "__path__", [str(tmp_path)])
    monkeypatch.setattr(registry, "_decouvert", False)
    for nom in ("sous", "sous.module_decouvert"):
        monkeypatch.delitem(sys.modules, f"wavelibrarian.components.{nom}", raising=False)
    registry.discover()
    assert registry.get("reranker", "decouvert").__name__ == "Decouvert"
    registry.discover()  # sans effet, pas de doublon
    assert registry.names("reranker") == ["decouvert"]


def test_cli_registre() -> None:
    _toy()
    runner = CliRunner()
    tout = runner.invoke(app, ["registre"])
    assert tout.exit_code == 0
    assert "chunker / toy : Découpeur jouet." in tout.output
    assert "size (int), défaut : 300" in tout.output
    filtre = runner.invoke(app, ["registre", "--kind", "chunker"])
    assert filtre.exit_code == 0 and "toy" in filtre.output
    autre = runner.invoke(app, ["registre", "--kind", "parser"])
    assert autre.exit_code == 0 and "toy" not in autre.output


def test_cli_kind_invalide() -> None:
    resultat = CliRunner().invoke(app, ["registre", "--kind", "nope"])
    assert resultat.exit_code == 2
