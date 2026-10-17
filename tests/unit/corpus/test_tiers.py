"""Paliers de volume et commande `wl corpus paliers` (story 2.7)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import ParsedCorpus
from wavelibrarian.corpus.declare import TiersSpec
from wavelibrarian.corpus.tiers import tirer, tirer_chemins

MINI = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
REQUIS = ["atlas-vaelmor.md", "phare-de-keld.md", "lettre-torvane.pdf"]
BASE = "corpus_id: t\npath: docs\nlang: fr\nlicense: MIT\npublishable: true\nvolatility: low\n"


def _chemins(c: ParsedCorpus) -> list[str]:
    return [d.source_path for d in c.documents]


def _petit_corpus(tmp_path: Path, extra: str) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\n\nTexte.\n", encoding="utf-8")
    (tmp_path / "corpus.yaml").write_text(BASE + extra, encoding="utf-8")
    return tmp_path / "corpus.yaml"


def test_emboitement_et_requis(minicorpus: ParsedCorpus) -> None:
    p = tirer(minicorpus, TiersSpec(seed=42, sizes=(5, 10, 20)), REQUIS)
    assert [len(c.documents) for c in p.values()] == [5, 10, 20]
    assert set(_chemins(p[5])) <= set(_chemins(p[10])) <= set(_chemins(p[20]))
    for c in p.values():
        assert set(REQUIS) <= set(_chemins(c))


def test_graine_reproductible_et_variable(minicorpus: ParsedCorpus) -> None:
    t = TiersSpec(seed=42, sizes=(5, 10, 20))
    base = tirer(minicorpus, t, REQUIS)
    assert tirer(minicorpus, t, REQUIS) == base
    autre = tirer(minicorpus, TiersSpec(seed=7, sizes=(5, 10, 20)), REQUIS)
    assert set(_chemins(autre[10])) != set(_chemins(base[10]))


def test_requis_plus_nombreux_que_la_plus_petite_taille(minicorpus: ParsedCorpus) -> None:
    with pytest.raises(ConfigError, match="ne peut pas contenir") as e:
        tirer(minicorpus, TiersSpec(seed=1, sizes=(2, 10)), REQUIS)
    assert "tiers.sizes[0]" in str(e.value)


def test_taille_superieure_au_corpus(minicorpus: ParsedCorpus) -> None:
    with pytest.raises(ConfigError) as e:
        tirer(minicorpus, TiersSpec(seed=1, sizes=(5, 21)))
    assert "tiers.sizes[1]" in str(e.value)


def test_requis_inconnu() -> None:
    with pytest.raises(ConfigError, match="absent du Corpus"):
        tirer_chemins(["a.md", "b.md"], TiersSpec(seed=1, sizes=(1,)), ["z.md"])


def test_sous_corpus_et_empreinte(minicorpus: ParsedCorpus) -> None:
    p = tirer(minicorpus, TiersSpec(seed=42, sizes=(5, 10, 20)), REQUIS)
    assert p[20].fingerprint == minicorpus.fingerprint
    assert len({p[5].fingerprint, p[10].fingerprint, p[20].fingerprint}) == 3
    assert p[5].corpus_id == minicorpus.corpus_id
    assert all(d in minicorpus.documents for d in p[5].documents)


def test_commande_paliers() -> None:
    res = CliRunner().invoke(app, ["corpus", "paliers", str(MINI / "corpus.yaml")])
    assert res.exit_code == 0, res.output
    assert "Palier 5 (5 Documents)" in res.output
    assert "Palier 20 (20 Documents)" in res.output
    assert "atlas-vaelmor.md" in res.output


def test_commande_sans_tiers(tmp_path: Path) -> None:
    res = CliRunner().invoke(app, ["corpus", "paliers", str(_petit_corpus(tmp_path, ""))])
    assert res.exit_code == 0
    assert "ne déclare pas de clé `tiers`" in res.output


def test_commande_taille_trop_grande(tmp_path: Path) -> None:
    chemin = _petit_corpus(tmp_path, "tiers: {seed: 1, sizes: [3]}\n")
    res = CliRunner().invoke(app, ["corpus", "paliers", str(chemin)])
    assert res.exit_code == 2
    assert "tiers.sizes[0]" in res.output
