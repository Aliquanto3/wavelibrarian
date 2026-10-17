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
from wavelibrarian.core.errors import ConfigError, WlError
from wavelibrarian.core.ids import canonical_json, sha16
from wavelibrarian.core.types import ParsedCorpus, QuestionInput
from wavelibrarian.corpus.declare import declare
from wavelibrarian.corpus.ingest import ingest, parsers_par_format
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

GEL = "ab" * 32
CORPUS_MINICORPUS = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus" / "corpus.yaml"


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[Context]:
    c = Context.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-1", seed=1, providers={"fake": FakeProvider()}
    )
    c.parser = "markdown+pdf_text"  # parser résolu du Mini-corpus (resolve_parsers)
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
                "parser_versions": {"markdown": "1", "pdf_text": "1"},
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


def test_cle_change_avec_la_version_du_parser(
    ctx: Context, minicorpus: ParsedCorpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavelibrarian.components.parsers.markdown import MarkdownParser

    avant = index_key(minicorpus.fingerprint, _factory(ctx)())
    monkeypatch.setattr(MarkdownParser, "version", "2")
    assert index_key(minicorpus.fingerprint, _factory(ctx)()) != avant


def test_parser_auto_refuse_par_la_cle(ctx: Context, minicorpus: ParsedCorpus) -> None:
    ctx.parser = "auto"
    with pytest.raises(ConfigError, match="auto"):
        index_key(minicorpus.fingerprint, _factory(ctx)())


def test_contenu_modifie_change_fingerprint_et_cle(ctx: Context, tmp_path: Path) -> None:
    racine = tmp_path / "c"
    (racine / "docs").mkdir(parents=True)
    (racine / "corpus.yaml").write_text(
        "corpus_id: mini\npath: docs\nlang: fr\nlicense: CC-BY-4.0\npublishable: true\n"
        "volatility: low\n",
        encoding="utf-8",
    )
    doc = racine / "docs" / "a.md"
    doc.write_text("# Titre\n\nPremier texte.\n", encoding="utf-8")
    ctx.parser = "markdown"
    avant = ingest(declare(racine / "corpus.yaml"), "markdown", wl_home=tmp_path / "wl")
    doc.write_text("# Titre\n\nTexte modifié.\n", encoding="utf-8")
    apres = ingest(declare(racine / "corpus.yaml"), "markdown", wl_home=tmp_path / "wl")
    assert apres.fingerprint != avant.fingerprint
    arch = _factory(ctx)()
    assert index_key(apres.fingerprint, arch) != index_key(avant.fingerprint, arch)


def test_manifest_porte_embedder_dim_quand_l_architecture_en_a_un(
    ctx: Context, minicorpus: ParsedCorpus
) -> None:
    assert _factory(ctx)().embedder_dim() is None  # défaut du port

    def factory() -> ArchitectureBase:
        arch = _factory(ctx)()
        arch.embedder_dim = lambda: 8  # type: ignore[method-assign]
        return arch

    _, cle = IndexCache(ctx.wl_home).build(ctx, factory, minicorpus)
    manifest = json.loads((ctx.wl_home / "index" / cle / "manifest.json").read_text("utf-8"))
    assert manifest["embedder_dim"] == 8


# --- dossier d'Exécution ----------------------------------------------------------------------


def test_parser_auto_remplace_avant_write_resolved(tmp_path: Path) -> None:
    experience = _experience(tmp_path)
    assert experience.configurations[0].parser.name == "auto"
    corpus = declare(CORPUS_MINICORPUS)
    resolue = resolve_parsers(experience, corpus)
    assert resolue.configurations[0].parser.name == "markdown+pdf_text"
    wl = tmp_path / "wl"
    dossier = create_run_dir(wl, "run-1", resolue, freeze_sha256=GEL)
    texte = (dossier / "experiment.resolved.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load(texte)["configurations"][0]["parser"]["name"] == "markdown+pdf_text"
    assert "name: auto" not in texte
    with Context.from_experiment(resolue, wl_home=wl, run_id="run-1") as c:
        assert c.parser == "markdown+pdf_text"
        # de bout en bout : le nom résolu sert à l'ingestion réelle puis à la clé d'index
        parse = ingest(corpus, c.parser, wl_home=wl)
        assert {d.source_path.rsplit(".", 1)[-1] for d in parse.documents} == {"md", "pdf"}
        assert parse.fingerprint == ingest(corpus, wl_home=wl).fingerprint
        _, cle = IndexCache(wl).build(c, _factory(c), parse)
        assert IndexCache(wl).has(cle)


def test_parser_composite_par_format() -> None:
    assert parsers_par_format(["markdown", "pdf"], "markdown+pdf_text") == {
        "markdown": "markdown",
        "pdf": "pdf_text",
    }
    with pytest.raises(ConfigError, match="inconnu"):
        parsers_par_format(["markdown"], "markdown+nimporte")
    with pytest.raises(ConfigError, match="pdf"):
        parsers_par_format(["markdown", "pdf"], "html+markdown")


def test_parser_explicite_conserve_et_auto_refuse_par_create_run_dir(tmp_path: Path) -> None:
    experience = _experience(tmp_path, parser="markdown")
    resolue = resolve_parsers(experience, declare(CORPUS_MINICORPUS))
    assert resolue.configurations[0].parser.name == "markdown"
    with pytest.raises(WlError, match="auto"):
        create_run_dir(tmp_path / "wl", "run-2", _experience(tmp_path), freeze_sha256=GEL)


def test_dossier_d_execution_fichiers_avant_tout_appel(tmp_path: Path) -> None:
    resolue = resolve_parsers(_experience(tmp_path), declare(CORPUS_MINICORPUS))
    wl = tmp_path / "wl"
    dossier = create_run_dir(wl, "run-3", resolue, freeze_sha256=GEL)
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
    assert manifest["freeze_sha256"] == GEL
    empreinte = (dossier / "experiment.sha256").read_text(encoding="utf-8").strip()
    assert manifest["experiment_sha256"] == empreinte and len(empreinte) == 64
    with pytest.raises(WlError, match="déjà initialisée"):
        create_run_dir(wl, "run-3", resolue, freeze_sha256=GEL)
    with pytest.raises(ValueError, match="run_id invalide"):
        create_run_dir(wl, "../x", resolue, freeze_sha256=GEL)
    with pytest.raises(ValueError, match="freeze_sha256"):
        create_run_dir(wl, "run-4", resolue, freeze_sha256="ab")
    reste = wl / "runs" / "run-5"
    reste.mkdir()
    (reste / "answers.jsonl").write_text("{}\n", encoding="utf-8")  # dossier sans manifeste
    with pytest.raises(WlError, match="déjà initialisée"):
        create_run_dir(wl, "run-5", resolue, freeze_sha256=GEL)
    assert (reste / "answers.jsonl").read_text(encoding="utf-8") == "{}\n"
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


def test_run_log_filtre_les_debug_reseau_et_les_en_tetes(tmp_path: Path) -> None:
    racine = logging.getLogger()
    niveau = racine.level
    racine.setLevel(logging.DEBUG)
    handler = attach_run_log(tmp_path)
    try:
        for nom in ("anthropic", "httpx", "httpx2", "httpcore2._trace"):
            log = logging.getLogger(nom)
            log.setLevel(logging.DEBUG)  # relevé après coup (ANTHROPIC_LOG=debug)
            log.debug("Request headers: {'x-api-key': 'sk-ant-SECRET'} %s", nom)
        logging.getLogger("httpx").warning("avertissement réseau gardé")
        logging.getLogger("wavelibrarian.runner").debug("debug du runner gardé")
    finally:
        detach_run_log(handler)
        racine.setLevel(niveau)
        for nom in ("anthropic", "httpx", "httpx2", "httpcore2._trace"):
            logging.getLogger(nom).setLevel(logging.WARNING)
    texte = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "SECRET" not in texte and "x-api-key" not in texte
    assert "avertissement réseau gardé" in texte and "debug du runner gardé" in texte
