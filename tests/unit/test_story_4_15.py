"""Story 4.15 : l'Expérience du test réel SM-4 est valide sans réseau et plafonnée à 5 USD."""

from decimal import Decimal
from pathlib import Path

from wavelibrarian.config.validate import validate_file

EXPERIENCE = Path(__file__).resolve().parents[1] / "real" / "experiment_sm4.yaml"


def test_experience_sm4_valide_et_plafonnee() -> None:
    exp = validate_file(EXPERIENCE).resolved
    assert exp.max_questions == 5
    assert exp.budget.per_run["anthropic"].amount == Decimal("5.00")
    assert exp.judges.pool == ("fake-llm-b", "fake-llm-c")
    assert {m for c in exp.configurations for m in c.models} == {
        "claude-haiku-5-5",
        "fake-embedder",
    }
