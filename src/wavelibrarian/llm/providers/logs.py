"""Journaux des bibliothèques réseau (AD-19) : jamais en dessous de `WARNING`.

Les journaux `DEBUG` d'`anthropic`, `httpx` et `httpcore` peuvent détailler requêtes et en-têtes
(`x-api-key` compris). `limiter_journaux` les ramène à `WARNING` au niveau des loggers et, si on
lui passe le gestionnaire de `run.log`, par un filtre qui résiste à un niveau relevé après coup
(variable `ANTHROPIC_LOG=debug`, logging racine en `DEBUG`).
"""

import logging

LOGGERS_RESEAU = ("anthropic", "httpx", "httpcore")


class _FiltreReseau(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        return not any(
            record.name == nom or record.name.startswith(nom + ".") for nom in LOGGERS_RESEAU
        )


def limiter_journaux(handler: logging.Handler | None = None) -> None:
    """Force les trois loggers à `WARNING` et filtre leurs messages sous ce niveau sur `handler`."""
    for nom in LOGGERS_RESEAU:
        logging.getLogger(nom).setLevel(logging.WARNING)
    if handler is not None and not any(isinstance(f, _FiltreReseau) for f in handler.filters):
        handler.addFilter(_FiltreReseau())
