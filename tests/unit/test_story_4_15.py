"""Story 4.15 : les Expériences du test réel SM-4 sont valides sans réseau et plafonnées à 5 USD."""

from decimal import Decimal
from pathlib import Path

from wavelibrarian.config.validate import validate_file

RACINE = Path(__file__).resolve().parents[2]


def test_experience_sm4_est_mini_real_haiku_plafonnee() -> None:
    exp = validate_file(RACINE / "experiments" / "mini-real-haiku.yaml").resolved
    assert exp.max_questions == 5
    assert exp.budget.per_run["anthropic"].amount == Decimal("5.00")
    assert exp.judges.pool == ("fake-llm-b", "fake-llm-c")


def test_majorant_de_schema_unique() -> None:
    """Les Composants ne voient pas les providers : `SURCOUT_SCHEMA` recopie le majorant."""
    from wavelibrarian.components.graph._texte import SURCOUT_SCHEMA
    from wavelibrarian.llm.providers.anthropic import AnthropicProvider

    assert SURCOUT_SCHEMA == AnthropicProvider.schema_prompt_overhead


def test_experience_juges_reels_valide_et_plafonnee() -> None:
    exp = validate_file(RACINE / "tests" / "real" / "experiment_sm4_juges.yaml").resolved
    assert exp.max_questions == 2
    assert exp.budget.per_run["anthropic"].amount == Decimal("5.00")
    assert exp.judges.pool is not None and "claude-haiku-5-5" in exp.judges.pool
