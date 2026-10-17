"""Fixtures communes."""

from pathlib import Path

import pytest

from wavelibrarian.core.types import ParsedCorpus
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest

CORPUS_MINICORPUS = (
    Path(__file__).resolve().parent.parent / "corpora" / "minicorpus" / "corpus.yaml"
)


@pytest.fixture
def wl_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Dossier d'état local isolé, exposé par la variable `WL_HOME`."""
    dossier = tmp_path / "wl_home"
    dossier.mkdir()
    monkeypatch.setenv("WL_HOME", str(dossier))
    return dossier


@pytest.fixture(scope="session")
def minicorpus(tmp_path_factory: pytest.TempPathFactory) -> ParsedCorpus:
    """Mini-corpus fictif ingéré (profil `test`, Parsers `auto`), mis en cache pour la session."""
    wl_home = tmp_path_factory.mktemp("wl_home_minicorpus")
    return ingest(declare(CORPUS_MINICORPUS), wl_home=wl_home)
