"""Tests du Catalogue, des paramètres de coût et des profils (story 1.4)."""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from wavelibrarian.config.catalog import ModelCatalog, load_catalog
from wavelibrarian.config.defaults import PROFILS, load_costs, load_profile
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import Usage

HAIKU = "claude-haiku-5-5"
MILLION = 1_000_000


@pytest.fixture(scope="module")
def catalog() -> ModelCatalog:
    return load_catalog()


def test_catalogue_livre(catalog: ModelCatalog) -> None:
    haiku = catalog.get(HAIKU)
    assert haiku.token_factor == Decimal("1.5")
    assert haiku.prompt_cache is True
    assert haiku.min_cacheable_tokens == 512
    assert haiku.pricing is not None
    assert haiku.pricing.currency == "USD"
    assert haiku.pricing.tiers[0].above_prompt_tokens == 100_000
    assert haiku.pricing.tiers[0].multiplier == Decimal("5")
    for mid in (
        "minicpm5:1b-q4_k_m",
        "minicpm5:2b-q4_k_m",
        "granite4.2:3b",
        "qwen3.5:4b",
        "ministral-3:8b",
        "multilingual-e5-small",
        "bge-m3",
    ):
        assert catalog.get(mid).kind == "local"
    assert catalog.get("bge-m3").dim == 1024
    for lettre in "abc":
        fake = catalog.get(f"fake-llm-{lettre}")
        assert fake.family == f"fake-{lettre}"
        assert fake.provider == "fake"
        assert fake.pricing is not None
    assert catalog.get("fake-embedder").dim == 64
    assert catalog.get("fake-embedder").provider == "fake"


def test_api_sans_prix_refuse(tmp_path: Path) -> None:
    data = {
        "catalog_date": "2026-10-17",
        "models": [
            {"id": "m0", "provider": "ollama", "family": "f", "kind": "local", "modality": "llm"},
            {"id": "m1", "provider": "anthropic", "family": "f", "kind": "api", "modality": "llm"},
        ],
    }
    f = tmp_path / "models.yaml"
    f.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_catalog(f)
    assert exc.value.path == "models[1].pricing"


def test_cle_inconnue_et_yaml_invalide(tmp_path: Path) -> None:
    f = tmp_path / "models.yaml"
    f.write_text("catalog_date: 2026-10-17\nmodels: []\nextra: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_catalog(f)
    assert exc.value.path == "extra"
    f.write_text("a: [", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_catalog(f)


def test_get_absent(catalog: ModelCatalog) -> None:
    with pytest.raises(ConfigError, match="absent"):
        catalog.get("absent")


def test_cout_un_million_sans_palier(catalog: ModelCatalog) -> None:
    # Écart signalé : 1 M tokens d'entrée dépasse déjà le palier (x5, soit 3.00).
    # Le montant 0.60 de la story s'obtient avec les mêmes tarifs sans palier.
    haiku = catalog.get(HAIKU)
    assert haiku.pricing is not None
    sans_palier = haiku.model_copy(
        update={"pricing": haiku.pricing.model_copy(update={"tiers": ()})}
    )
    cat = ModelCatalog(catalog_date=catalog.catalog_date, models=(sans_palier,))
    cout = cat.cost(HAIKU, Usage(input_tokens=MILLION, output_tokens=MILLION))
    assert cout == Decimal("0.60")
    assert isinstance(cout, Decimal)
    assert catalog.cost(HAIKU, Usage(input_tokens=MILLION, output_tokens=MILLION)) == Decimal(
        "3.00"
    )


def test_cout_palier_tous_postes(catalog: ModelCatalog) -> None:
    # Prompt de 100 000 : pas de palier.
    usage = Usage(input_tokens=50_000, cache_read_tokens=50_000, output_tokens=1000)
    assert catalog.cost(HAIKU, usage) == Decimal("0.005") + Decimal("0.0005") + Decimal("0.0005")
    # 100 001 : palier x5 sur tous les postes, cache et sortie compris.
    usage = Usage(input_tokens=50_000, cache_read_tokens=50_001, output_tokens=1000)
    attendu = (
        Decimal("0.005") + Decimal(50_001) * Decimal("0.01") / MILLION + Decimal("0.0005")
    ) * 5
    assert catalog.cost(HAIKU, usage) == attendu
    # L'écriture de cache compte dans le prompt.
    usage = Usage(input_tokens=10, cache_write_tokens=100_000)
    assert (
        catalog.cost(HAIKU, usage)
        == (Decimal(10) * Decimal("0.10") / MILLION + Decimal(100_000) * Decimal("0.125") / MILLION)
        * 5
    )


def test_cout_cache_et_local(catalog: ModelCatalog) -> None:
    usage = Usage(cache_read_tokens=1000, cache_write_tokens=2000)
    assert (
        catalog.cost(HAIKU, usage)
        == (Decimal(1000) * Decimal("0.01") + Decimal(2000) * Decimal("0.125")) / MILLION
    )
    assert catalog.cost("granite4.2:3b", Usage(input_tokens=999)) == Decimal(0)


def test_cout_fake(catalog: ModelCatalog) -> None:
    usage = Usage(
        input_tokens=1000, output_tokens=1000, cache_read_tokens=1000, cache_write_tokens=1000
    )
    assert catalog.cost("fake-llm-a", usage) == Decimal("0.00435")


def test_costs_defauts() -> None:
    c = load_costs(wl_home=None)
    assert c.owned_costs.kwh_price_eur == Decimal("0.2001")
    assert c.carbon.gco2e_per_kwh == Decimal("19.6")
    assert c.fx.rates_to_eur["USD"] == Decimal("0.8938")


def test_costs_fusion_cle_par_cle(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "costs.yaml").write_text('owned_costs:\n  kwh_price_eur: "0.30"\n', encoding="utf-8")
    exp = tmp_path / "exp_costs.yaml"
    exp.write_text('carbon:\n  gco2e_per_kwh: "50"\n', encoding="utf-8")
    base = load_costs(wl_home=None)
    c = load_costs(wl_home=home, experiment_costs=exp)
    assert c.owned_costs.kwh_price_eur == Decimal("0.30")
    assert c.carbon.gco2e_per_kwh == Decimal("50")
    # Le reste et les dates des valeurs sont conservés.
    assert c.owned_costs.date == base.owned_costs.date
    assert c.owned_costs.hardware_price_eur == base.owned_costs.hardware_price_eur
    assert c.carbon.date == base.carbon.date
    assert c.carbon.region == "FR"
    assert c.fx == base.fx
    # Précédence : l'Expérience l'emporte sur WL_HOME.
    exp.write_text('owned_costs:\n  kwh_price_eur: "0.40"\n', encoding="utf-8")
    resolu = load_costs(wl_home=home, experiment_costs=exp)
    assert resolu.owned_costs.kwh_price_eur == Decimal("0.40")


def test_costs_wl_home_par_variable(wl_home: Path) -> None:
    (wl_home / "costs.yaml").write_text("carbon:\n  region: DE\n", encoding="utf-8")
    assert load_costs().carbon.region == "DE"


def test_costs_cle_inconnue(tmp_path: Path) -> None:
    exp = tmp_path / "c.yaml"
    exp.write_text("carbon:\n  inconnue: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        load_costs(wl_home=None, experiment_costs=exp)
    assert e.value.path == "carbon.inconnue"


def test_profils() -> None:
    cpu, gpu, test = (load_profile(n) for n in PROFILS)
    assert cpu.ollama.options == {"num_gpu": 0}
    assert cpu.embedder_device == "cpu"
    assert cpu.defaults.embedder == "multilingual-e5-small"
    assert cpu.defaults.generator_models == (HAIKU, "minicpm5:1b-q4_k_m")
    assert gpu.ollama.options == {}
    assert gpu.embedder_device == "cuda"
    assert gpu.defaults.embedder == "bge-m3"
    assert {"qwen3.5:4b", "ministral-3:8b"} <= gpu.model_ids()
    assert test.tokenizer == "approx"
    assert test.energy.local == "fake"
    assert test.energy.api == "fake"
    assert all(m.startswith("fake-") for m in test.model_ids())


def test_profil_inconnu() -> None:
    with pytest.raises(ConfigError, match="cpu, gpu, test"):
        load_profile("tpu")


@pytest.mark.parametrize("nom", PROFILS)
def test_coherence_profils_catalogue(catalog: ModelCatalog, nom: str) -> None:
    profil = load_profile(nom)
    for mid in profil.model_ids():
        catalog.get(mid)
    assert catalog.get(profil.defaults.embedder).modality == "embedding"


def test_cout_un_million_catalogue_livre(catalog: ModelCatalog) -> None:
    # AC réécrit de la story 1.4 (arbitrage P1) : 1 M d'entrée dépasse 100 000, donc
    # x5 sur 0.10 + 0.50 ; sous le seuil, prix de base (0.10 x 0.05 + 0.50 x 0.05).
    cout = catalog.cost(HAIKU, Usage(input_tokens=MILLION, output_tokens=MILLION))
    assert cout == Decimal("3.00")
    assert isinstance(cout, Decimal)
    petit = catalog.cost(HAIKU, Usage(input_tokens=50_000, output_tokens=50_000))
    assert petit == Decimal("0.03")
    assert isinstance(petit, Decimal)


def _catalogue(tmp_path: Path, modele: dict[str, object]) -> Path:
    f = tmp_path / "models.yaml"
    f.write_text(
        yaml.safe_dump({"catalog_date": "2026-10-17", "models": [modele]}), encoding="utf-8"
    )
    return f


_PRIX = {"date": "2026-10-17", "currency": "USD", "per_mtok": {"input": "1", "output": "2"}}


def test_local_avec_prix_refuse(tmp_path: Path) -> None:
    m = {"id": "m", "provider": "ollama", "family": "f", "kind": "local", "modality": "llm"}
    with pytest.raises(ConfigError, match="local") as exc:
        load_catalog(_catalogue(tmp_path, {**m, "pricing": _PRIX}))
    assert exc.value.path == "models[0].pricing"


def test_tarifs_requis(tmp_path: Path) -> None:
    m = {"id": "m", "provider": "anthropic", "family": "f", "kind": "api", "modality": "llm"}
    sans_sortie = {**_PRIX, "per_mtok": {"input": "1"}}
    with pytest.raises(ConfigError, match="output") as exc:
        load_catalog(_catalogue(tmp_path, {**m, "pricing": sans_sortie}))
    assert exc.value.path == "models[0].pricing"
    with pytest.raises(ConfigError, match="cache_read, cache_write"):
        load_catalog(_catalogue(tmp_path, {**m, "prompt_cache": True, "pricing": _PRIX}))
    # Sans cache déclaré, des tokens de cache sans tarif ne sont pas facturés à 0 en silence.
    cat = load_catalog(_catalogue(tmp_path, {**m, "pricing": _PRIX}))
    assert cat.cost("m", Usage(input_tokens=MILLION)) == Decimal("1")
    with pytest.raises(ConfigError, match="cache_read"):
        cat.cost("m", Usage(cache_read_tokens=10))
