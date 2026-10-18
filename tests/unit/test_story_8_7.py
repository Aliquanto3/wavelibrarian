"""Story 8.7 : PageIndex sur Mini-CPU ; `select_model` n'est pas un `answer_producer` (AD-14)."""

from pathlib import Path

import yaml

from wavelibrarian.config.defaults import load_profile
from wavelibrarian.config.validate import validate_file

RACINE = Path(__file__).resolve().parents[2]
MINI_CPU = RACINE / "experiments" / "mini-cpu.yaml"


def _pageindex(brut: dict) -> dict:
    return next(c for c in brut["configurations"] if c["id"] == "pageindex")


def test_profil_cpu_penalise_les_repetitions() -> None:
    profil = load_profile("cpu")
    assert profil.ollama.options["repeat_penalty"] == 1.15
    assert profil.ollama.options["num_gpu"] == 0


def test_select_model_de_la_famille_d_un_juge_ne_change_pas_le_panel(tmp_path: Path) -> None:
    brut = yaml.safe_load(MINI_CPU.read_text(encoding="utf-8"))
    brut["corpus"] = str((MINI_CPU.parent / brut["corpus"]).resolve())
    brut["questions"] = str((MINI_CPU.parent / brut["questions"]).resolve())
    res_avant = validate_file(MINI_CPU)
    avant = res_avant.resolved
    # granite4.2:3b est un Juge du réservoir : il ne doit pas écarter ce Juge du Panel de PageIndex.
    _pageindex(brut)["params"]["select_model"] = "granite4.2:3b"
    fichier = tmp_path / "essai.yaml"
    fichier.write_text(yaml.safe_dump(brut, allow_unicode=True), encoding="utf-8")
    res_apres = validate_file(fichier)
    apres = res_apres.resolved
    assert res_apres.panels == res_avant.panels

    def conf(exp):  # type: ignore[no-untyped-def]
        return next(c for c in exp.configurations if c.id == "pageindex")

    assert conf(apres).answer_producers == conf(avant).answer_producers
    assert "granite4.2:3b" not in conf(apres).answer_producers
