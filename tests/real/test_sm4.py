"""Story 4.15 : test réel SM-4 sur Claude Haiku 5.5 (`real_api`, jamais lancé par défaut).

Lancement (consomme l'API Anthropic, 5 $ au plus) :
    uv run pytest -q --tb=short -m real_api tests/real/test_sm4.py

Désélectionné par défaut (`addopts` de pyproject), sauté sans `ANTHROPIC_API_KEY` dans
l'environnement. Expériences : `experiments/mini-real-haiku.yaml` (livrée par 4.14 : 5 Questions,
5 Configurations, Juges factices, plafond 5,00 USD) et `experiment_sm4_juges.yaml`
(un Juge Haiku réel).
"""

import csv
import json
import os
import sqlite3
from decimal import Decimal
from math import ceil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import charger_yaml, load_costs
from wavelibrarian.core.types import Usage

RACINE = Path(__file__).resolve().parents[2]
EXPERIENCE = RACINE / "experiments" / "mini-real-haiku.yaml"
EXPERIENCE_JUGES = Path(__file__).with_name("experiment_sm4_juges.yaml")
PLAFOND_USD = Decimal("5.00")
INVITE = "Question : capitale de la France ? Passage : Paris."
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


def _verifier_run(experience: Path, wl_home: Path) -> list[dict[str, Any]]:
    """Lance `wl run`, vérifie les AC 2 à 6 et renvoie les spans payants."""
    # Garde du plafond : l'Expérience doit porter un plafond Anthropic d'au plus 5 $.
    plafond = charger_yaml(experience)["budget"]["per_run"]["anthropic"]
    assert Decimal(plafond["amount"]) <= PLAFOND_USD and plafond["currency"] == "USD"

    res = CliRunner().invoke(app, ["run", str(experience)])
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
    print(f"SM-4 {experience.name} : {len(payants)} appels, coût tracé {total_spans} USD")

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
    print(f"SM-4 registre réglé {regle} USD, écart {abs(Decimal(str(regle)) - total_spans)}")
    assert abs(Decimal(str(regle)) - total_spans) <= CENTIME

    # 3. Rapport (story 8.2) : `cost_eur_real` (hors possession) == dépense du Registre Anthropic
    #    convertie en euros ; les Juges factices sont dans `cost_eur_fake`, hors du coût réel.
    taux = load_costs(wl_home).fx.rates_to_eur
    with (dossier / "report" / "costs.csv").open(encoding="utf-8", newline="") as f:
        lignes_csv = list(csv.DictReader(f))
    total_rapport = sum(
        (Decimal(r["cost_eur_real"]) - Decimal(r["possession_eur"]) for r in lignes_csv),
        Decimal(0),
    )
    registre_eur = Decimal(str(regle)) * taux["USD"]
    print(f"SM-4 cost_eur_real {total_rapport} EUR, registre converti {registre_eur} EUR")
    assert abs(total_rapport - registre_eur) <= CENTIME
    assert total_rapport > 0 and "cost_eur_fake" in lignes_csv[0]

    # 4. Ni la clé ni l'en-tête `x-api-key` dans un fichier de l'Exécution.
    cle = os.environ["ANTHROPIC_API_KEY"]
    for fichier in dossier.rglob("*"):
        if fichier.is_file():
            texte = fichier.read_bytes().decode("utf-8", errors="replace")
            assert cle not in texte and "x-api-key" not in texte.lower(), fichier
    return payants


def test_sm4_cout_trace_egal_cout_recalcule(wl_home: Path) -> None:
    payants = _verifier_run(EXPERIENCE, wl_home)
    assert len(payants) >= 5  # des Réponses servies par le Cache de réponses sont exclues


def test_sm4_plafond_couvre_les_juges(wl_home: Path) -> None:
    """Generator factice, Juge Haiku réel : les seuls appels payants sont ceux du Juge, qui passent
    par le même Registre et le même plafond que le Generator."""
    payants = _verifier_run(EXPERIENCE_JUGES, wl_home)
    assert len(payants) >= 2  # un appel de Juge par Réponse


def test_sm4_temperature_et_outil_impose_acceptes() -> None:
    """L'outil `emit_output` imposé est accepté, et `accepts_temperature` du Catalogue dit vrai :
    `false` (Haiku 5.5) si l'API refuse `temperature` (HTTP 400, envoyée par `extra_body`, SDK
    1.15), `true` si elle l'accepte. La requête effective suit la capacité, comme la passerelle."""
    from wavelibrarian.core.errors import ProviderError
    from wavelibrarian.llm.providers.anthropic import AnthropicProvider
    from wavelibrarian.llm.roles import GradeRelevanceOutput
    from wavelibrarian.ports.gateway import LLMRequest, Message

    requete = LLMRequest(
        model_id="claude-haiku-5-5",
        role="grade_relevance",
        step="sm4.outil",
        system="Tu évalues la pertinence d'un passage.",
        messages=(Message(role="user", content=INVITE),),
        max_tokens=200,
        temperature=0.0,
    )
    schema = GradeRelevanceOutput.model_json_schema()
    fournisseur = AnthropicProvider()
    if load_catalog().get(requete.model_id).accepts_temperature:
        rep = fournisseur.complete(requete, timeout_s=60, output_schema=schema)
    else:
        with pytest.raises(ProviderError, match="HTTP 400"):
            fournisseur.complete(requete, timeout_s=60, output_schema=schema)
        effective = requete.model_copy(update={"temperature": None})
        rep = fournisseur.complete(effective, timeout_s=60, output_schema=schema)
    GradeRelevanceOutput.model_validate_json(rep.text)  # entrée de l'outil `emit_output`
    assert rep.usage.output_tokens > 0


def test_sm4_majorant_schema_couvre_count_tokens() -> None:
    """Le majorant de la passerelle (tokens du schéma x facteur, arrondi au-dessus, + 600) couvre
    le surcoût réel de `count_tokens`."""
    import anthropic
    from anthropic.types import MessageParam

    from wavelibrarian.llm.providers.anthropic import OUTIL_SORTIE, AnthropicProvider
    from wavelibrarian.llm.providers.secrets import load_secret
    from wavelibrarian.llm.roles import GradeRelevanceOutput
    from wavelibrarian.measure.tokenizers import ReferenceTokenizer

    cle = load_secret("ANTHROPIC_API_KEY")
    assert cle is not None
    client = anthropic.Anthropic(api_key=cle.get_secret_value(), max_retries=0)
    modele = "claude-haiku-5-5"
    schema = GradeRelevanceOutput.model_json_schema()
    messages: list[MessageParam] = [{"role": "user", "content": INVITE}]
    sans = client.messages.count_tokens(model=modele, messages=messages).input_tokens
    avec = client.messages.count_tokens(
        model=modele,
        messages=messages,
        tools=[{"name": OUTIL_SORTIE, "description": "Renvoie.", "input_schema": schema}],
        tool_choice={"type": "tool", "name": OUTIL_SORTIE},
    ).input_tokens
    texte = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    facteur = load_catalog().get(modele).token_factor
    majorant = (
        ceil(Decimal(ReferenceTokenizer().count(texte)) * facteur)
        + AnthropicProvider.schema_prompt_overhead
    )
    print(f"SM-4 count_tokens : surcoût réel {avec - sans}, majorant {majorant}")
    assert avec - sans <= majorant
