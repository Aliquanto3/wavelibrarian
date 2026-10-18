"""Appariement des résultats par Question (fonction pure, AD-22)."""

from collections.abc import Mapping


def questions_communes[T](a: Mapping[str, T], b: Mapping[str, T]) -> list[str]:
    """Identifiants présents dans les deux ensembles, triés (AD-20)."""
    return sorted(set(a) & set(b))
