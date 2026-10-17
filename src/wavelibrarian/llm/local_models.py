"""Modèles locaux déjà présents sur la machine (cache Hugging Face), sans réseau ni dépendance."""

import os
from pathlib import Path


def hf_cache_dir() -> Path:
    """Même règle que `huggingface_hub` : `HF_HUB_CACHE`, `HF_HOME/hub`, sinon `~/.cache`."""
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def embedder_installe(hf_repo: str) -> bool:
    """Vrai si le dépôt Hugging Face `hf_repo` a au moins un instantané dans le cache local."""
    snapshots = hf_cache_dir() / ("models--" + hf_repo.replace("/", "--")) / "snapshots"
    try:
        return any(any(s.iterdir()) for s in snapshots.iterdir() if s.is_dir())
    except OSError:
        return False
