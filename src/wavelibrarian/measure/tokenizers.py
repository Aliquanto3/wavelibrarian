"""Tokenizers (contracts.md §2.2) : `approx` sans dépendance, `reference` = tiktoken."""

import hashlib
import math
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from wavelibrarian.config.catalog import ModelCatalog
from wavelibrarian.core.errors import WlError
from wavelibrarian.ports.measure import Tokenizer

_ENCODAGE = "o200k_base"
_URL_ENCODAGE = "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
# SHA-256 attendu par tiktoken (`tiktoken_ext/openai_public.py`) : un fichier qui ne le
# vérifie pas serait supprimé puis retéléchargé par tiktoken, d'où le contrôle préalable.
_SHA256_ENCODAGE = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"


class ApproxTokenizer:
    """Un token par mot (séparé par des blancs) : déterministe, sans réseau (profil `test`)."""

    name = "approx"

    def count(self, text: str) -> int:
        return len(text.split())


def _dossier_cache_tiktoken() -> Path | None:
    """Même règle que tiktoken : `TIKTOKEN_CACHE_DIR`, `DATA_GYM_CACHE_DIR`, sinon le temporaire.

    Une variable définie mais vide désactive le cache chez tiktoken (lecture réseau) : `None`.
    """
    for var in ("TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR"):
        if var in os.environ:
            valeur = os.environ[var]
            return Path(valeur) if valeur else None
    return Path(tempfile.gettempdir()) / "data-gym-cache"


def encodage_installe() -> bool:
    """Vrai si l'encodage de référence est en cache local et intègre (aucun accès réseau).

    Intègre = SHA-256 attendu par tiktoken, qui lit alors le cache sans jamais télécharger.
    """
    dossier = _dossier_cache_tiktoken()
    if dossier is None:
        return False
    chemin = dossier / hashlib.sha1(_URL_ENCODAGE.encode()).hexdigest()  # nom choisi par tiktoken
    try:
        return hashlib.sha256(chemin.read_bytes()).hexdigest() == _SHA256_ENCODAGE
    except OSError:
        return False


class ReferenceTokenizer:
    """tiktoken `o200k_base`, chargé au premier usage ; jamais de téléchargement."""

    name = "reference"

    def __init__(self) -> None:
        self._enc: Any = None

    def count(self, text: str) -> int:
        if self._enc is None:
            self._enc = self._charger()
        return len(self._enc.encode(text, disallowed_special=()))

    @staticmethod
    def _charger() -> Any:
        message = (
            f"encodage tiktoken `{_ENCODAGE}` absent du cache local : "
            "lancer `wl installer` pour le préparer (aucun téléchargement automatique)"
        )
        if not encodage_installe():
            raise WlError(message)
        try:
            import tiktoken

            return tiktoken.get_encoding(_ENCODAGE)
        except Exception as exc:  # cache illisible, réseau tenté puis refusé, etc.
            raise WlError(message) from exc


class ScaledTokenizer:
    """Tokenizer de base majoré de `token_factor` (estimation pour un autre tokenizer)."""

    def __init__(self, base: Tokenizer, factor: Decimal) -> None:
        self._base = base
        self.factor = factor
        self.name = f"{base.name}x{factor.normalize():f}"

    def count(self, text: str) -> int:
        return math.ceil(Decimal(self._base.count(text)) * self.factor)


def make_tokenizer(name: str) -> Tokenizer:
    """Tokenizer de profil : `approx` ou `reference`."""
    if name == "approx":
        return ApproxTokenizer()
    if name == "reference":
        return ReferenceTokenizer()
    raise WlError(f"tokenizer inconnu : {name!r} (attendu : approx, reference)")


def tokenizer_for(model_id: str, catalog: ModelCatalog, reference: Tokenizer) -> Tokenizer:
    """Tokenizer d'un modèle : `reference` au Catalogue = tokenizer de référence tel quel,
    sinon tokenizer de référence du profil × `token_factor` du modèle (défaut 1,2)."""
    entry = catalog.get(model_id)
    if entry.tokenizer == "reference":
        return reference
    return ScaledTokenizer(reference, entry.token_factor)
