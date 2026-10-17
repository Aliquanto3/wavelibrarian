"""Verrou d'Exécution `WL_HOME/run.lock` (AD-11) : une seule Exécution à la fois."""

import os
import sys
from pathlib import Path
from typing import IO

from wavelibrarian.core.errors import WlError

# Octet verrouillé : le premier ; le `run_id` du détenteur s'écrit après, pour rester lisible
# par un second processus même quand le verrou Windows interdit la lecture de l'octet verrouillé.
_DECALAGE = 1


def _verrouiller(f: IO[bytes]) -> bool:
    f.seek(0)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _deverrouiller(f: IO[bytes]) -> None:
    f.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class RunLock:
    """Verrou du système : libéré par l'OS si le processus meurt, sans fichier orphelin bloquant."""

    def __init__(self, wl_home: Path, run_id: str) -> None:
        self.path = wl_home / "run.lock"
        self.run_id = run_id
        self._f: IO[bytes] | None = None

    def acquire(self) -> None:
        """Prend le verrou ; `WlError` « Exécution <run_id> en cours » s'il est détenu."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        f = os.fdopen(fd, "r+b", buffering=0)
        if not _verrouiller(f):
            try:
                f.seek(_DECALAGE)
                detenteur = f.read().decode("utf-8", "replace").strip() or "inconnue"
            finally:
                f.close()
            raise WlError(f"Exécution {detenteur} en cours")
        f.seek(_DECALAGE)
        f.truncate(_DECALAGE)
        f.write(self.run_id.encode("utf-8"))
        self._f = f

    def release(self) -> None:
        f, self._f = self._f, None
        if f is None:
            return
        try:
            _deverrouiller(f)
        finally:
            f.close()
