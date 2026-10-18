"""Tests de la validation statique et du Panel (story 1.6)."""

import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Annotated, Any, ClassVar

import pytest
import yaml
from pydantic import BaseModel, ConfigDict
from typer.testing import CliRunner

from wavelibrarian import registry
from wavelibrarian.cli import app
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.load import load_experiment
from wavelibrarian.config.panel import closed_book_judge, excluded_judges, form_panel
from wavelibrarian.config.validate import validate_experiment, validate_file
from wavelibrarian.core.errors import ConfigError, ValidationFailed
from wavelibrarian.core.types import ModelRefMeta
from wavelibrarian.ports.architecture import ArchCapabilities
from wavelibrarian.ports.components import ComponentSpec, StoreCapabilities


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@pytest.fixture(autouse=True)
def composants_de_test() -> Iterator[None]:
    """Enregistre des Composants de test, puis restaure le registre."""
    sauve = dict(registry._REGISTRE)
    decouvert = registry._decouvert
    registry._REGISTRE.clear()  # les Composants livrés ne se mêlent pas à ceux du test
    modules = set(sys.modules)
    registry._decouvert = True

    @registry.register("vector_store", "plain")
    class Plain:
        """Store non hybride."""

        capabilities: ClassVar[StoreCapabilities] = StoreCapabilities(hybrid=False)

        class Params(_Params):
            pass

    @registry.register("vector_store", "hybrid")
    class Hybrid:
        """Store hybride."""

        capabilities: ClassVar[StoreCapabilities] = StoreCapabilities(hybrid=True)

        class Params(_Params):
            pass

    @registry.register("embedder", "fake")
    class FakeEmb:
        """Faux embedder."""

        class Params(_Params):
            model: Annotated[str | None, ModelRefMeta("embedder")] = None

    @registry.register("generator", "llm_test")
    class Gen:
        """Generator de test."""

        class Params(_Params):
            model: Annotated[str | None, ModelRefMeta("generator_models[0]", True)] = None

    @registry.register("judge", "judge_test")
    class Jug:
        """Juge de test."""

        class Params(_Params):
            model: Annotated[str | None, ModelRefMeta("judge_pool[0]")] = None

    class ParamsArch(_Params):
        store: ComponentSpec = ComponentSpec(name="plain")
        embedder: ComponentSpec | None = None
        generator: ComponentSpec = ComponentSpec(name="llm_test")
        judge: ComponentSpec | None = None

    @registry.register("architecture", "simple")
    class Simple:
        """Architecture sans exigence."""

        capabilities: ClassVar[ArchCapabilities] = ArchCapabilities()
        Params = ParamsArch

    @registry.register("architecture", "hybride")
    class ArchHybride:
        """Architecture qui exige un store hybride."""

        capabilities: ClassVar[ArchCapabilities] = ArchCapabilities(requires_hybrid_store=True)
        Params = ParamsArch

    @registry.register("architecture", "cag")
    class Cag:
        """Architecture qui exige le cache de prompt."""

        capabilities: ClassVar[ArchCapabilities] = ArchCapabilities(requires_prompt_cache=True)
        Params = ParamsArch

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
    "profile": "test",
    "corpus": "c.yaml",
    "questions": "q.yaml",
    "configurations": [{"id": "a", "architecture": "simple"}],
}


@pytest.fixture
def ecrire(tmp_path: Path) -> Callable[..., Path]:
    def _ecrire(donnees: dict[str, Any], nom: str = "exp.yaml") -> Path:
        chemin = tmp_path / nom
        chemin.write_text(yaml.safe_dump(donnees, sort_keys=False), encoding="utf-8")
        return chemin

    return _ecrire


def _conf(id_: str, architecture: str = "simple", **params: Any) -> dict[str, Any]:
    return {"id": id_, "architecture": architecture, "params": params}


def _echec(chemin: Path, wl_home: Path) -> ValidationFailed:
    with pytest.raises(ValidationFailed) as info:
        validate_file(chemin, wl_home)
    return info.value


def _chemins(echec: ValidationFailed) -> list[str]:
    return [e.path for e in echec.errors]


# --- AC 1 : regroupement ---


def test_trois_defauts_en_une_erreur(ecrire: Callable[..., Path], wl_home: Path) -> None:
    chemin = ecrire(
        {
            **BASE,
            "configurations": [
                _conf("a", store={"name": "inexistant"}),
                _conf("b", generator={"name": "llm_test", "params": {"model": "ghost"}}),
                _conf("c", "hybride"),
            ],
        }
    )
    echec = _echec(chemin, wl_home)
    assert _chemins(echec) == [
        "configurations[0].params.store.name",
        "configurations[1].params.generator.params.model",
        "configurations[2].params.store",
    ]
    assert "inexistant" in echec.errors[0].message
    assert "ghost" in echec.errors[1].message
    assert "hybrid: false" in echec.errors[2].message


def test_plusieurs_defauts_dans_une_meme_configuration(
    ecrire: Callable[..., Path], wl_home: Path
) -> None:
    chemin = ecrire(
        {
            **BASE,
            "configurations": [
                _conf(
                    "a",
                    "hybride",
                    store={"name": "plain"},
                    generator={"name": "llm_test", "params": {"model": "ghost"}},
                    judge={"name": "judge_test", "params": {"model": "ghost-2"}},
                ),
                {"id": "b", "architecture": "inconnue"},
            ],
        }
    )
    echec = _echec(chemin, wl_home)
    assert sorted(_chemins(echec)) == sorted(
        [
            "configurations[0].params.store",
            "configurations[0].params.generator.params.model",
            "configurations[0].params.judge.params.model",
            "configurations[1].architecture",
        ]
    )


def test_params_inconnus_agreges_avec_le_reste(ecrire: Callable[..., Path], wl_home: Path) -> None:
    chemin = ecrire(
        {**BASE, "configurations": [_conf("a", kk=1), _conf("b", "hybride")]},
    )
    echec = _echec(chemin, wl_home)
    assert _chemins(echec) == ["configurations[0].params.kk", "configurations[1].params.store"]
    # `load_experiment` reste strict par défaut : il s'arrête à la première erreur.
    with pytest.raises(ConfigError, match=r"configurations\[0\]\.params\.kk"):
        load_experiment(chemin)


def test_erreur_de_schema_devient_validation_failed(
    ecrire: Callable[..., Path], wl_home: Path
) -> None:
    echec = _echec(ecrire({**BASE, "seed": "42"}), wl_home)
    assert _chemins(echec) == ["seed"]


def test_experience_valide(ecrire: Callable[..., Path], wl_home: Path) -> None:
    res = validate_file(
        ecrire({**BASE, "configurations": [_conf("a", "hybride", store={"name": "hybrid"})]}),
        wl_home,
    )
    assert res.resolved.configurations[0].id == "a"
    assert res.panels == {"a": ("fake-llm-c", "fake-llm-b")}  # profil test : réservoir c, b, a


# --- AC 2 : cache de prompt ---


def test_cache_de_prompt_non_satisfait(
    ecrire: Callable[..., Path], tmp_path: Path, wl_home: Path
) -> None:
    catalogue = yaml.safe_load(
        (Path(__file__).parents[3] / "src/wavelibrarian/defaults/models.yaml").read_text("utf-8")
    )
    for m in catalogue["models"]:
        if m["id"] == "fake-llm-a":
            m["prompt_cache"] = False
    (tmp_path / "models.yaml").write_text(yaml.safe_dump(catalogue), encoding="utf-8")
    donnees = {**BASE, "catalog": "models.yaml", "configurations": [_conf("a", "cag")]}
    echec = _echec(ecrire(donnees), wl_home)
    assert len(echec.errors) == 1
    assert "fake-llm-a" in echec.errors[0].message
    assert "prompt_cache: false" in echec.errors[0].message
    # Avec un Generator dont le cache est déclaré, la Configuration passe.
    ok = {
        **BASE,
        "catalog": "models.yaml",
        "configurations": [
            _conf("a", "cag", generator={"name": "llm_test", "params": {"model": "fake-llm-b"}})
        ],
    }
    assert validate_file(ecrire(ok, "ok.yaml"), wl_home).resolved.configurations[0].id == "a"


# --- AC 3 : index réutilisé ---


def _manifeste(wl_home: Path, cle: str, contenu: dict[str, Any]) -> None:
    dossier = wl_home / "index" / cle
    dossier.mkdir(parents=True)
    (dossier / "manifest.json").write_text(json.dumps(contenu), encoding="utf-8")


def _reuse(cle: str) -> dict[str, Any]:
    return {
        **BASE,
        "configurations": [{**_conf("a", embedder={"name": "fake"}), "reuse_index": cle}],
    }


def test_index_de_dimension_incompatible(ecrire: Callable[..., Path], wl_home: Path) -> None:
    _manifeste(wl_home, "k1", {"index_key": "k1", "embedder_dim": 384})
    echec = _echec(ecrire(_reuse("k1")), wl_home)
    assert _chemins(echec) == ["configurations[0].reuse_index"]
    assert "384" in echec.errors[0].message
    assert "64" in echec.errors[0].message


def test_index_de_meme_dimension_accepte(ecrire: Callable[..., Path], wl_home: Path) -> None:
    _manifeste(wl_home, "k2", {"index_key": "k2", "embedder_dim": 64})
    validate_file(ecrire(_reuse("k2")), wl_home)


def test_index_sans_embedder_dim_accepte(ecrire: Callable[..., Path], wl_home: Path) -> None:
    _manifeste(wl_home, "k3", {"index_key": "k3"})
    validate_file(ecrire(_reuse("k3")), wl_home)


def test_index_introuvable_ou_cle_invalide(ecrire: Callable[..., Path], wl_home: Path) -> None:
    echec = _echec(ecrire(_reuse("absent")), wl_home)
    assert "illisible" in echec.errors[0].message
    echec = _echec(ecrire(_reuse("../x")), wl_home)
    assert "invalide" in echec.errors[0].message


def test_wl_home_pris_dans_l_environnement(ecrire: Callable[..., Path], wl_home: Path) -> None:
    _manifeste(wl_home, "k1", {"embedder_dim": 384})
    chemin = ecrire(_reuse("k1"))
    with pytest.raises(ValidationFailed):
        validate_file(chemin)  # WL_HOME fixé par la fixture


# --- AC 4 : Panel ---

POOL = ["fake-llm-a", "fake-llm-b", "fake-llm-c"]


def test_form_panel_ordre_declare_et_famille() -> None:
    catalogue = load_catalog()
    assert form_panel(POOL, 2, ["fake-llm-a"], catalogue) == ("fake-llm-b", "fake-llm-c")
    assert form_panel(POOL, 2, [], catalogue) == ("fake-llm-a", "fake-llm-b")
    assert form_panel(POOL, 5, ["fake-llm-a"], catalogue) == ("fake-llm-b", "fake-llm-c")


def test_form_panel_exclusion_par_calibration_et_minimum() -> None:
    catalogue = load_catalog()
    with pytest.raises(ConfigError, match="minimum 2") as info:
        form_panel(POOL, 2, ["fake-llm-a"], catalogue, excluded={"fake-llm-c"})
    assert info.value.path == "judges.pool"
    with pytest.raises(ConfigError):
        form_panel(POOL, 1, [], catalogue)  # un Panel d'un seul Juge est refusé


def test_panel_refuse_par_la_validation(
    ecrire: Callable[..., Path], tmp_path: Path, wl_home: Path
) -> None:
    (tmp_path / "calibration.json").write_text(
        json.dumps(
            {
                "judges": {
                    "fake-llm-c": {"excluded": True, "criteria": {"correctness": {"kappa": 0.2}}},
                    "fake-llm-b": {"excluded": False},
                }
            }
        ),
        encoding="utf-8",
    )
    juges = {"pool": POOL, "panel_size": 2}
    ok = validate_file(ecrire({**BASE, "judges": juges}), wl_home)
    assert ok.panels == {"a": ("fake-llm-b", "fake-llm-c")}
    refus = _echec(
        ecrire({**BASE, "judges": {**juges, "excluded_from": "calibration.json"}}, "e2.yaml"),
        wl_home,
    )
    assert _chemins(refus) == ["judges.pool"]
    assert "'a'" in refus.errors[0].message


def test_calibration_illisible(tmp_path: Path) -> None:
    (tmp_path / "c.json").write_text("{pas du json", encoding="utf-8")
    with pytest.raises(ConfigError, match="illisible"):
        excluded_judges(tmp_path / "c.json")
    (tmp_path / "d.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError, match="judges"):
        excluded_judges(tmp_path / "d.json")


def test_pool_avec_modele_inconnu(ecrire: Callable[..., Path], wl_home: Path) -> None:
    echec = _echec(ecrire({**BASE, "judges": {"pool": ["fake-llm-b", "ghost"]}}), wl_home)
    assert _chemins(echec) == ["judges.pool[1]"]


def test_juge_explicite_de_la_famille_du_generator(
    ecrire: Callable[..., Path], wl_home: Path
) -> None:
    mauvais = _conf("a", judge={"name": "judge_test", "params": {"model": "fake-llm-a"}})
    echec = _echec(ecrire({**BASE, "configurations": [mauvais]}), wl_home)
    assert _chemins(echec) == ["configurations[0].params.judge.params.model"]
    assert "fake-a" in echec.errors[0].message
    bon = _conf("a", judge={"name": "judge_test", "params": {"model": "fake-llm-b"}})
    validate_file(ecrire({**BASE, "configurations": [bon]}, "ok.yaml"), wl_home)


# --- AC 5 : Juge closed-book ---


def test_closed_book_judge() -> None:
    catalogue = load_catalog()
    assert closed_book_judge("fake-llm-a", POOL, catalogue) == "fake-llm-b"
    assert closed_book_judge("fake-llm-b", POOL, catalogue) == "fake-llm-a"
    with pytest.raises(ConfigError, match="aucun Juge closed-book"):
        closed_book_judge("fake-llm-a", ["fake-llm-a"], catalogue)


# --- AC 6 : CLI ---


def test_cli_experience_invalide(
    ecrire: Callable[..., Path], wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chemin = ecrire({**BASE, "configurations": [_conf("a", "hybride"), _conf("b", kk=1)]})
    res = CliRunner().invoke(app, ["run", str(chemin)])
    assert res.exit_code == 2
    assert "Expérience invalide : 2 erreur(s)" in res.output
    assert "configurations[0].params.store" in res.output
    assert "configurations[1].params.kk" in res.output
    assert "Validation réussie" not in res.output


def test_cli_experience_valide(
    ecrire: Callable[..., Path], wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from wavelibrarian import cli

    # Validation seule : l'Exécution (story 4.4) est testée dans `test_story_4_4.py`.
    issue = SimpleNamespace(
        run_id="r", status="completed", n_answers=0, run_dir=wl_home, all_failed=False
    )
    monkeypatch.setattr(cli, "load_questions", lambda _r: None)
    monkeypatch.setattr(cli, "run_experiment", lambda *_a, **_k: issue)
    res = CliRunner().invoke(app, ["run", str(ecrire(BASE))])
    assert res.exit_code == 0
    assert "Validation réussie" in res.output


def test_cli_fichier_absent(tmp_path: Path, wl_home: Path) -> None:
    res = CliRunner().invoke(app, ["run", str(tmp_path / "absent.yaml")])
    assert res.exit_code == 2
    assert "illisible" in res.output


def test_validate_experiment_sur_objet(ecrire: Callable[..., Path], wl_home: Path) -> None:
    chemin = ecrire(BASE)
    exp = load_experiment(chemin)
    assert validate_experiment(exp, chemin, wl_home).panels


# --- Revue : agrégation complète, calibration stricte, juge de calibration ---


def test_cles_inconnues_multiples_et_defauts_imbriques_agreges(
    ecrire: Callable[..., Path], wl_home: Path
) -> None:
    gen = {"name": "llm_test", "params": {"model": "ghost", "zz": 0}}
    chemin = ecrire({**BASE, "configurations": [_conf("a", kk=1, kk2=2, generator=gen)]})
    assert sorted(_chemins(_echec(chemin, wl_home))) == [
        "configurations[0].params.generator.params.model",
        "configurations[0].params.generator.params.zz",
        "configurations[0].params.kk",
        "configurations[0].params.kk2",
    ]


def test_calibration_excluded_doit_etre_booleen(tmp_path: Path) -> None:
    fichier = tmp_path / "cal.json"
    fichier.write_text('{"judges": {"fake-llm-c": {"excluded": "true"}}}', encoding="utf-8")
    with pytest.raises(ConfigError, match=r"judges\.fake-llm-c\.excluded"):
        excluded_judges(fichier)
    fichier.write_text(
        '{"judges": {"fake-llm-c": {"excluded": true, "criteria": {}}, '
        '"fake-llm-b": {"excluded": false}}, "inter_annotator": {}}',
        encoding="utf-8",
    )
    assert excluded_judges(fichier) == {"fake-llm-c"}


def test_juge_de_calibration_absent_du_catalogue(
    ecrire: Callable[..., Path], wl_home: Path
) -> None:
    chemin = ecrire({**BASE, "judges": {"calibration_judge": "ghost-cal"}})
    echec = _echec(chemin, wl_home)
    assert _chemins(echec) == ["judges.calibration_judge"]
    assert "ghost-cal" in echec.errors[0].message
