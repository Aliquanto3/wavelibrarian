import re
from decimal import Decimal

from wavelibrarian.core.ids import canonical_json, new_run_id, sha16, slug


def test_canonical_json() -> None:
    assert canonical_json({"b": 1, "a": Decimal("1.50")}) == '{"a":"1.50","b":1}'


def test_sha16_stable() -> None:
    assert sha16("a", "b") == sha16("a", "b")
    assert re.fullmatch(r"[0-9a-f]{16}", sha16("a"))
    assert sha16("a", "b") != sha16("ab")


def test_slug() -> None:
    assert slug("Éléments d'histoire") == "elements-d-histoire"


def test_new_run_id() -> None:
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", new_run_id("abc"))
