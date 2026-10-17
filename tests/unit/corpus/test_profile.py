"""Tests du Profil de corpus, des entités et de `wl corpus profiler` (story 2.4)."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.config.catalog import ModelCatalog
from wavelibrarian.config.schemas import ModelEntry
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import Anchor, Block, ParsedCorpus, ParsedDocument
from wavelibrarian.corpus.entities import extraire_entites, link_density
from wavelibrarian.corpus.profile import profile
from wavelibrarian.measure.tokenizers import ApproxTokenizer

runner = CliRunner()


def _mots(n: int) -> str:
    return " ".join(["mot"] * n)


def _doc(i: int, lang: str, profondeur: int, blocs: list[tuple[str, str]]) -> ParsedDocument:
    did = f"d{i}"
    ancres: dict[str, Anchor] = {}
    for k in range(profondeur + 1):
        aid = f"{did}#h/{'/'.join(f't{j}' for j in range(k))}"
        ancres[aid] = Anchor(
            anchor_id=aid,
            doc_id=did,
            source_path=f"{did}.md",
            heading_path=tuple(f"T{j}" for j in range(k)),
        )
    aid = next(iter(ancres))
    return ParsedDocument(
        doc_id=did,
        source_path=f"{did}.md",
        format="markdown",
        lang=lang,
        blocks=tuple(Block(text=t, anchor_id=aid, kind=k) for k, t in blocs),  # type: ignore[arg-type]
        anchors=ancres,
    )


def _corpus_connu() -> ParsedCorpus:
    # 200 tokens dont un tableau de 20 ; 2 images ; profondeurs 1, 2, 3 ; fr, fr, en.
    d1 = _doc(1, "fr", 1, [("text", _mots(80)), ("image", ""), ("table", _mots(20))])
    d2 = _doc(2, "fr", 2, [("text", _mots(60)), ("image", "")])
    d3 = _doc(3, "en", 3, [("text", _mots(40))])
    return ParsedCorpus(corpus_id="c", fingerprint="f" * 16, documents=(d1, d2, d3))


def test_profil_aux_valeurs_connues() -> None:
    p = profile(_corpus_connu(), parser="markdown", tokenizer=ApproxTokenizer(), volatility="high")
    assert (p.n_documents, p.n_tokens) == (3, 200)
    assert p.mean_tokens_per_document == pytest.approx(200 / 3)
    assert p.heading_depth_max == 3
    assert p.heading_depth_mean == pytest.approx(2.0)
    assert p.table_share == pytest.approx(0.1)
    assert p.images_per_document == pytest.approx(2 / 3)
    assert p.dominant_lang == "fr"
    assert p.langs == {"en": 1, "fr": 2}
    assert p.formats == {"markdown": 3}
    assert p.tokenizer == "approx"
    assert p.volatility == "high"
    assert p.parser == "markdown"


def test_langue_dominante_a_egalite_est_alphabetique() -> None:
    docs = (_doc(1, "fr", 0, [("text", "a")]), _doc(2, "en", 0, [("text", "b")]))
    c = ParsedCorpus(corpus_id="c", fingerprint="f", documents=docs)
    p = profile(c, parser="x", tokenizer=ApproxTokenizer(), volatility="low")
    assert p.dominant_lang == "en"


def test_corpus_vide_est_refuse() -> None:
    c = ParsedCorpus(corpus_id="c", fingerprint="f", documents=())
    with pytest.raises(ConfigError):
        profile(c, parser="x", tokenizer=ApproxTokenizer(), volatility="low")


def test_entites_hors_debut_de_phrase() -> None:
    e = extraire_entites("Hier, la Guilde d'Orvane a ouvert. Paris est calme. Elle vit à Lyon.")
    assert "guilde d'orvane" in e
    assert "lyon" in e
    assert "paris" not in e  # seul mot capitalisé en début de phrase
    assert "hier" not in e


def test_link_density_deux_tiers() -> None:
    textes = [
        "Le registre cite la Guilde d'Orvane et son chef.",
        "On sait que la Guilde d'Orvane a fondé le port.",
        "Rien de remarquable ici, tout est en minuscules.",
    ]
    docs = tuple(_doc(i, "fr", 0, [("text", t)]) for i, t in enumerate(textes))
    c = ParsedCorpus(corpus_id="c", fingerprint="f", documents=docs)
    assert link_density(c) == pytest.approx(2 / 3)


def _entree(id_: str, **kw: object) -> ModelEntry:
    return ModelEntry(
        id=id_,
        provider="fake",
        family="f",
        kind="local",
        modality="llm",
        **kw,  # type: ignore[arg-type]
    )


def test_tokens_for_reference_facteur_et_defaut() -> None:
    cat = ModelCatalog(
        catalog_date="2026-10-17",  # type: ignore[arg-type]
        models=(
            _entree("ref", tokenizer="reference"),
            _entree("x15", tokenizer="approx", token_factor=Decimal("1.5")),
            _entree("defaut", tokenizer="approx"),
        ),
    )
    p = profile(_corpus_connu(), parser="m", tokenizer=ApproxTokenizer(), volatility="low")
    p = p.model_copy(update={"n_tokens": 50_000})
    assert p.tokens_for("ref", cat) == 50_000
    assert p.tokens_for("x15", cat) == 75_000
    assert p.tokens_for("defaut", cat) == 60_000


def _ecrire_corpus(racine: Path, volatilite: str = "medium") -> Path:
    docs = racine / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# Titre\n\nLa Guilde d'Orvane commerce.\n", encoding="utf-8")
    (docs / "b.md").write_text(
        "# Autre\n\n## Sous\n\nOn cite la Guilde d'Orvane ici.\n", encoding="utf-8"
    )
    yml = racine / "corpus.yaml"
    yml.write_text(
        "corpus_id: demo\npath: docs\nlang: fr\nlicense: CC-BY-4.0\npublishable: true\n"
        f"volatility: {volatilite}\n",
        encoding="utf-8",
    )
    return yml


def test_cli_ecrit_le_profil(tmp_path: Path, wl_home: Path) -> None:
    yml = _ecrire_corpus(tmp_path)
    sortie = tmp_path / "out"
    args = ["corpus", "profiler", str(yml), "--parser", "auto", "--profil", "test"]
    r = runner.invoke(app, [*args, "--sortie", str(sortie)])
    assert r.exit_code == 0, r.output
    data = json.loads((sortie / "corpus_profile.json").read_text(encoding="utf-8"))
    assert data["n_documents"] == 2
    assert data["tokenizer"] == "approx"
    assert data["volatility"] == "medium"
    assert data["link_density"] == 1.0
    assert data["parser"] == "markdown"
    assert "Documents : 2" in r.output
    assert "Langue dominante : fr" in r.output


def test_cli_corpus_invalide_sort_en_code_2(tmp_path: Path, wl_home: Path) -> None:
    yml = _ecrire_corpus(tmp_path, volatilite="inconnue")
    r = runner.invoke(
        app, ["corpus", "profiler", str(yml), "--profil", "test", "--sortie", str(tmp_path)]
    )
    assert r.exit_code == 2
    assert not (tmp_path / "corpus_profile.json").exists()
