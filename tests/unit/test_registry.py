"""Registre de Composants et commande `wl registre` (story 1.3)."""

import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import BaseModel, ConfigDict, Field
from typer.testing import CliRunner

import wavelibrarian.architectures as paquet_architectures
import wavelibrarian.components as paquet_components
from wavelibrarian import registry
from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError


@pytest.fixture(autouse=True)
def registre_isole() -> Iterator[None]:
    sauve = dict(registry._REGISTRE)
    decouvert = registry._decouvert
    modules = set(sys.modules)
    yield
    registry._REGISTRE.clear()
    registry._REGISTRE.update(sauve)
    registry._decouvert = decouvert
    # Un module importé par `discover()` pendant le test est oublié, sinon il ne se
    # réenregistrerait plus après la restauration du registre.
    for nom in set(sys.modules) - modules:
        if nom.startswith(registry._PAQUETS_DECOUVERTS):
            del sys.modules[nom]


def _vide(nom: str) -> type:
    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

    return type(nom, (), {"Params": Params})


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
    registry.discover()
    toy = _toy()
    assert registry.get("chunker", "toy") is toy
    chunkers = registry.list_components(kind="chunker")
    assert "fixed_tokens" in {i.name for i in chunkers}
    [info] = [i for i in chunkers if i.name == "toy"]
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
    registry.register("chunker", "toy2")(_vide("Toy2"))
    registry.register("parser", "autre")(_vide("Autre"))
    with pytest.raises(ConfigError) as exc:
        registry.get("chunker", "inconnu")
    assert "toy, toy2" in str(exc.value)
    assert "autre" not in str(exc.value)


def test_params_exige_forbid_et_frozen() -> None:
    with pytest.raises(ConfigError):
        registry.register("chunker", "sans_params")(type("SansParams", (), {}))

    class Laxiste(BaseModel):
        size: int = 1

    with pytest.raises(ConfigError, match="forbid"):
        registry.register("chunker", "laxiste")(type("L", (), {"Params": Laxiste}))
    assert "laxiste" not in registry.names("chunker")


def test_description_non_heritee_et_defaut_calcule() -> None:
    class Base:
        """Docstring de la classe de base."""

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        a: int = 1
        b: int = Field(default_factory=lambda data: data["a"] + 1)

    registry.register("retriever", "herite")(type("Herite", (Base,), {"Params": Params}))
    [info] = [i for i in registry.list_components(kind="retriever") if i.name == "herite"]
    assert info.description == ""
    assert [(p.name, p.default) for p in info.params] == [("a", "1"), ("b", "calculé")]


@pytest.mark.parametrize("paquet", [paquet_components, paquet_architectures])
def test_discover_recursif_et_idempotent(
    paquet: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry.discover()  # les modules réels (dont les Architectures qui importent des Composants)
    sous = tmp_path / "sous"
    sous.mkdir()
    (sous / "__init__.py").write_text("")
    (sous / "module_decouvert.py").write_text(
        textwrap.dedent(
            """
            from wavelibrarian.registry import register

            from pydantic import BaseModel, ConfigDict, Field

            @register("reranker", "decouvert")
            class Decouvert:
                \"\"\"Trouvé par pkgutil.\"\"\"

                class Params(BaseModel):
                    model_config = ConfigDict(extra="forbid", frozen=True)
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(paquet, "__path__", [str(tmp_path)])
    monkeypatch.setattr(registry, "_decouvert", False)
    registry.discover()
    assert registry.get("reranker", "decouvert").__name__ == "Decouvert"
    registry.discover()  # sans effet, pas de doublon
    assert registry.names("reranker").count("decouvert") == 1  # le reranker réel `fake` coexiste


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
    assert "kind inconnu « nope »" in resultat.output
