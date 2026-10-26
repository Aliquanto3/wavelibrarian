"""Story 9.1 : `wl calibrer` écrit ses verdicts au fil de l'eau (SDK factice, aucun réseau)."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
import yaml
from typer.testing import CliRunner

import wavelibrarian.runner.calibrer as module_calibrer
from wavelibrarian.cli import app
from wavelibrarian.components.judges import llm as juge_llm
from wavelibrarian.config.validate import validate_file
from wavelibrarian.core.errors import ConfigError, ProviderError
from wavelibrarian.evalset import io
from wavelibrarian.evalset.freeze import select_questions
from wavelibrarian.llm.providers.anthropic import AnthropicProvider
from wavelibrarian.runner.calibrer import calibrer, fichier_verdicts
from wavelibrarian.runner.rundir import read_answers
from wavelibrarian.scoring.panel import criteres_juges

RACINE = Path(__file__).resolve().parents[3]
MINI = RACINE / "corpora" / "minicorpus"
JUGES = ["claude-haiku-5-5", "claude-opus-5-5"]
PASSES = 2


def _experience(tmp_path: Path, claude: bool = True) -> Path:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-9-1",
        "seed": 42,
        "profile": "test",
        "corpus": str(MINI / "corpus.yaml"),
        "questions": str(MINI / "questions.yaml"),
        "split": "dev",
        "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
        "configurations": [{"id": "bm25", "architecture": "bm25_only"}],
    }
    if claude:  # sans Juges Claude, l'Exécution annotée se joue sans clé
        donnees["judges"] = {"pool": JUGES, "panel_size": 2, "calibration_passes": PASSES}
        donnees["budget"] = {"per_run": {"anthropic": {"amount": "10.00", "currency": "USD"}}}
    chemin = tmp_path / ("exp.yaml" if claude else "exp-run.yaml")
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    return chemin


def _annoter(dossier: Path, cible: Path, inverser_premiere: bool = False) -> None:
    questions = {q.id: q for q in select_questions(io.load(MINI / "questions.yaml"), "dev")}
    lignes = [
        {"answer_id": a.answer_id, "criterion": c, "verdict": "yes"}
        for a in sorted(read_answers(dossier).values(), key=lambda a: a.answer_id)
        for c in criteres_juges(questions[a.question_id])
    ]
    if inverser_premiere:
        lignes[0]["verdict"] = "no"
    cible.mkdir(exist_ok=True)
    texte = yaml.safe_dump({"annotator": "anael", "annotations": lignes}, allow_unicode=True)
    (cible / "anael.yaml").write_text(texte, encoding="utf-8")


class _Sdk:
    """Remplace `anthropic.Anthropic` : `yes` à tout Critère ; HTTP 400 (non réessayable) au
    `echec_au`-ième appel (1 pour le premier)."""

    def __init__(self, echec_au: int | None = None, interrompre: bool = False) -> None:
        self.appels: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)
        self._echec_au = echec_au
        self._interrompre = interrompre

    def _create(self, **corps: Any) -> Any:
        self.appels.append(corps)
        if self._echec_au is not None and len(self.appels) == self._echec_au:
            if self._interrompre:
                raise KeyboardInterrupt
            requete = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.BadRequestError(
                "requête refusée", response=httpx2.Response(400, request=requete), body=None
            )
        entree = json.loads(corps["messages"][0]["content"])
        verdicts = {c: {"verdict": "yes", "justification": "ok"} for c in entree["criteria"]}
        usage = SimpleNamespace(
            input_tokens=100,
            output_tokens=30,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        bloc = SimpleNamespace(type="tool_use", input={"verdicts": verdicts})
        return SimpleNamespace(content=[bloc], usage=usage, stop_reason="tool_use")


@pytest.fixture
def execution(tmp_path: Path, wl_home: Path) -> tuple[Path, Path]:
    res = CliRunner().invoke(app, ["run", str(_experience(tmp_path, claude=False))])
    assert res.exit_code == 0, res.output
    (dossier,) = [d for d in (wl_home / "runs").iterdir() if d.is_dir()]
    _annoter(dossier, tmp_path / "ann")
    return _experience(tmp_path), dossier


def _cli(
    monkeypatch: pytest.MonkeyPatch,
    sdk: _Sdk,
    exp: Path,
    tmp_path: Path,
    run: str,
    *args: str,
) -> Any:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "cle-factice")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **_kw: sdk)
    return CliRunner().invoke(
        app, ["calibrer", str(exp), "--annotations", str(tmp_path / "ann"), "--run", run, *args]
    )


def _lire(chemin: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in chemin.read_text("utf-8").splitlines()]


def _sans_date(chemin: Path) -> dict[str, Any]:
    donnees = json.loads(chemin.read_text("utf-8"))
    donnees.pop("created_at")
    return donnees


def test_verdicts_ecrits_et_vides_a_chaque_appel(
    execution: tuple[Path, Path],
    tmp_path: Path,
    wl_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """À chaque `fsync`, le fichier contient déjà la ligne de l'appel qui vient de rendre."""
    _, dossier = execution
    exp = validate_file(_experience(tmp_path)).resolved
    sdk = _Sdk()
    fichier = dossier / "calibration_verdicts.jsonl"
    vus: list[int] = []
    reel = os.fsync

    def fsync(fd: int) -> None:
        if fichier.exists():
            vus.append(len(fichier.read_text("utf-8").splitlines()))
        reel(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    res, _ = calibrer(
        exp,
        tmp_path / "ann",
        dossier.name,
        wl_home=wl_home,
        providers={"anthropic": AnthropicProvider(client=sdk)},  # type: ignore[arg-type]
    )
    n = len(read_answers(dossier)) * len(JUGES) * PASSES
    assert res.n_appels == n and len(sdk.appels) == n
    assert vus[:n] == list(range(1, n + 1))  # la ligne i est sur disque au i-ème appel
    lignes = _lire(fichier)
    assert len(lignes) == n  # une ligne par (Juge, Réponse, passe)
    assert len({(x["judge_model"], x["answer_id"], x["pass_id"]) for x in lignes}) == n
    premiere = lignes[0]
    assert set(premiere) == {
        "answer_id",
        "judge_model",
        "pass_id",
        "empreinte",
        "calibration_id",
        "verdicts",
    }
    assert all(
        set(v) == {"verdict", "justification"} and v["verdict"] is True
        for v in premiere["verdicts"].values()
    )


def test_erreur_fournisseur_au_5e_appel_garde_4_verdicts_et_la_reprise_n_appelle_que_le_reste(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    fichier = dossier / "calibration_verdicts.jsonl"
    sdk = _Sdk(echec_au=5)
    res = _cli(monkeypatch, sdk, exp, tmp_path, dossier.name)
    assert res.exit_code == 4, res.output
    assert "4 verdict(s) conservé(s)" in res.output
    assert "calibration_verdicts.jsonl" in res.output
    assert f"--run {dossier.name} --reprendre" in res.output
    assert len(sdk.appels) == 5
    assert not (dossier / "calibration.json").exists()
    avant = _lire(fichier)
    assert len(avant) == 4  # relus du fichier

    sdk2 = _Sdk()
    res = _cli(monkeypatch, sdk2, exp, tmp_path, dossier.name, "--reprendre")
    assert res.exit_code == 0, res.output
    total = len(read_answers(dossier)) * len(JUGES) * PASSES
    assert len(sdk2.appels) == total - 4
    lignes = _lire(fichier)
    assert lignes[:4] == avant  # les verdicts déjà reçus ne sont pas réécrits
    assert len({(x["judge_model"], x["answer_id"], x["pass_id"]) for x in lignes}) == total

    # calibration.json calculé sur l'ensemble = celui d'une calibration sans interruption.
    complet = tmp_path / "complet" / "calibration.json"
    res = _cli(monkeypatch, _Sdk(), exp, tmp_path, dossier.name, "--sortie", str(complet))
    assert res.exit_code == 0, res.output
    assert _sans_date(dossier / "calibration.json") == _sans_date(complet)


def test_plafond_atteint_code_3_message_nombre_et_commande_de_reprise(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    donnees = yaml.safe_load(exp.read_text("utf-8"))
    donnees["budget"]["per_run"]["anthropic"]["amount"] = "0.01"
    serre = tmp_path / "serre.yaml"
    serre.write_text(yaml.safe_dump(donnees), encoding="utf-8")
    sortie = tmp_path / "sortie" / "cal.json"
    res = _cli(monkeypatch, _Sdk(), serre, tmp_path, dossier.name, "--sortie", str(sortie))
    assert res.exit_code == 3, res.output
    n = len(_lire(fichier_verdicts(sortie))) if fichier_verdicts(sortie).exists() else 0
    assert f"{n} verdict(s) conservé(s)" in res.output
    assert f"--sortie {sortie} --reprendre" in res.output
    assert not sortie.exists()


def test_fichier_existant_refuse_sans_reprendre_ni_ecraser(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    fichier = dossier / "calibration_verdicts.jsonl"
    res = _cli(monkeypatch, _Sdk(echec_au=3), exp, tmp_path, dossier.name)
    assert res.exit_code == 4
    avant = fichier.read_bytes()
    sdk = _Sdk()
    res = _cli(monkeypatch, sdk, exp, tmp_path, dossier.name)
    assert res.exit_code == 2 and "--reprendre" in res.output and "--ecraser" in res.output
    assert not sdk.appels and fichier.read_bytes() == avant  # rien appelé, rien perdu

    res = _cli(monkeypatch, sdk, exp, tmp_path, dossier.name, "--reprendre", "--ecraser")
    assert res.exit_code == 2 and "incompatible" in res.output and not sdk.appels

    res = _cli(monkeypatch, sdk, exp, tmp_path, dossier.name, "--ecraser")
    assert res.exit_code == 0, res.output
    total = len(read_answers(dossier)) * len(JUGES) * PASSES
    # Tout est rappelé ; le Cache de réponses sert au plus les 2 passes 0 déjà reçues.
    assert total - 2 <= len(sdk.appels) <= total
    assert len(_lire(fichier)) == total


def test_reprise_refusee_si_les_annotations_ont_change(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    res = _cli(monkeypatch, _Sdk(echec_au=3), exp, tmp_path, dossier.name)
    assert res.exit_code == 4
    _annoter(dossier, tmp_path / "ann", inverser_premiere=True)
    sdk = _Sdk()
    res = _cli(monkeypatch, sdk, exp, tmp_path, dossier.name, "--reprendre")
    assert res.exit_code == 2 and "empreinte différente" in res.output
    assert not sdk.appels


def test_reprise_refusee_pour_une_autre_experience(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    res = _cli(monkeypatch, _Sdk(echec_au=3), exp, tmp_path, dossier.name)
    assert res.exit_code == 4
    donnees = yaml.safe_load(exp.read_text("utf-8"))
    donnees["experiment_id"] = "exp-9-1-bis"
    autre = tmp_path / "autre.yaml"
    autre.write_text(yaml.safe_dump(donnees), encoding="utf-8")
    res = _cli(monkeypatch, _Sdk(), autre, tmp_path, dossier.name, "--reprendre")
    assert res.exit_code == 2 and "empreinte différente" in res.output


def test_reprise_ecarte_une_derniere_ligne_tronquee_et_rappelle_les_verdicts_manquants(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    fichier = dossier / "calibration_verdicts.jsonl"
    res = _cli(monkeypatch, _Sdk(echec_au=4), exp, tmp_path, dossier.name)
    assert res.exit_code == 4
    lignes = _lire(fichier)
    assert len(lignes) == 3
    # Un verdict manquant est rappelé ; une ligne coupée par un arrêt brutal est écartée.
    manquant = {k: v for k, v in lignes[2].items() if k != "verdicts"}
    manquant.update(missing=True, error="sortie non conforme")
    texte = "".join(json.dumps(x) + "\n" for x in [*lignes[:2], manquant])
    fichier.write_text(texte + '{"answer_id": "tronq', encoding="utf-8")
    sdk = _Sdk()
    res = _cli(monkeypatch, sdk, exp, tmp_path, dossier.name, "--reprendre")
    assert res.exit_code == 0, res.output
    total = len(read_answers(dossier)) * len(JUGES) * PASSES
    # 2 triplets déjà notés ne sont pas rappelés ; le Cache sert au plus le « manquant » (reçu).
    assert total - 3 <= len(sdk.appels) <= total - 2
    reçus = [x for x in _lire(fichier) if "verdicts" in x]
    assert len({(x["judge_model"], x["answer_id"], x["pass_id"]) for x in reçus}) == total


def test_ligne_illisible_au_milieu_est_une_erreur_de_configuration(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path
) -> None:
    _, dossier = execution
    (dossier / "calibration_verdicts.jsonl").write_text("pas du json\n{}\n", encoding="utf-8")
    exp = validate_file(_experience(tmp_path)).resolved
    with pytest.raises(ConfigError, match="ligne 1 illisible"):
        calibrer(exp, tmp_path / "ann", dossier.name, wl_home=wl_home, reprendre=True)


def test_exception_porte_le_nombre_de_verdicts_recus(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path
) -> None:
    _, dossier = execution
    exp = validate_file(_experience(tmp_path)).resolved
    with pytest.raises(ProviderError) as e:
        calibrer(
            exp,
            tmp_path / "ann",
            dossier.name,
            wl_home=wl_home,
            providers={"anthropic": AnthropicProvider(client=_Sdk(echec_au=6))},  # type: ignore[arg-type]
        )
    assert getattr(e.value, "verdicts_recus") == 5  # noqa: B009
    assert getattr(e.value, "fichier_verdicts") == dossier / "calibration_verdicts.jsonl"  # noqa: B009


def test_reprise_refusee_si_le_prompt_des_juges_a_change(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un prompt modifié entre deux tentatives mêlerait deux prompts : reprise refusée (code 2)."""
    exp, dossier = execution
    fichier = dossier / "calibration_verdicts.jsonl"
    res = _cli(monkeypatch, _Sdk(echec_au=3), exp, tmp_path, dossier.name)
    assert res.exit_code == 4
    avant = fichier.read_bytes()
    monkeypatch.setattr(juge_llm, "_SYSTEM", juge_llm._SYSTEM + " Sois bref.")
    sdk = _Sdk()
    res = _cli(monkeypatch, sdk, exp, tmp_path, dossier.name, "--reprendre")
    assert res.exit_code == 2 and "requête de Juge" in res.output, res.output
    assert not sdk.appels and fichier.read_bytes() == avant


def test_reprise_comptee_dans_le_meme_plafond_par_execution(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La reprise garde l'identifiant de Registre : le plafond `per_run` déjà consommé compte."""
    exp, dossier = execution
    fichier = dossier / "calibration_verdicts.jsonl"
    complet = _Sdk()
    res = _cli(monkeypatch, complet, exp, tmp_path, dossier.name)
    assert res.exit_code == 0, res.output
    fichier.unlink()
    (dossier / "calibration.json").unlink()
    donnees = yaml.safe_load(exp.read_text("utf-8"))
    donnees["experiment_id"] = "exp-9-1-plafond"  # hors Cache de réponses de la 1re calibration
    donnees["budget"]["per_run"]["anthropic"]["amount"] = "0.02"
    serre = tmp_path / "serre.yaml"
    serre.write_text(yaml.safe_dump(donnees), encoding="utf-8")
    res = _cli(monkeypatch, _Sdk(), serre, tmp_path, dossier.name, "--ecraser")
    assert res.exit_code == 3, res.output
    avant = _lire(fichier)
    assert 0 < len(avant) < len(complet.appels)
    assert len({x["calibration_id"] for x in avant}) == 1
    sdk = _Sdk()
    res = _cli(monkeypatch, sdk, serre, tmp_path, dossier.name, "--reprendre")
    assert res.exit_code == 3, res.output  # plafond déjà atteint par la tentative interrompue
    assert not sdk.appels and _lire(fichier) == avant


def test_derniere_ligne_complete_sans_saut_de_ligne_est_rappelee(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une ligne sans saut de ligne final (arrêt pendant l'écriture) est retirée, son triplet
    rappelé : l'ajout suivant ne se colle pas à elle."""
    exp, dossier = execution
    fichier = dossier / "calibration_verdicts.jsonl"
    res = _cli(monkeypatch, _Sdk(echec_au=4), exp, tmp_path, dossier.name)
    assert res.exit_code == 4
    lignes = _lire(fichier)
    fichier.write_bytes(fichier.read_bytes().rstrip(b"\n"))
    res = _cli(monkeypatch, _Sdk(), exp, tmp_path, dossier.name, "--reprendre")
    assert res.exit_code == 0, res.output
    relu = _lire(fichier)  # chaque ligne se relit seule
    assert relu[:2] == lignes[:2]
    total = len(read_answers(dossier)) * len(JUGES) * PASSES
    assert len(relu) == total
    assert len({(x["judge_model"], x["answer_id"], x["pass_id"]) for x in relu}) == total
    assert not fichier.with_name(fichier.name + ".tmp").exists()


@pytest.mark.parametrize(
    ("contenu", "message"),
    [
        (
            '{"answer_id": "a", "judge_model": "m", "pass_id": 0, "empreinte": "e", '
            '"calibration_id": "c"}\n',
            "ligne 1 illisible",
        ),
        (
            '{"answer_id": "a", "judge_model": "m", "criterion": "correctness", "pass_id": 0, '
            '"verdict": true, "justification": "ok"}\n',
            "ancien format",
        ),
    ],
)
def test_ligne_complete_invalide_refusee_sans_suppression(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, contenu: str, message: str
) -> None:
    _, dossier = execution
    fichier = dossier / "calibration_verdicts.jsonl"
    fichier.write_text(contenu, encoding="utf-8", newline="\n")
    exp = validate_file(_experience(tmp_path)).resolved
    with pytest.raises(ConfigError, match=message):
        calibrer(exp, tmp_path / "ann", dossier.name, wl_home=wl_home, reprendre=True)
    assert fichier.read_text("utf-8") == contenu


def test_ecraser_ne_supprime_rien_si_la_preparation_echoue(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dossier = execution
    fichier = dossier / "calibration_verdicts.jsonl"
    fichier.write_text("{}\n", encoding="utf-8")
    exp = validate_file(_experience(tmp_path)).resolved

    def panne(*_a: Any, **_k: Any) -> Any:  # injection de panne avant le premier appel
        raise ConfigError("judges", "Juge impossible à construire")

    monkeypatch.setattr(module_calibrer, "construire_juges", panne)
    with pytest.raises(ConfigError, match="impossible"):
        calibrer(exp, tmp_path / "ann", dossier.name, wl_home=wl_home, ecraser=True)
    assert fichier.read_text("utf-8") == "{}\n"


def test_interruption_clavier_donne_la_commande_de_reprise(
    execution: tuple[Path, Path], tmp_path: Path, wl_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, dossier = execution
    res = _cli(monkeypatch, _Sdk(echec_au=3, interrompre=True), exp, tmp_path, dossier.name)
    assert res.exit_code == 1, res.output
    assert "Interrompu" in res.output and "2 verdict(s) conservé(s)" in res.output
    assert f"--run {dossier.name} --reprendre" in res.output
    assert len(_lire(dossier / "calibration_verdicts.jsonl")) == 2
