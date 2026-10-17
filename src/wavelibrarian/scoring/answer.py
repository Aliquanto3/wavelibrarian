"""Forme des Réponses de référence (FR-36) et correspondance exacte normalisée."""

import re
import unicodedata

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


_NOMBRE_GROUPE = re.compile(r"(?<![\d.,])\d{1,3}(?:[ '  ]\d{3})+(?!\d)")
_DECIMAL = re.compile(r"(?<=\d),(?=\d)")
_JETON = re.compile(r"\d+(?:\.\d+)?|[^\W\d_]+")


def _jeton_nombre(j: str) -> str:
    entier, _, decimale = j.partition(".")
    entier = entier.lstrip("0") or "0"
    decimale = decimale.rstrip("0")
    return f"{entier}.{decimale}" if decimale else entier


def _jetons(texte: str) -> list[str]:
    t = unicodedata.normalize("NFKD", texte.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = _NOMBRE_GROUPE.sub(lambda m: re.sub(r"\D", "", m[0]), t)
    t = _DECIMAL.sub(".", t)
    return [_jeton_nombre(j) if j[0].isdigit() else j for j in _JETON.findall(t)]


def exact_match(reference: str, answer: str) -> bool:
    """Vrai si la référence figure, mot pour mot, dans la réponse après normalisation.

    Normalisation : casse, accents, ponctuation, format des nombres (« 1 412 » = « 1412 »,
    « 3,5 » = « 3.5 »). Un nombre ne correspond qu'à lui-même : « 1413 » ne répond pas à « 1412 ».
    """
    ref, rep = _jetons(reference), _jetons(answer)
    if not ref or len(ref) > len(rep):
        return False
    n = len(ref)
    return any(rep[i : i + n] == ref for i in range(len(rep) - n + 1))
