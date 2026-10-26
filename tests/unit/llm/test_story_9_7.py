"""Story 9.7 : prompt du Decider sans score soufflé, Cache isolé par Configuration (sans réseau)."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from wavelibrarian.components.deciders.llm import SYSTEM
from wavelibrarian.config.catalog import load_catalog
from wavelibrarian.config.defaults import load_profile
from wavelibrarian.config.experiment import Experiment, LlmCacheSettings
from wavelibrarian.config.resolve import fingerprint
from wavelibrarian.config.validate import validate_file
from wavelibrarian.llm.cache import cache_key, role_marker
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.gateway import LLMRequest, Message
from wavelibrarian.runner.context import Context

EXPERIENCES = Path(__file__).resolve().parents[3] / "experiments"

SYSTEM_FIGE = (
    "Pour chaque passage numéroté, donne un score de pertinence entre 0 (sans rapport) et 1 "
    "(répond directement) au regard de la question. Réponds en JSON, un score par passage, dans "
    "l'ordre reçu : "
    '{"scores": [<score du passage 1>, <score du passage 2>, ...]}.'
)


def test_prompt_du_decider_fige_et_exemple_sans_valeur_numerique() -> None:
    assert SYSTEM == SYSTEM_FIGE
    exemple = SYSTEM[SYSTEM.index('{"scores"') :]
    # Les seuls chiffres de l'exemple sont les numéros de passage, aucun score (constat 8.8 c).
    assert re.findall(r"\d+(?:\.\d+)?", exemple) == ["1", "2"]
    assert "0.0" not in SYSTEM


def _requete() -> LLMRequest:
    return LLMRequest(
        model_id="fake-llm-a",
        role="grade_relevance",
        step="s",
        system=role_marker("grade_relevance") + "sys",
        messages=(Message(role="user", content="Q"),),
        max_tokens=64,
        seed=7,
    )


def test_cle_inchangee_sans_portee_valeurs_litterales() -> None:
    # Valeurs calculées avant la story 9.7 : sans `scope`, la clé ne bouge pas.
    r = _requete()
    avec_options = cache_key(r, "ollama", {"type": "object"}, {"num_ctx": 4096})
    assert avec_options == "3c932136cb864f5288bc9485e8aac7de91567c94faa648036e082f7c594a3709"
    assert cache_key(r, "fake") == (
        "5c96826532ef5a095052b7a6fc2c13f2bc095bd994db83e068fa50e7fa1db7b9"
    )
    assert cache_key(r, "fake", scope=None) == cache_key(r, "fake")


def test_cle_differe_selon_la_configuration() -> None:
    r = _requete()
    a, b = cache_key(r, "fake", scope="cfg-a"), cache_key(r, "fake", scope="cfg-b")
    assert len({a, b, cache_key(r, "fake")}) == 3


class _Env:
    def __init__(self, wl_home: Path, isoler: bool) -> None:
        self.appels: list[str] = []
        self.provider = FakeProvider()
        self.provider.script("generate", "*", self._appel)
        self.ctx = Context(
            profile=load_profile("test"),
            catalog=load_catalog(),
            wl_home=wl_home,
            run_id="r-1",
            providers={"fake": self.provider},
            isoler_configurations=isoler,
        )

    def _appel(self, req: LLMRequest) -> str:
        self.appels.append(self.ctx.config_id)
        return "ok"

    def appeler(self, config_id: str):  # type: ignore[no-untyped-def]
        self.ctx.config_id = config_id
        req = LLMRequest(
            model_id="fake-llm-a",
            role="generate",
            step="generate",
            system="Réponds.",
            messages=(Message(role="user", content="Capitale ?"),),
            max_tokens=50,
            inputs={"question": "q", "blocks": {}},
        )
        with self.ctx.scope(post="query"):
            return self.ctx.gateway.complete(req)


def test_isolation_deux_configurations_paient_et_mesurent_chacune(tmp_path: Path) -> None:
    env = _Env(tmp_path / "wl", isoler=True)
    with env.ctx:
        r1, r2 = env.appeler("cfg-a"), env.appeler("cfg-b")
        r3 = env.appeler("cfg-a")
    assert env.appels == ["cfg-a", "cfg-b"]  # chacune a appelé : pas de rejeu entre elles
    assert (r1.from_cache, r2.from_cache) == (False, False)
    assert r3.from_cache is True  # même Configuration : le Cache joue toujours


def test_sans_isolation_les_configurations_partagent_le_cache(tmp_path: Path) -> None:
    env = _Env(tmp_path / "wl", isoler=False)
    with env.ctx:
        r1, r2 = env.appeler("cfg-a"), env.appeler("cfg-b")
    assert env.appels == ["cfg-a"]
    assert (r1.from_cache, r2.from_cache) == (False, True)


def test_llm_cache_defaut_faux_et_champ_strict() -> None:
    assert LlmCacheSettings().isoler_configurations is False
    assert Experiment.model_fields["llm_cache"].default == LlmCacheSettings()
    with pytest.raises(ValidationError):
        LlmCacheSettings(isoler_configurations="oui")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        LlmCacheSettings(isoler=True)  # type: ignore[call-arg]


def test_experience_lazy_seuil_cpu(wl_home: Path) -> None:
    res = validate_file(EXPERIENCES / "lazy-seuil-cpu.yaml", wl_home)
    r = res.resolved
    assert r.llm_cache.isoler_configurations is True
    seuils = {c.id: c.params["relevance_threshold"] for c in r.configurations}
    assert seuils == {"lazy-seuil-01": 0.1, "lazy-seuil-03": 0.3, "lazy-seuil-05": 0.5}
    assert {c.params["decider"]["params"]["model"] for c in r.configurations} == {"granite4.2:3b"}
    # Option ordinaire : elle entre dans l'empreinte (une reprise ne peut pas la changer).
    autre = r.model_copy(update={"llm_cache": LlmCacheSettings()})
    assert fingerprint(autre) != fingerprint(r)
