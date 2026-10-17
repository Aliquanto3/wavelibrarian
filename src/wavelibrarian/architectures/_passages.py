"""Fichier `passages.jsonl` commun aux Architectures à Passages (contracts.md §2.1)."""

from collections.abc import Iterable
from pathlib import Path

from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import Passage

FICHIER = "passages.jsonl"


def ecrire_passages(directory: Path, passages: Iterable[Passage]) -> None:
    """Un Passage par ligne, UTF-8, LF."""
    directory.mkdir(parents=True, exist_ok=True)
    lignes = "".join(p.model_dump_json() + "\n" for p in passages)
    (directory / FICHIER).write_bytes(lignes.encode("utf-8"))


def lire_passages(directory: Path) -> list[Passage]:
    chemin = directory / FICHIER
    try:
        texte = chemin.read_text(encoding="utf-8")
    except OSError as exc:
        raise WlError(f"index illisible : {chemin} absent ou illisible") from exc
    return [Passage.model_validate_json(ligne) for ligne in texte.split("\n") if ligne]
