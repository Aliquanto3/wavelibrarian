"""Expériences livrées dans `experiments/` (story 4.14) : chargées et validées sans réseau."""

from pathlib import Path

import pytest

from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.validate import ValidationResult, validate_file

EXPERIENCES = Path(__file__).resolve().parents[2] / "experiments"


def _valider(nom: str, wl_home: Path) -> ValidationResult:
    return validate_file(EXPERIENCES / f"{nom}.yaml", wl_home)


def _fournisseurs(res: ValidationResult) -> set[str]:
    catalogue = load_catalog()
    modeles = {m for c in res.resolved.configurations for m in c.models}
    modeles |= set(res.resolved.judges.pool or ())
    return {catalogue.get(m).provider for m in modeles}


@pytest.mark.parametrize("nom", sorted(p.stem for p in EXPERIENCES.glob("*.yaml")))
def test_experience_livree_valide_sans_reseau(nom: str, wl_home: Path) -> None:
    res = _valider(nom, wl_home)
    assert res.panels  # Panel admissible pour chaque Configuration (AD-14)
    # Toute Expérience livrée sur le Mini-corpus borne ses Paliers (split dev : 12 Documents).
    if res.resolved.tier is not None and res.resolved.split == "dev":
        assert res.resolved.max_questions is not None


def test_mini_cpu_profil_cpu_sans_api(wl_home: Path) -> None:
    res = _valider("mini-cpu", wl_home)
    assert res.resolved.profile == "cpu"
    assert _fournisseurs(res) <= {"ollama", "sentence_transformers"}


def test_mini_real_haiku_api_seule(wl_home: Path) -> None:
    res = _valider("mini-real-haiku", wl_home)
    r = res.resolved
    assert r.max_questions == 5
    plafond = r.budget.per_run["anthropic"]
    assert (plafond.amount, plafond.currency) == (5, "USD")
    assert tuple(r.judges.pool or ()) == ("fake-llm-b", "fake-llm-c")
    assert {p for c in r.configurations for p in c.answer_producers} == {"claude-haiku-5-5"}
    # Aucun modèle local : seule l'API Anthropic est sollicitée (l'embedder et les Juges sont
    # factices), ce qui laisse l'Ollama local libre pour un autre banc.
    assert _fournisseurs(res) == {"anthropic", "fake"}
    embedders = {c.params["embedder"]["name"] for c in r.configurations if "embedder" in c.params}
    assert embedders <= {"fake"}
