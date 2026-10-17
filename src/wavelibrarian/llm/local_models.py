"""Modèles locaux déjà présents sur la machine (cache Hugging Face), sans réseau ni dépendance."""

import os
from pathlib import Path

_POIDS = ("*.safetensors", "pytorch_model*.bin")
_TOKENIZER = ("tokenizer.json", "tokenizer_config.json")


def hf_cache_dir() -> Path:
    """Même règle que `huggingface_hub` : `HF_HUB_CACHE`, `HF_HOME/hub`, `XDG_CACHE_HOME`,
    sinon `~/.cache`."""
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    if os.environ.get("XDG_CACHE_HOME"):
        return Path(os.environ["XDG_CACHE_HOME"]) / "huggingface" / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _instantane_complet(snap: Path) -> bool:
    """Configuration, poids et tokenizer présents (un lien cassé ne compte pas)."""
    return (
        (snap / "config.json").is_file()
        and any(p.is_file() for motif in _POIDS for p in snap.glob(motif))
        and any((snap / nom).is_file() for nom in _TOKENIZER)
    )


def embedder_installe(hf_repo: str) -> bool:
    """Vrai si le dépôt `hf_repo` a un instantané complet dans le cache local.

    Un téléchargement interrompu (poids ou tokenizer absents) ne compte pas comme installé.
    """
    snapshots = hf_cache_dir() / ("models--" + hf_repo.replace("/", "--")) / "snapshots"
    try:
        return any(_instantane_complet(s) for s in snapshots.iterdir() if s.is_dir())
    except OSError:
        return False
