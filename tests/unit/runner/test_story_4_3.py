"""Story 4.3 : cache d'index (`index_cache.py`) et dossier d'Exécution (`rundir.py`)."""

import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from wavelibrarian.architectures.bm25_only import Bm25Only
from wavelibrarian.config.experiment import ResolvedExperiment
from wavelibrarian.config.load import load_experiment
from wavelibrarian.config.resolve import resolve_experiment
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.ids import canonical_json, sha16
from wavelibrarian.core.types import ParsedCorpus, QuestionInput
from wavelibrarian.corpus.declare import declare
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.architecture import ArchitectureBase
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.runner.context import Context
from wavelibrarian.runner.index_cache import IndexCache, index_key
from wavelibrarian.runner.rundir import (
    JsonlWriter,
    attach_run_log,
    create_run_dir,
    detach_run_log,
    resolve_parsers,
    set_status,
)

CORPUS_MINICORPUS = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus" / "corpus.yaml"


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[Context]:
    c = Context.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-1", seed=1, providers={"fake": FakeProvider()}
    )
    with c:
        yield c


def _factory(ctx: Context, **params: Any) -> Callable[[], ArchitectureBase]:
    return lambda: ctx.build("architecture", ComponentSpec(name="bm25_only", params=params))


def _spans(ctx: Context) -> list[dict[str, Any]]:
    chemin = ctx.run_dir / "traces.jsonl"
    if not chemin.exists():
        return []
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


def _experience(tmp_path: Path, parser: str = "auto") -> ResolvedExperiment:
    donnees: dict[str, Any] = {
        "experiment_id": "exp-1",
        "seed": 3,
        "profile": "test",
        "corpus": str(CORPUS_MINICORPUS),
        "questions": str(tmp_path / "questions.yaml"),
        "configurations": [{"id": "bm25", "architecture": "bm25_only", "parser": {"name": parser}}],
    }
    chemin = tmp_path / "exp.yaml"
    chemin.write_text(yaml.safe_dump(donnees), encoding="utf-8")
    return resolve_experiment(load_experiment(chemin), chemin, tmp_path / "wl")


# --- cache d'index ----------------------------------------------------------------------------


def test_premiere_demande_ecrit_tmp_manifest_puis_renomme(
    ctx: Context, minicorpus: ParsedCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    vus: list[str] = []
    original = Bm25Only.index

    def espion(self: Any, corpus: ParsedCorpus, directory: Path) -> None:
        vus.append(directory.name)
        original(self, corpus, directory)

    monkeypatch.setattr(Bm25Only, "index", espion)
    arch, cle = IndexCache(ctx.wl_home).build(ctx, _factory(ctx), minicorpus)
    assert vus == [f".tmp-{cle}"]
    final = ctx.wl_home / "index" / cle
    assert final.is_dir() and not (ctx.wl_home / "index" / f".tmp-{cle}").exists()
    manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"index_key", "architecture", "corpus_fingerprint", "created_at"}
    assert manifest["index_key"] == cle and manifest["architecture"] == "bm25_only"
    assert manifest["corpus_fingerprint"] == minicorpus.fingerprint
    assert (final / "passages.jsonl").is_file()
    assert isinstance(arch, Bm25Only)


def test_index_key_est_le_hachage_des_trois_elements(
    ctx: Context, minicorpus: ParsedCorpus
) -> None:
    arch = _factory(ctx)()
    attendu = sha16(
        canonical_json(
            {
                "corpus_fingerprint": minicorpus.fingerprint,
                "architecture": "bm25_only",
                "index_key": arch.index_key(),
            }
        )
    )
    assert index_key(minicorpus.fingerprint, arch) == attendu
    cle = arch.index_key()
    assert cle["parser"] == ctx.parser and cle["tokenizer"] == ctx.tokenizer.name
    assert "k" not in cle["params"]


def test_index_present_pas_de_index_instance_neuve_load_et_span_hit(
    ctx: Context, minicorpus: ParsedCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = IndexCache(ctx.wl_home)
    premiere, cle = cache.build(ctx, _factory(ctx), minicorpus)
    appels: list[Path] = []
    monkeypatch.setattr(Bm25Only, "index", lambda self, corpus, d: appels.append(d))
    seconde, cle2 = cache.build(ctx, _factory(ctx), minicorpus)
    assert appels == [] and cle2 == cle
    assert seconde is not premiere
    mot = max(minicorpus.documents[0].blocks[0].text.split(), key=len)
    with ctx.scope(post="query"):
        rep = seconde.answer(QuestionInput(question_id="q", text=mot, lang="fr"))
    assert rep.retrieved  # l'instance chargée répond
    spans = [s for s in _spans(ctx) if s["name"] == "index"]
    assert [s["wl.index_cache_hit"] for s in spans] == [False, True]
    assert all(s["wl.kind"] == "local" and s["wl.post"] == "indexing" for s in spans)


def test_exception_pendant_index_aucun_dossier_final_ni_tmp(
    ctx: Context, minicorpus: ParsedCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = IndexCache(ctx.wl_home)
    original = Bm25Only.index

    def echoue(self: Any, corpus: ParsedCorpus, directory: Path) -> None:
        (directory / "partiel.txt").write_text("x", encoding="utf-8")
        raise RuntimeError("boum")

    monkeypatch.setattr(Bm25Only, "index", echoue)
    with pytest.raises(RuntimeError, match="boum"):
        cache.build(ctx, _factory(ctx), minicorpus)
    assert list((ctx.wl_home / "index").iterdir()) == []
    assert [s for s in _spans(ctx) if s["name"] == "index"] == []
    monkeypatch.setattr(Bm25Only, "index", original)  # la reprise reconstruit normalement
    _, cle = cache.build(ctx, _factory(ctx), minicorpus)
    assert cache.has(cle)


def test_dossier_temporaire_obsolete_ignore_a_la_reprise(
    ctx: Context, minicorpus: ParsedCorpus
) -> None:
    cache = IndexCache(ctx.wl_home)
    cle = index_key(minicorpus.fingerprint, _factory(ctx)())
    tmp = ctx.wl_home / "index" / f".tmp-{cle}"
    tmp.mkdir(parents=True)
    (tmp / "reste.txt").write_text("x", encoding="utf-8")
    assert not cache.has(cle)
    cache.build(ctx, _factory(ctx), minicorpus)
    assert not tmp.exists() and not (ctx.wl_home / "index" / cle / "reste.txt").exists()


def test_k_hors_de_la_cle_size_du_chunker_dans_la_cle(
    ctx: Context, minicorpus: ParsedCorpus
) -> None:
    fp = minicorpus.fingerprint

    def cle(**p: Any) -> str:
        return index_key(fp, _factory(ctx, **p)())

    assert cle(k=3) == cle(k=9) == cle()
    petit = ComponentSpec(name="fixed_tokens", params={"size": 120, "overlap": 10})
    assert cle(chunker=petit) != cle()


def test_cle_change_avec_le_corpus_et_le_parser(ctx: Context, minicorpus: ParsedCorpus) -> None:
    arch = _factory(ctx)()
    avant = index_key(minicorpus.fingerprint, arch)
    assert index_key("autre", arch) != avant
    ctx.parser = "text"
    assert index_key(minicorpus.fingerprint, _factory(ctx)()) != avant


def test_manifest_porte_embedder_dim_quand_l_architecture_en_a_un(
    ctx: Context, minicorpus: ParsedCorpus
) -> None:
    class Dim:
        dim = 8

    def factory() -> ArchitectureBase:
        arch = _factory(ctx)()
        arch.embedder = Dim()  # type: ignore[attr-defined]
        return arch

    _, cle = IndexCache(ctx.wl_home).build(ctx, factory, minicorpus)
    manifest = json.loads((ctx.wl_home / "index" / cle / "manifest.json").read_text("utf-8"))
    assert manifest["embedder_dim"] == 8


# --- dossier d'Exécution ----------------------------------------------------------------------


def test_parser_auto_remplace_avant_write_resolved(tmp_path: Path) -> None:
    experience = _experience(tmp_path)
    assert experience.configurations[0].parser.name == "auto"
    resolue = resolve_parsers(experience, declare(CORPUS_MINICORPUS))
    assert resolue.configurations[0].parser.name == "markdown+pdf_text"
    wl = tmp_path / "wl"
    dossier = create_run_dir(wl, "run-1", resolue)
    texte = (dossier / "experiment.resolved.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load(texte)["configurations"][0]["parser"]["name"] == "markdown+pdf_text"
    assert "name: auto" not in texte
    with Context.from_experiment(resolue, wl_home=wl, run_id="run-1") as c:
        assert c.parser == "markdown+pdf_text"


def test_parser_explicite_conserve_et_auto_refuse_par_create_run_dir(tmp_path: Path) -> None:
    experience = _experience(tmp_path, parser="markdown")
    resolue = resolve_parsers(experience, declare(CORPUS_MINICORPUS))
    assert resolue.configurations[0].parser.name == "markdown"
    with pytest.raises(WlError, match="auto"):
        create_run_dir(tmp_path / "wl", "run-2", _experience(tmp_path))


def test_dossier_d_execution_fichiers_avant_tout_appel(tmp_path: Path) -> None:
    resolue = resolve_parsers(_experience(tmp_path), declare(CORPUS_MINICORPUS))
    wl = tmp_path / "wl"
    dossier = create_run_dir(wl, "run-3", resolue, freeze_sha256="ab" * 32)
    assert dossier == wl / "runs" / "run-3"
    assert sorted(p.name for p in dossier.iterdir()) == [
        "experiment.resolved.yaml",
        "experiment.sha256",
        "manifest.json",
    ]
    manifest = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "running" and manifest["profile"] == "test"
    assert manifest["models_frozen_at"] == resolue.models_frozen_at.isoformat()
    assert manifest["models"] and "fake-llm-a" in manifest["models"]
    assert manifest["freeze_sha256"] == "ab" * 32
    empreinte = (dossier / "experiment.sha256").read_text(encoding="utf-8").strip()
    assert manifest["experiment_sha256"] == empreinte and len(empreinte) == 64
    with pytest.raises(WlError, match="déjà initialisée"):
        create_run_dir(wl, "run-3", resolue)
    with pytest.raises(ValueError, match="run_id invalide"):
        create_run_dir(wl, "../x", resolue)
    set_status(dossier, "completed")
    manifest = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed" and "finished_at" in manifest


def test_jsonl_ajout_seulement_utf8_lf(tmp_path: Path) -> None:
    with JsonlWriter(tmp_path, "answers.jsonl") as w:
        w.append({"id": "é", "n": 1})
    with JsonlWriter(tmp_path, "answers.jsonl") as w:  # réouverture : on ajoute, on n'écrase pas
        w.append({"id": "ü", "n": 2})
    brut = (tmp_path / "answers.jsonl").read_bytes()
    assert b"\r" not in brut and brut.endswith(b"\n")
    lignes = brut.decode("utf-8").splitlines()
    assert [json.loads(x)["n"] for x in lignes] == [1, 2] and "é" in lignes[0]
    with pytest.raises(ValueError, match="traces.jsonl"):
        JsonlWriter(tmp_path, "traces.jsonl")  # type: ignore[arg-type]  # fichier du Tracer


def test_run_log_ecrit_en_utf8(tmp_path: Path) -> None:
    handler = attach_run_log(tmp_path)
    try:
        logging.getLogger("wavelibrarian.test").warning("bonjour é")
    finally:
        detach_run_log(handler)
    assert "bonjour é" in (tmp_path / "run.log").read_text(encoding="utf-8")
