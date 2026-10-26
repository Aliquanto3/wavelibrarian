"""Forme des Réponses de référence (FR-36) et correspondance exacte normalisée."""

import re
import unicodedata
from collections.abc import Collection

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


# Milliers : espace (fine, insécable, apostrophe) dès un groupe ; point ou virgule à partir de
# deux groupes de même séparateur (« 1.412.000 », « 1,412,000 »). Sinon la virgule est décimale.
_NOMBRE_GROUPE = re.compile(r"(?<![\w.,])\d{1,3}(?:(?:[ '  ]\d{3})+|([.,])\d{3}(?:\1\d{3})+)(?!\d)")
_DECIMAL = re.compile(r"(?<=\d),(?=\d)")
_MOINS = re.compile("[−–]")  # signe moins et tiret de plage
# Un jeton est une suite alphanumérique entière (« A1412 », « 5e » ne valent pas « 1412 », « 5 ») ;
# une plage « 1412-1413 » reste un seul jeton ; le signe moins tient au nombre qui le suit.
_JETON = re.compile(
    r"(?<![\w-])-?\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)+(?![\w-])"  # plage, date à tirets
    r"|(?:(?<![\w-])-)?\d+(?:\.\d+)?(?![^\W_])"  # nombre, signé ou non
    r"|[^\W_]+"  # mot, ou chiffres collés à des lettres
)
_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae"})


def _jeton_nombre(j: str) -> str:
    signe, j = ("-", j[1:]) if j.startswith("-") else ("", j)
    entier, _, decimale = j.partition(".")
    entier = entier.lstrip("0") or "0"
    decimale = decimale.rstrip("0")
    valeur = f"{entier}.{decimale}" if decimale else entier
    return f"{signe}{valeur}" if valeur != "0" else valeur


def _normalise(j: str) -> str:
    if re.fullmatch(r"-?\d+(?:\.\d+)?", j):
        return _jeton_nombre(j)
    if re.fullmatch(r"-?\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)+", j):  # plage ou date à tirets
        tete, reste = (j[0], j[1:]) if j.startswith("-") else ("", j)
        return tete + "-".join(_jeton_nombre(x) for x in reste.split("-"))
    return j


def _jetons(texte: str) -> list[str]:
    t = unicodedata.normalize("NFKD", texte.casefold().translate(_LIGATURES))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = _MOINS.sub("-", t)
    t = _NOMBRE_GROUPE.sub(lambda m: re.sub(r"\D", "", m[0]), t)
    t = _DECIMAL.sub(".", t)
    return [_normalise(j) for j in _JETON.findall(t)]


def exact_match(reference: str, answer: str) -> bool:
    """Vrai si la référence figure, mot pour mot, dans la réponse après normalisation.

    Normalisation : casse, accents, ponctuation, format des nombres (« 1 412 » = « 1412 »,
    « 3,5 » = « 3.5 »). Un nombre ne correspond qu'à lui-même : « 1413 » ne répond pas à « 1412 »,
    ni « -3 » à « 3 », ni « A1412 », « 5e » ou la plage « 1412-1413 » à « 1412 » ou « 5 ».
    Limite du critère d'inclusion : une négation ou une disjonction (« 1412 ou 1413 ») matche.
    """
    ref, rep = _jetons(reference), _jetons(answer)
    if not ref or len(ref) > len(rep):
        return False
    n = len(ref)
    return any(rep[i : i + n] == ref for i in range(len(rep) - n + 1))


# --- Critères automatiques (FR-36, AD-14) : jamais de Juge, `judge_model: "auto"` ---------------

JUGE_AUTO = "auto"


def citation_correctness(
    cited: Collection[str],
    reference_anchor_ids: Collection[str],
    corpus_anchor_ids: Collection[str],
    *,
    unanswerable: bool,
    invalid: int = 0,
) -> bool:
    """Oui si au moins une Citation désigne un Ancrage de référence et qu'aucune n'est hors du
    Corpus ; pour une Question `unanswerable`, oui si la Réponse ne cite rien. `invalid` : Citations
    écartées par le Generator faute de désigner un Ancrage (`Answer.invalid_citations`) ; elles
    sont hors du Corpus, donc une seule suffit à rendre le Critère faux."""
    if invalid:
        return False
    if unanswerable:
        return not cited
    corpus = set(corpus_anchor_ids)
    return any(a in set(reference_anchor_ids) for a in cited) and all(a in corpus for a in cited)


def abstention_correctness(abstained: bool, *, unanswerable: bool) -> bool:
    """Oui si la Réponse s'abstient exactement quand la Question est `unanswerable`."""
    return abstained == unanswerable


def faithfulness_sans_objet(text: str, abstained: bool) -> bool:
    """Vrai pour une Réponse vide (ou faite de blancs) ou une abstention : elle n'affirme rien,
    `faithfulness` vaut `na` sans appel de Juge (story 9.3)."""
    return abstained or not text.strip()
