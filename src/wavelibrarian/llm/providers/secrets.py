"""Lecture des clés d'API (AD-19) : `.env` puis environnement, gardées en `SecretStr`.

Seul `llm/providers/` lit les clés. Le fichier est lu par `python-dotenv` sans modifier
`os.environ`. Une clé ne sort jamais de son `SecretStr` : ni repr, ni message d'erreur, ni trace.
"""

import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import SecretStr


def load_secret(name: str, env_file: Path | str | None = None) -> SecretStr | None:
    """Valeur de `name` dans `env_file` (défaut `.env` du dossier courant), sinon `os.environ`.

    Une valeur vide compte pour absente.
    """
    chemin = Path(env_file) if env_file is not None else Path(".env")
    valeur: str | None = None
    if chemin.is_file():
        valeur = dotenv_values(chemin).get(name)
    if not valeur:
        valeur = os.environ.get(name)
    return SecretStr(valeur) if valeur else None
