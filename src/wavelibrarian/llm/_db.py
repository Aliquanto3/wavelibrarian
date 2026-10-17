"""Accès SQLite commun au registre de dépense et au Cache de réponses (AD-9, AD-11)."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def resolve_wl_home(wl_home: Path | None = None) -> Path:
    """Dossier d'état : argument, sinon `WL_HOME`, sinon `./.wl`."""
    if wl_home is not None:
        return wl_home
    env = os.environ.get("WL_HOME")
    return Path(env) if env else Path(".wl")


def connect(path: Path) -> sqlite3.Connection:
    """Connexion en mode autocommit : les transactions sont ouvertes à la main (`transaction`)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """`BEGIN IMMEDIATE` : le verrou d'écriture est pris dès le début (lecture comprise)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
