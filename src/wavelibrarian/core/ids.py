"""Identités et sérialisation canonique."""

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


def _defaut(obj: Any) -> str:
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Type non sérialisable : {type(obj).__name__}")


def canonical_json(obj: Any) -> str:
    """JSON canonique : clés triées, sans espaces, `Decimal` en chaîne."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_defaut
    )


def sha16(*parts: str) -> str:
    """16 premiers caractères hexadécimaux du sha256 des parties."""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def slug(text: str) -> str:
    """Minuscules, accents retirés, uniquement `[a-z0-9-]`."""
    sans_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", sans_accents.lower()).strip("-")


def new_run_id(experiment_hash: str) -> str:
    """Identifiant d'Exécution `YYYYMMDD-HHMMSS-<6 hex>` en UTC."""
    maintenant = datetime.now(UTC)
    suffixe = sha16(experiment_hash, maintenant.isoformat())[:6]
    return f"{maintenant:%Y%m%d-%H%M%S}-{suffixe}"


def sha16_bytes(data: bytes) -> str:
    """16 premiers caracteres hexadecimaux du sha256 d octets bruts (doc_id, AD-5)."""
    return hashlib.sha256(data).hexdigest()[:16]


def answer_id(
    run_id: str, config_id: str, condition: str, tier: int | None, phase: str, question_id: str
) -> str:
    """`<run_id>/<config_id>/<condition>/<tier>/<phase>/<question_id>`, `tier = "all"` sans
    Palier (contracts.md §1)."""
    palier = "all" if tier is None else str(tier)
    return "/".join((run_id, config_id, condition, palier, phase, question_id))
