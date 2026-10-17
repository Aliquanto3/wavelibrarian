"""`wl installer` (AD-16) : prépare les modèles locaux d'un profil, seule voie de téléchargement.

Encodage tiktoken `o200k_base` et embedder du profil, puis comparaison de `ollama list` aux
modèles Ollama du profil (jamais de `ollama pull` automatique). Les trois accès au monde
extérieur sont des fonctions de module, remplacées par des doubles en test.
"""

import subprocess
from dataclasses import dataclass

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.core.errors import ProviderError, WlError

ENCODAGE = "o200k_base"


@dataclass(frozen=True)
class InstallResult:
    profil: str
    encodage: str
    embedder: str  # dépôt Hugging Face
    ollama_manquants: tuple[str, ...]


def telecharger_encodage(nom: str) -> None:
    """Demande l'encodage à tiktoken, qui le télécharge et vérifie son empreinte."""
    try:
        import tiktoken

        tiktoken.get_encoding(nom)
    except Exception as exc:
        raise WlError(f"encodage tiktoken {nom} non téléchargé ({type(exc).__name__})") from exc


def telecharger_embedder(hf_repo: str) -> None:
    """Télécharge le dépôt Hugging Face dans le cache local (extra `local` requis)."""
    try:
        from huggingface_hub import snapshot_download  # pyright: ignore[reportMissingImports]
    except ImportError:
        raise WlError("installer l'extra local") from None
    try:
        snapshot_download(hf_repo)
    except Exception as exc:
        raise WlError(f"embedder {hf_repo} non téléchargé ({type(exc).__name__})") from exc


def ollama_list() -> str:
    """Sortie de `ollama list` ; `ProviderError` (Ollama injoignable, code 4) si la commande
    est introuvable ou échoue."""
    try:
        res = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderError(f"`ollama list` impossible ({type(exc).__name__})") from exc
    if res.returncode != 0:
        raise ProviderError("`ollama list` a échoué : Ollama est-il démarré ?")
    return res.stdout


def _noms(sortie: str) -> set[str]:
    noms: set[str] = set()
    for ligne in sortie.splitlines()[1:]:  # la première ligne est l'en-tête (NAME ID SIZE ...)
        if ligne.split():
            nom = ligne.split()[0]
            noms.add(nom)
            noms.add(nom.removesuffix(":latest"))
    return noms


def installer(profil: str) -> InstallResult:
    """Prépare le profil `cpu` ou `gpu` ; renvoie les modèles Ollama encore à tirer."""
    if profil not in ("cpu", "gpu"):
        raise WlError(f"profil à installer inconnu : {profil!r} (attendu : cpu, gpu)")
    reglages = load_profile(profil)
    catalogue = load_catalog()
    embedder = catalogue.get(reglages.defaults.embedder)
    if not embedder.hf_repo:
        raise WlError(f"embedder {embedder.id} sans dépôt Hugging Face dans le Catalogue")
    telecharger_encodage(ENCODAGE)
    telecharger_embedder(embedder.hf_repo)
    attendus = sorted(m for m in reglages.model_ids() if catalogue.get(m).provider == "ollama")
    presents = _noms(ollama_list())
    manquants = tuple(m for m in attendus if m not in presents)
    return InstallResult(profil, ENCODAGE, embedder.hf_repo, manquants)
