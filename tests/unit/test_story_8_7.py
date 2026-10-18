"""Story 8.7 : PageIndex sur Mini-CPU ; `select_model` n'est pas un `answer_producer` (AD-14)."""

from pathlib import Path

import yaml

from wavelibrarian.config.defaults import load_profile
from wavelibrarian.config.validate import validate_file

RACINE = Path(__file__).resolve().parents[2]
MINI_CPU = RACINE / "experiments" / "mini-cpu.yaml"


def _pageindex(brut: dict) -> dict:
    return next(c for c in brut["configurations"] if c["id"] == "pageindex")


def test_profil_cpu_sans_penalite_de_repetition() -> None:
    profil = load_profile("cpu")
    assert "repeat_penalty" not in profil.ollama.options
    assert profil.ollama.options["num_gpu"] == 0


def test_mini_cpu_selectionne_avec_granite() -> None:
    brut = yaml.safe_load(MINI_CPU.read_text(encoding="utf-8"))
    assert _pageindex(brut)["params"]["select_model"] == "granite4.2:3b"


def test_select_model_de_la_famille_d_un_juge_ne_change_pas_le_panel() -> None:
    res = validate_file(MINI_CPU)

    def conf(exp):  # type: ignore[no-untyped-def]
        return next(c for c in exp.configurations if c.id == "pageindex")

    # granite4.2:3b est un Juge du réservoir : il ne doit pas écarter ce Juge du Panel de PageIndex.
    assert "granite4.2:3b" not in conf(res.resolved).answer_producers
    assert "granite4.2:3b" in res.panels["pageindex"]
    autres = {p for cid, p in res.panels.items() if cid != "pageindex"}
    assert autres == {res.panels["pageindex"]}
