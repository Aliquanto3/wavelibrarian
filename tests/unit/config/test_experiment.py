"""Tests du chargement et de la résolution d'une Expérience (story 1.5)."""

import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Annotated, Any

import pytest
import yaml
from pydantic import BaseModel, ConfigDict, Field

from wavelibrarian import registry
from wavelibrarian.config.experiment import Experiment
from wavelibrarian.config.load import load_experiment
from wavelibrarian.config.resolve import (
    fingerprint,
    resolve_experiment,
    to_yaml,
    write_resolved,
)
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import ModelRef, ModelRefMeta
from wavelibrarian.ports.components import ComponentSpec


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@pytest.fixture(autouse=True)
def composants_de_test() -> Iterator[None]:
    """Enregistre des Composants de test, puis restaure le registre."""
    sauve = dict(registry._REGISTRE)
    decouvert = registry._decouvert
    modules = set(sys.modules)
    registry._decouvert = True  # les paquets livrés sont vides ou hors sujet ici

    @registry.register("chunker", "fixed")
    class Fixed:
        """Découpe fixe."""

        class Params(_Params):
            size: int = 300
            overlap: int = 50

    @registry.register("vector_store", "exact")
    class Exact:
        """Magasin exact."""

        class Params(_Params):
            pass

    @registry.register("generator", "llm_test")
    class LlmTest:
        """Generator de test."""

        class Params(_Params):
            model: Annotated[str | None, ModelRefMeta("generator_models[0]", True)] = None
            max_tokens: int = 512

    @registry.register("embedder", "sentence_transformers")
    class St:
        """Embedder réel."""

        class Params(_Params):
            model: Annotated[str | None, ModelRefMeta("embedder")] = None

    @registry.register("embedder", "fake")
    class Fake:
        """Faux embedder."""

        class Params(_Params):
            model: ModelRef = None

    @registry.register("architecture", "arch_test")
    class Arch:
        """Architecture de test."""

        class Params(_Params):
            chunker: ComponentSpec = ComponentSpec(name="fixed")
            embedder: ComponentSpec | None = None
            store: ComponentSpec = ComponentSpec(name="exact")
            generator: ComponentSpec = ComponentSpec(name="llm_test")
            k: int = 5
            alias: Annotated[ComponentSpec, Field(json_schema_extra={"kind": "chunker"})] = (
                ComponentSpec(name="fixed")
            )

    yield
    registry._REGISTRE.clear()
    registry._REGISTRE.update(sauve)
    registry._decouvert = decouvert
    for nom in set(sys.modules) - modules:
        if nom.startswith(registry._PAQUETS_DECOUVERTS):
            del sys.modules[nom]


BASE: dict[str, Any] = {
    "experiment_id": "exp-test",
    "seed": 42,
    "corpus": "../corpora/mini/corpus.yaml",
    "questions": "../corpora/mini/questions.yaml",
    "configurations": [
        {"id": "a", "architecture": "arch_test"},
        {"id": "b", "architecture": "arch_test", "params": {"k": 3}},
    ],
}


@pytest.fixture
def ecrire(tmp_path: Path) -> Callable[..., Path]:
    def _ecrire(donnees: dict[str, Any] | str, nom: str = "experiments/exp.yaml") -> Path:
        chemin = tmp_path / nom
        chemin.parent.mkdir(parents=True, exist_ok=True)
        texte = donnees if isinstance(donnees, str) else yaml.safe_dump(donnees, sort_keys=False)
        chemin.write_text(texte, encoding="utf-8")
        return chemin

    return _ecrire


def _avec(**modifs: Any) -> dict[str, Any]:
    return {**BASE, **modifs}


def _erreur(chemin: Path) -> ConfigError:
    with pytest.raises(ConfigError) as info:
        load_experiment(chemin)
    return info.value


# --- chargement strict (AC 1, 2, 5) ---


def test_chargement_valide(ecrire: Callable[..., Path]) -> None:
    exp = load_experiment(ecrire(BASE))
    assert isinstance(exp, Experiment)
    assert exp.profile == "cpu"
    assert exp.conditions == ("standard",)
    assert exp.budget.per_run["anthropic"].currency == "USD"


def test_cle_inconnue_dans_params(ecrire: Callable[..., Path]) -> None:
    donnees = _avec(
        configurations=[
            BASE["configurations"][0],
            {"id": "b", "architecture": "arch_test", "params": {"kk": 5}},
        ]
    )
    assert _erreur(ecrire(donnees)).path == "configurations[1].params.kk"


def test_cle_inconnue_dans_composant_imbrique(ecrire: Callable[..., Path]) -> None:
    conf = {
        "id": "a",
        "architecture": "arch_test",
        "params": {"chunker": {"name": "fixed", "params": {"sizee": 1}}},
    }
    assert _erreur(ecrire(_avec(configurations=[conf]))).path == (
        "configurations[0].params.chunker.params.sizee"
    )


def test_cle_inconnue_dans_spec_de_composant(ecrire: Callable[..., Path]) -> None:
    conf = {
        "id": "a",
        "architecture": "arch_test",
        "params": {"chunker": {"name": "fixed", "parms": {}}},
    }
    assert _erreur(ecrire(_avec(configurations=[conf]))).path == (
        "configurations[0].params.chunker.parms"
    )


def test_cle_inconnue_racine_et_configuration(ecrire: Callable[..., Path]) -> None:
    assert _erreur(ecrire(_avec(seeed=1))).path == "seeed"
    conf = {"id": "a", "architecture": "arch_test", "parametres": {}}
    assert _erreur(ecrire(_avec(configurations=[conf]))).path == "configurations[0].parametres"


def test_valeur_mal_typee(ecrire: Callable[..., Path]) -> None:
    assert _erreur(ecrire(_avec(seed="abc"))).path == "seed"
    conf = {"id": "a", "architecture": "arch_test", "params": {"k": "beaucoup"}}
    assert _erreur(ecrire(_avec(configurations=[conf]))).path == "configurations[0].params.k"


def test_architecture_inconnue_liste_les_noms(ecrire: Callable[..., Path]) -> None:
    conf = {"id": "a", "architecture": "naive"}
    err = _erreur(ecrire(_avec(configurations=[conf])))
    assert err.path == "configurations[0].architecture"
    assert "arch_test" in err.message


def test_composant_inconnu(ecrire: Callable[..., Path]) -> None:
    conf = {"id": "a", "architecture": "arch_test", "params": {"store": {"name": "zzz"}}}
    err = _erreur(ecrire(_avec(configurations=[conf])))
    assert err.path == "configurations[0].params.store.name"
    assert "exact" in err.message


def test_balise_python_refusee(ecrire: Callable[..., Path]) -> None:
    texte = "experiment_id: !!python/object/apply:os.getcwd []\nseed: 1\n"
    err = _erreur(ecrire(texte))
    assert "illisible ou YAML invalide" in err.message


def test_yaml_racine_non_dictionnaire(ecrire: Callable[..., Path]) -> None:
    assert "dictionnaire" in _erreur(ecrire("- 1\n- 2\n")).message


def test_id_en_double(ecrire: Callable[..., Path]) -> None:
    confs = [{"id": "a", "architecture": "arch_test"}, {"id": "a", "architecture": "arch_test"}]
    assert _erreur(ecrire(_avec(configurations=confs))).path == "configurations[1].id"


@pytest.mark.parametrize("mauvais", ["Naive", "a_b", "a b", ""])
def test_id_hors_motif(ecrire: Callable[..., Path], mauvais: str) -> None:
    confs = [
        {"id": "ok", "architecture": "arch_test"},
        {"id": mauvais, "architecture": "arch_test"},
    ]
    assert _erreur(ecrire(_avec(configurations=confs))).path == "configurations[1].id"


def test_experiment_id_hors_motif(ecrire: Callable[..., Path]) -> None:
    assert _erreur(ecrire(_avec(experiment_id="Bad Id"))).path == "experiment_id"


# --- résolution (AC 3) ---


def test_resolution_profil_cpu_par_defaut(ecrire: Callable[..., Path]) -> None:
    chemin = ecrire(BASE)
    res = resolve_experiment(load_experiment(chemin), chemin)
    assert res.profile == "cpu"
    conf = res.configurations[0]
    assert conf.params["generator"]["params"]["model"] == "claude-haiku-5-5"
    assert conf.params["generator"]["params"]["max_tokens"] == 512
    assert conf.answer_producers == ("claude-haiku-5-5",)
    assert "claude-haiku-5-5" in conf.models
    assert conf.params["k"] == 5
    assert conf.params["chunker"] == {"name": "fixed", "params": {"size": 300, "overlap": 50}}
    assert res.configurations[1].params["k"] == 3


def test_modele_explicite_prime_sur_le_profil(ecrire: Callable[..., Path]) -> None:
    gen = {"name": "llm_test", "params": {"model": "granite4.2:3b"}}
    conf = {"id": "a", "architecture": "arch_test", "params": {"generator": gen}}
    chemin = ecrire(_avec(configurations=[conf]))
    res = resolve_experiment(load_experiment(chemin), chemin)
    assert res.configurations[0].answer_producers == ("granite4.2:3b",)


def test_embedder_omis_cpu_sentence_transformers(ecrire: Callable[..., Path]) -> None:
    chemin = ecrire(BASE)
    conf = resolve_experiment(load_experiment(chemin), chemin).configurations[0]
    assert conf.params["embedder"] == {
        "name": "sentence_transformers",
        "params": {"model": "multilingual-e5-small"},
    }
    assert "multilingual-e5-small" in conf.models


def test_embedder_omis_profil_test_fake(ecrire: Callable[..., Path]) -> None:
    chemin = ecrire(_avec(profile="test"))
    conf = resolve_experiment(load_experiment(chemin), chemin).configurations[0]
    assert conf.params["embedder"] == {"name": "fake", "params": {"model": "fake-embedder"}}
    assert conf.params["generator"]["params"]["model"] == "fake-llm-a"
    assert conf.answer_producers == ("fake-llm-a",)


def test_embedder_explicite_conserve(ecrire: Callable[..., Path]) -> None:
    emb = {"name": "fake", "params": {"model": "fake-embedder"}}
    conf = {"id": "a", "architecture": "arch_test", "params": {"embedder": emb}}
    chemin = ecrire(_avec(configurations=[conf]))
    res = resolve_experiment(load_experiment(chemin), chemin)
    assert res.configurations[0].params["embedder"]["name"] == "fake"


def test_kind_declare_par_champ(ecrire: Callable[..., Path]) -> None:
    conf = {
        "id": "a",
        "architecture": "arch_test",
        "params": {"alias": {"name": "fixed", "params": {"size": 9}}},
    }
    chemin = ecrire(_avec(configurations=[conf]))
    res = resolve_experiment(load_experiment(chemin), chemin)
    assert res.configurations[0].params["alias"]["params"]["size"] == 9


def test_chemins_relatifs_au_fichier(ecrire: Callable[..., Path], tmp_path: Path) -> None:
    donnees = _avec(scenario="scen.yaml", costs="c.yaml", catalog=None)
    donnees["judges"] = {"excluded_from": "cal.json"}
    (tmp_path / "experiments").mkdir()
    (tmp_path / "experiments" / "c.yaml").write_text(
        "owned_costs: {hardware_price_eur: '999'}\n", encoding="utf-8"
    )
    chemin = ecrire(donnees)
    res = resolve_experiment(load_experiment(chemin), chemin)
    base = (tmp_path / "experiments").resolve()
    assert res.corpus == (base.parent / "corpora/mini/corpus.yaml").as_posix()
    assert res.questions == (base.parent / "corpora/mini/questions.yaml").as_posix()
    assert res.scenario == (base / "scen.yaml").as_posix()
    assert res.judges.excluded_from == (base / "cal.json").as_posix()
    assert str(res.costs.owned_costs.hardware_price_eur) == "999"  # clé `costs:` branchée (1.4)


def test_defauts_juges_et_date_gel(ecrire: Callable[..., Path]) -> None:
    chemin = ecrire(BASE)
    res = resolve_experiment(load_experiment(chemin), chemin)
    assert res.judges.pool == res.profile_settings.defaults.judge_pool
    assert res.judges.panel_size == 2
    assert res.models_frozen_at == res.catalog_date
    pose = ecrire(_avec(models_frozen_at="2026-01-02"))
    assert str(resolve_experiment(load_experiment(pose), pose).models_frozen_at) == "2026-01-02"


# --- sérialisation et empreinte (AC 4) ---


def test_serialisation_et_empreinte(ecrire: Callable[..., Path], tmp_path: Path) -> None:
    chemin = ecrire(BASE)
    res = resolve_experiment(load_experiment(chemin), chemin)
    texte = to_yaml(res)
    lu = yaml.safe_load(texte)
    assert lu["configurations"][0]["params"]["k"] == 5  # défaut écrit
    assert lu["models_frozen_at"] == str(res.models_frozen_at)
    assert lu["costs"]["fx"]["rates_to_eur"]["USD"] == "0.8938"
    assert lu["budget"]["per_run"]["anthropic"]["amount"] == "5.00"
    sortie = tmp_path / "run"
    empreinte = write_resolved(res, sortie)
    assert (sortie / "experiment.resolved.yaml").read_text(encoding="utf-8") == texte
    assert (sortie / "experiment.sha256").read_text(encoding="utf-8").strip() == empreinte
    assert empreinte == fingerprint(res) == fingerprint(res)
    assert len(empreinte) == 64


def test_empreinte_insensible_a_l_ordre_des_cles(ecrire: Callable[..., Path]) -> None:
    a = ecrire(BASE, "experiments/a.yaml")
    inverse = {k: BASE[k] for k in reversed(list(BASE))}
    inverse["configurations"] = [dict(reversed(list(c.items()))) for c in BASE["configurations"]]
    b = ecrire(inverse, "experiments/b.yaml")
    ra = resolve_experiment(load_experiment(a), a)
    rb = resolve_experiment(load_experiment(b), b)
    assert fingerprint(ra) == fingerprint(rb)


def test_empreinte_change_avec_une_valeur(ecrire: Callable[..., Path]) -> None:
    a = ecrire(BASE, "experiments/a.yaml")
    b = ecrire(_avec(seed=43), "experiments/b.yaml")
    assert fingerprint(resolve_experiment(load_experiment(a), a)) != fingerprint(
        resolve_experiment(load_experiment(b), b)
    )
