"""Cache de réponses LLM `llm_cache.sqlite` (FR-34) : pas de paiement en double."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wavelibrarian.core.ids import canonical_json
from wavelibrarian.core.types import Usage
from wavelibrarian.llm._db import connect, resolve_wl_home, transaction
from wavelibrarian.ports.gateway import LLMRequest

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS responses "
    "(key TEXT PRIMARY KEY, text TEXT NOT NULL, usage TEXT NOT NULL, latency_s REAL)"
)


def role_marker(role: str) -> str:
    """Marqueur que la passerelle pose en première ligne du system (AD-4, contracts.md §3)."""
    return f"[[wl:role={role}]]\n"


def cache_key(
    request: LLMRequest, provider: str, output_schema: dict[str, Any] | None = None
) -> str:
    """`sha256(canonical_json(model, params, system, messages, pass_id[, output_schema]))`.

    `output_schema` (schéma JSON de `complete_structured`) entre dans la clé quand il est
    donné : il change la requête native (outil imposé, `format` d'Ollama) et donc la réponse.

    `step`, `role`, `cache_system`, `Message.cache` et `timeout_s` n'y entrent pas (ils ne
    changent pas la réponse). `inputs` et `step` n'y entrent que pour un provider `fake` : il
    ne lit que `inputs`, et sa sortie scénarisée dépend de `step` (AD-4, contracts.md §2.2, §3).
    `system` est pris tel quel : la passerelle y a déjà posé le marqueur de rôle, qui fait
    entrer le rôle dans la clé (le Faux LLM répond selon le rôle).
    Un system sans ce marqueur lève `ValueError` : la clé se calcule après le marquage.
    """
    if not request.system.startswith(role_marker(request.role)):
        raise ValueError(
            f"system sans marqueur {role_marker(request.role)!r} : "
            "la clé de cache se calcule après le marquage par la passerelle"
        )
    contenu: dict[str, Any] = {
        "model": request.model_id,
        "params": {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "seed": request.seed,
        },
        "system": request.system,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "pass_id": request.pass_id,
    }
    if provider == "fake":
        contenu["inputs"] = request.inputs
        contenu["step"] = request.step  # `script(role, step_glob, …)` : sortie selon l'étape
    if output_schema is not None:
        contenu["output_schema"] = output_schema
    return hashlib.sha256(canonical_json(contenu).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CachedResponse:
    text: str
    usage: Usage
    latency_s: float = 0.0  # latence de l'appel d'origine, retracée au rejeu (p50/p95, §7)


class ResponseCache:
    """Cache persistant des réponses déjà payées."""

    def __init__(self, wl_home: Path | None = None) -> None:
        self._conn = connect(resolve_wl_home(wl_home) / "llm_cache.sqlite")
        try:
            self._conn.execute(_SCHEMA)
            colonnes = {r[1] for r in self._conn.execute("PRAGMA table_info(responses)")}
            if "latency_s" not in colonnes:  # cache d'avant la story 4.5 : latence inconnue (0)
                self._conn.execute("ALTER TABLE responses ADD COLUMN latency_s REAL")
        except BaseException:
            self._conn.close()
            raise

    def close(self) -> None:
        self._conn.close()

    def get(self, key: str) -> CachedResponse | None:
        row = self._conn.execute(
            "SELECT text, usage, latency_s FROM responses WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return None
        return CachedResponse(
            text=row[0], usage=Usage.model_validate_json(row[1]), latency_s=float(row[2] or 0.0)
        )

    def put(
        self, key: str, text: str, usage: Usage, *, replace: bool = False, latency_s: float = 0.0
    ) -> None:
        """Première réponse gardée : une clé déjà présente n'est pas réécrite.

        `replace=True` (passerelle seule) remplace une entrée jugée invalide par une réponse
        conforme, payée en contournant le cache.
        """
        verbe = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
        with transaction(self._conn) as c:
            c.execute(
                f"{verbe} INTO responses (key, text, usage, latency_s) VALUES (?, ?, ?, ?)",  # noqa: S608
                (key, text, usage.model_dump_json(), float(latency_s)),
            )
