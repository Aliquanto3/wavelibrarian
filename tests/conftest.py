"""Fixtures communes."""

from pathlib import Path

import pytest


@pytest.fixture
def wl_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Dossier d'état local isolé, exposé par la variable `WL_HOME`."""
    dossier = tmp_path / "wl_home"
    dossier.mkdir()
    monkeypatch.setenv("WL_HOME", str(dossier))
    return dossier
