"""Story 4.15 : test réel SM-4 sur Claude Haiku 5.5 (`real_api`, jamais lancé par défaut).

Lancement (consomme l'API Anthropic, 5 $ au plus) :
    uv run pytest -q --tb=short -m real_api tests/real/test_sm4.py

Désélectionné par défaut (`addopts` de pyproject), sauté sans `ANTHROPIC_API_KEY` dans
l'environnement. Expérience propre au test : `experiment_sm4.yaml` (5 Questions, Juges et embedder
factices, plafond 5,00 USD), indépendante de `experiments/mini-real-haiku.yaml` (story 4.14).
"""

import csv
import json
import os
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import charger_yaml, load_costs
from wavelibrarian.core.types import Usage

EXPERIENCE = Path(__file__).with_name("experiment_sm4.yaml")
PLAFOND_USD = Decimal("5.00")
CENTIME = Decimal("0.005")  # « au centime près » : écart d'au plus un demi-centime

pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY absente"),
]


def _lignes(chemin: Path) -> list[dict[str, Any]]:
    texte = chemin.read_text(encoding="utf-8")
    return [json.loads(ligne) for ligne in texte.splitlines() if ligne.strip()]


def _usage(span: dict[str, Any]) -> Usage:
    return Usage(
        input_tokens=int(span.get("gen_ai.usage.input_tokens", 0)),
        output_tokens=int(span.get("gen_ai.usage.output_tokens", 0)),
        cache_read_tokens=int(span.get("wl.usage.cache_read_tokens", 0)),
        cache_write_tokens=int(span.get("wl.usage.cache_write_tokens", 0)),
    )


def test_sm4_cout_trace_egal_cout_recalcule(wl_home: Path) -> None:
    # Garde du plafond : l'Expérience du test doit porter un plafond ne dépassant pas 5 $.
    plafond = charger_yaml(EXPERIENCE)["budget"]["per_run"]["anthropic"]
    assert Decimal(plafond["amount"]) <= PLAFOND_USD and plafond["currency"] == "USD"

    res = CliRunner().invoke(app, ["run", str(EXPERIENCE)])
    assert res.exit_code == 0, res.output  # 3 = plafond atteint : le test échoue
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    run_id = dossier.name

    # 1. Chaque span payant : `wl.cost` == catalog.cost(model, usage), au dernier chiffre.
    catalogue = load_catalog()
    payants = [
        s
        for s in _lignes(dossier / "traces.jsonl")
        if s.get("gen_ai.provider.name") == "anthropic" and not s.get("wl.llm_cache_hit")
    ]
    assert payants, "aucun span payant : l'API n'a pas été appelée"
    total_spans = Decimal(0)
    for span in payants:
        attendu = catalogue.cost(span["gen_ai.request.model"], _usage(span))
        assert Decimal(span["wl.cost"]) == attendu, span
        total_spans += attendu
    assert total_spans < PLAFOND_USD

    # 2. Registre de dépense : somme réglée pour ce run_id == somme des spans, au centime près.
    conn = sqlite3.connect(wl_home / "ledger.sqlite")
    try:
        (regle,) = conn.execute(
            "SELECT COALESCE(SUM(CAST(actual AS REAL)), 0) FROM reservations "
            "WHERE run_id=? AND provider='anthropic' AND status='settled'",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()
    assert abs(Decimal(str(regle)) - total_spans) <= CENTIME

    # 3. Rapport : somme de `cost_eur_real` de costs.csv == somme des spans convertie en euros.
    taux = load_costs(wl_home).fx.rates_to_eur["USD"]
    with (dossier / "report" / "costs.csv").open(encoding="utf-8", newline="") as f:
        total_rapport = sum((Decimal(r["cost_eur_real"]) for r in csv.DictReader(f)), Decimal(0))
    assert abs(total_rapport - total_spans * taux) <= CENTIME

    # 4. Ni la clé ni l'en-tête `x-api-key` dans un fichier de l'Exécution.
    cle = os.environ["ANTHROPIC_API_KEY"]
    for fichier in dossier.rglob("*"):
        if fichier.is_file():
            texte = fichier.read_bytes().decode("utf-8", errors="replace")
            assert cle not in texte, fichier
