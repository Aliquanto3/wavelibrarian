"""Forme des Réponses de référence (FR-36) : `short` = au plus 5 mots, un nombre ou une date."""

import re

MAX_MOTS_COURTE = 5

_NOMBRE = re.compile(r"^[-+]?\d[\d\s.,'  ]*\s?(%|[^\W\d_]{1,4}\.?)?$")
_DATE_NUMERIQUE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}([ T]\d{1,2}:\d{2}(:\d{2})?Z?)?$")


def is_short_form(texte: str) -> bool:
    """Vrai si `texte` tient dans la forme `short` : au plus 5 mots, ou un nombre, ou une date."""
    t = texte.strip()
    if not t:
        return False
    if len(t.split()) <= MAX_MOTS_COURTE:
        return True
    return bool(_NOMBRE.match(t) or _DATE_NUMERIQUE.match(t))
