"""Génération de Questions candidates et `wl questions generer` (story 3.3), Faux LLM seul."""

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

import wavelibrarian.cli as cli
from wavelibrarian.cli import app
from wavelibrarian.config.experiment import Amount, Budget
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.evalset import check, generate, io
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context

SECTIONS = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta"]
REPARTITION = "factual=3,multi_hop=1,unanswerable=1"


def _question(i: int, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": f"q-{i:03d}",
        "type": "factual",
        "follow_up": False,
        "cross_lingual": False,
        "text": "Que dit Alpha ?",
        "lang": "fr",
        "reference_answer": "La section Alpha.",
        "answer_form": "free",
        "reference_anchors": [{"doc": "a.md", "headings": ["Guide", "Alpha"]}],
        "status": "validated",
        "split": None,
        "contaminated_by": [],
        "history": [],
        "origin": {"kind": "human", "name": "anael"},
        "scenario_target": None,
    }
    base.update(kw)
    return base


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    md = "# Guide\n\n" + "".join(
        f"## {s}\n\nLa section {s} décrit un point précis numéro {i}.\n\n"
        for i, s in enumerate(SECTIONS)
    )
    (tmp_path / "docs" / "a.md").write_text(md, encoding="utf-8")
    spec = {
        "corpus_id": "demo",
        "path": "docs",
        "lang": "fr",
        "license": "CC-BY-4.0",
        "publishable": True,
        "volatility": "low",
    }
    chemin = tmp_path / "corpus.yaml"
    chemin.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return chemin


def _ecrire(chemin: Path, questions: list[dict[str, Any]], **kw: Any) -> Path:
    doc: dict[str, Any] = {
        "corpus_id": "demo",
        "target_count": 10,
        "freeze": None,
        "questions": questions,
    }
    doc.update(kw)
    chemin.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return chemin


class Env:
    def __init__(self) -> None:
        self.provider = FakeProvider()
        self.requetes: list[LLMRequest] = []
        self.budget: Budget | None = None

    def script(self, sortie: Callable[[LLMRequest], str]) -> None:
        def _enregistre(req: LLMRequest) -> str:
            self.requetes.append(req)
            return sortie(req)

        self.provider.script("question_gen", "question_gen*", _enregistre)

    def capture(self) -> None:
        """Garde le comportement par défaut du Faux LLM, en notant les requêtes."""
        self.script(lambda req: json.dumps(_defaut(req)))


def _defaut(req: LLMRequest) -> dict[str, Any]:
    from wavelibrarian.llm.providers.fake import default_output

    return json.loads(default_output("question_gen", req.inputs))


def _sortie(req: LLMRequest) -> str:
    """Sortie scénarisée valide : 3 factual, 1 multi_hop (2 Ancrages), 1 unanswerable."""
    ids = [a["anchor_id"] for a in req.inputs["anchors"]]
    qs = [
        {
            "type": "factual",
            "text": f"Question factuelle {i}",
            "reference_answer": "Réponse",
            "answer_form": "free",
            "anchor_ids": [ids[i]],
        }
        for i in range(3)
    ]
    qs.append(
        {
            "type": "multi_hop",
            "text": "Question à deux sauts",
            "reference_answer": "Réponse",
            "answer_form": "free",
            "anchor_ids": [ids[3], ids[4]],
        }
    )
    qs.append(
        {
            "type": "unanswerable",
            "text": "Question sans réponse",
            "reference_answer": "",
            "answer_form": "free",
            "anchor_ids": [],
        }
    )
    return json.dumps({"questions": qs})


@pytest.fixture
def env(wl_home: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    e = Env()

    def _contexte(profil: str, seed: int) -> Context:
        return Context.from_profile(
            "test",
            wl_home=wl_home,
            run_id="hors-1",
            seed=seed,
            providers={"fake": e.provider},
            budget=e.budget,
        )

    monkeypatch.setattr(cli, "_contexte_hors_execution", _contexte)
    return e


def _generer(corpus: Path, *args: str, repartition: str = REPARTITION):
    return CliRunner().invoke(
        app,
        [
            "questions",
            "generer",
            str(corpus),
            "--repartition",
            repartition,
            "--profil",
            "test",
            *args,
        ],
    )


# --- AC 1 : Questions ajoutées, existantes conservées -----------------------------------------


def test_questions_ajoutees_generated_et_existantes_conservees(corpus: Path, env: Env) -> None:
    env.script(_sortie)
    fichier = _ecrire(
        corpus.parent / "questions.yaml",
        [_question(1), _question(5, status="rejected"), _question(7, status="corrected")],
    )
    avant = io.load(fichier)
    res = _generer(corpus)
    assert res.exit_code == 0, res.output
    apres = io.load(fichier)
    assert apres.questions[:3] == avant.questions  # inchangées, même ordre
    nouvelles = apres.questions[3:]
    assert [q.type for q in nouvelles] == ["factual"] * 3 + ["multi_hop", "unanswerable"]
    # id neuf : jamais ceux du fichier, y compris celui d'une Question rejetée
    assert [q.id for q in nouvelles] == ["q-008", "q-009", "q-010", "q-011", "q-012"]
    for q in nouvelles:
        assert q.status == "generated" and q.split is None
        assert q.origin == {"kind": "model", "name": "fake-llm-a"}
        assert q.lang == "fr"
    assert nouvelles[0].reference_anchors[0].headings[0] == "Guide"
    assert len(nouvelles[3].reference_anchors) == 2 and nouvelles[4].reference_anchors == ()
    assert "Questions ajoutées : 5" in res.output and "Rejetées à la génération : 0" in res.output
    # le fichier produit passe le contrôle : les Ancrages se résolvent
    from wavelibrarian.corpus.declare import declare
    from wavelibrarian.corpus.ingest import ingest

    assert not check.controler(apres, ingest(declare(corpus))).echec


def test_nouveau_fichier_cree_a_cote_du_corpus(corpus: Path, env: Env) -> None:
    env.script(_sortie)
    res = _generer(corpus)
    assert res.exit_code == 0, res.output
    doc = io.load(corpus.parent / "questions.yaml")
    assert doc.corpus_id == "demo" and doc.target_count == 5 and doc.freeze is None
    assert len(doc.questions) == 5 and doc.questions[0].id == "q-001"


def test_faux_llm_par_defaut_respecte_la_repartition(corpus: Path, env: Env) -> None:
    """Le Faux LLM ignore `types` (une factual par Ancrage) : le tri borne par Type."""
    env.capture()
    res = _generer(corpus)
    assert res.exit_code == 0, res.output
    doc = io.load(corpus.parent / "questions.yaml")
    assert [q.type for q in doc.questions] == ["factual"] * 3
    assert "Écartées en surplus de la répartition : 2" in res.output
    assert "Manquantes pour multi_hop : 1" in res.output
    assert "Manquantes pour unanswerable : 1" in res.output


# --- AC 2 : Ancrage absent écarté --------------------------------------------------------------


def test_anchor_id_absent_du_corpus_ecarte(corpus: Path, env: Env) -> None:
    def sortie(req: LLMRequest) -> str:
        ids = [a["anchor_id"] for a in req.inputs["anchors"]]
        bon = {"type": "factual", "text": "Bonne", "reference_answer": "x", "answer_form": "free"}
        qs = [
            {**bon, "anchor_ids": [ids[0]]},
            {**bon, "text": "Fausse", "anchor_ids": ["zzzz#h/absent"]},
            {**bon, "text": "Mi-fausse", "anchor_ids": [ids[1], "zzzz#p9"]},
            {**bon, "text": "Sans ancrage", "anchor_ids": []},
            {**bon, "text": "Type inconnu", "type": "poetique", "anchor_ids": [ids[2]]},
            {**bon, "text": "Réponse sans réponse", "type": "unanswerable", "anchor_ids": [ids[2]]},
        ]
        return json.dumps({"questions": qs})

    env.script(sortie)
    res = _generer(corpus, repartition="factual=4,unanswerable=1")
    assert res.exit_code == 0, res.output
    doc = io.load(corpus.parent / "questions.yaml")
    assert [q.text for q in doc.questions] == ["Bonne", "Réponse sans réponse"]
    assert doc.questions[1].reference_anchors == ()  # Ancrages d'une unanswerable ignorés
    assert "Rejetées à la génération : 4" in res.output
    assert "Ancrage inconnu du Corpus" in res.output and "aucun Ancrage cité" in res.output
    assert "Type inconnu : 'poetique'" in res.output
    # forme d'écriture AD-5 : {doc, headings} (jamais d'anchor_id brut)
    brut = (corpus.parent / "questions.yaml").read_text(encoding="utf-8")
    assert "anchor_id" not in brut and "headings" in brut


def test_ancrage_page_ecrit_en_doc_page(env: Env, wl_home: Path, tmp_path: Path) -> None:
    from fpdf import FPDF

    (tmp_path / "docs").mkdir()
    pdf = FPDF()
    for texte in ("premiere", "deuxieme"):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(text=texte)
    (tmp_path / "docs" / "r.pdf").write_bytes(bytes(pdf.output()))
    spec = {
        "corpus_id": "pdf",
        "path": "docs",
        "lang": "fr",
        "license": "CC-BY-4.0",
        "publishable": True,
        "volatility": "low",
    }
    corpus = tmp_path / "corpus.yaml"
    corpus.write_text(yaml.safe_dump(spec), encoding="utf-8")
    env.capture()
    res = _generer(corpus, repartition="factual=2")
    assert res.exit_code == 0, res.output
    doc = io.load(tmp_path / "questions.yaml")
    assert [(a.doc, a.page) for q in doc.questions for a in q.reference_anchors] == [
        ("r.pdf", 1),
        ("r.pdf", 2),
    ]


# --- AC 3 : rôle, inputs, Poste, Cache ---------------------------------------------------------


def test_role_inputs_et_poste_evalset_puis_cache(corpus: Path, env: Env, wl_home: Path) -> None:
    env.script(_sortie)
    assert _generer(corpus).exit_code == 0
    (req,) = env.requetes
    assert req.role == "question_gen" and req.model_id == "fake-llm-a"
    assert set(req.inputs) >= {"anchors", "types"}
    assert req.inputs["types"] == {"factual": 3, "multi_hop": 1, "unanswerable": 1}
    assert all(set(a) == {"anchor_id", "text"} for a in req.inputs["anchors"])
    traces = wl_home / "hors-execution" / "hors-1" / "traces.jsonl"
    (span,) = [json.loads(x) for x in traces.read_text(encoding="utf-8").splitlines()]
    assert span["wl.post"] == "evalset" and span["wl.step"] == "question_gen"
    assert span["wl.status"] == "ok" and span["wl.llm_cache_hit"] is False
    assert span["wl.cost"] != "0"

    # seconde génération identique : servie par le Cache, aucun appel, coût nul
    (corpus.parent / "questions.yaml").unlink()
    res = _generer(corpus)
    assert res.exit_code == 0, res.output
    assert len(env.requetes) == 1
    assert "servi par le Cache de réponses" in res.output and "Coût : 0 " in res.output
    spans = [json.loads(x) for x in traces.read_text(encoding="utf-8").splitlines()]
    assert spans[-1]["wl.llm_cache_hit"] is True and spans[-1]["wl.cost"] == "0"


def test_generer_fixe_lui_meme_le_poste(corpus: Path, wl_home: Path) -> None:
    """`generer` ouvre son `scope(post="evalset")` : un contexte sans Poste suffit."""
    from wavelibrarian.corpus.declare import declare
    from wavelibrarian.corpus.ingest import ingest

    parsed = ingest(declare(corpus))
    vide = io.QuestionsFile(corpus_id="demo", target_count=3, questions=())
    with Context.from_profile("test", wl_home=wl_home, run_id="r-1", seed=1) as ctx:
        res = generate.generer(ctx, parsed, vide, {"factual": 2}, "fake-llm-a")
        assert len(res.ajoutees) == 2
        with pytest.raises(Exception, match="Poste de coût non fixé"):
            _ = ctx.post


# --- AC 4 : plafond ----------------------------------------------------------------------------


def test_plafond_insuffisant_code_3_sans_ecriture(corpus: Path, env: Env) -> None:
    env.budget = Budget(per_run={"fake": Amount(amount=Decimal("0.0000001"), currency="USD")})
    env.script(_sortie)
    fichier = _ecrire(corpus.parent / "questions.yaml", [_question(1)])
    octets = fichier.read_bytes()
    res = _generer(corpus)
    assert res.exit_code == 3, res.output
    assert "Plafond atteint" in res.output
    assert fichier.read_bytes() == octets  # Questions validées intactes
    assert env.requetes == []  # l'appel refusé n'est jamais parti

    sans_fichier = corpus.parent / "autre.yaml"
    res = _generer(corpus, "--questions", str(sans_fichier))
    assert res.exit_code == 3 and not sans_fichier.exists()


# --- AC 5 : échantillon déterministe -----------------------------------------------------------


def test_meme_graine_meme_echantillon(corpus: Path, env: Env, wl_home: Path) -> None:
    from wavelibrarian.corpus.declare import declare
    from wavelibrarian.corpus.ingest import ingest

    parsed = ingest(declare(corpus))

    def tirage(graine: int) -> list[str]:
        with Context.from_profile("test", wl_home=wl_home, run_id="r-1", seed=graine) as ctx:
            return generate.echantillon_ancrages(ctx, parsed, 3)

    un = tirage(1)
    assert len(un) == 3 and len(set(un)) == 3
    assert tirage(1) == un
    assert len({tuple(tirage(g)) for g in range(2, 12)} | {tuple(un)}) > 1

    # de bout en bout : la requête de la commande porte l'échantillon de la graine
    env.capture()
    assert _generer(corpus, "--graine", "1", repartition="factual=3").exit_code == 0
    assert [a["anchor_id"] for a in env.requetes[0].inputs["anchors"]] == un


# --- Catalogue, usage et refus -----------------------------------------------------------------


def test_modele_inconnu_du_catalogue_code_2_sans_appel(
    corpus: Path, env: Env, wl_home: Path
) -> None:
    env.script(_sortie)
    res = _generer(corpus, "--modele", "modele-fantome")
    assert res.exit_code == 2 and "modèle inconnu du Catalogue" in res.output
    assert env.requetes == [] and not (wl_home / "hors-execution").exists()
    assert not (corpus.parent / "questions.yaml").exists()


def test_modele_explicite_trace_dans_origin(corpus: Path, env: Env) -> None:
    env.script(_sortie)
    assert _generer(corpus, "--modele", "fake-llm-b").exit_code == 0
    doc = io.load(corpus.parent / "questions.yaml")
    assert {q.origin["name"] for q in doc.questions} == {"fake-llm-b"}
    assert env.requetes[0].model_id == "fake-llm-b"


def test_jeu_gele_et_corpus_different_refuses(corpus: Path, env: Env) -> None:
    env.script(_sortie)
    gele = {"sha256": "x", "at": "2026-10-18", "seed": 1, "dev_ratio": 0.4}
    fichier = _ecrire(corpus.parent / "questions.yaml", [_question(1)], freeze=gele)
    res = _generer(corpus)
    assert res.exit_code == 2 and "jeu gelé" in res.output
    _ecrire(fichier, [_question(1)], corpus_id="autre")
    res = _generer(corpus)
    assert res.exit_code == 2 and "autre" in res.output
    assert env.requetes == []


@pytest.mark.parametrize(
    "texte",
    ["", "factual", "factual=0", "factual=x", "inconnu=2", "factual=1,factual=2", "=3"],
)
def test_repartition_invalide(texte: str) -> None:
    with pytest.raises(ConfigError):
        generate.parse_repartition(texte)


def test_repartition_valide() -> None:
    assert generate.parse_repartition("factual=3, multi_hop=1") == {"factual": 3, "multi_hop": 1}


def test_repartition_invalide_par_la_commande(corpus: Path, env: Env) -> None:
    res = _generer(corpus, repartition="inconnu=2")
    assert res.exit_code == 2 and "Type inconnu" in res.output


# --- Revue : doublons, échantillon, --cible, coût ---------------------------------------------


def test_doublons_ecartes_dans_la_sortie_et_face_au_fichier(corpus: Path, env: Env) -> None:
    def sortie(req: LLMRequest) -> str:
        ids = [a["anchor_id"] for a in req.inputs["anchors"]]
        bon = {"type": "factual", "reference_answer": "x", "answer_form": "free"}
        qs = [
            {**bon, "text": "Quelle est la capitale ?", "anchor_ids": [ids[0]]},
            {**bon, "text": "  quelle est  la Capitale ? ", "anchor_ids": [ids[0]]},
            {**bon, "text": "Quelle est la capitale ?", "anchor_ids": [ids[1]]},  # autre Ancrage
        ]
        return json.dumps({"questions": qs})

    env.script(sortie)
    res = _generer(corpus, repartition="factual=3")
    assert res.exit_code == 0, res.output
    assert "Rejetées à la génération : 1" in res.output and "doublon de q-001" in res.output
    assert len(io.load(corpus.parent / "questions.yaml").questions) == 2
    # seconde génération identique (servie par le Cache) : rien de neuf n'est ajouté
    res = _generer(corpus, repartition="factual=3")
    assert res.exit_code == 0, res.output
    assert "Questions ajoutées : 0" in res.output and "Rejetées à la génération : 3" in res.output
    assert len(io.load(corpus.parent / "questions.yaml").questions) == 2


def test_ancrage_reel_hors_echantillon_ecarte(corpus: Path, env: Env) -> None:
    def sortie(req: LLMRequest) -> str:
        presentes = {a["anchor_id"] for a in req.inputs["anchors"]}
        from wavelibrarian.corpus.declare import declare
        from wavelibrarian.corpus.ingest import ingest

        parsed = ingest(declare(corpus))
        tous = sorted(a for d in parsed.documents for a in d.anchors)
        hors = next(a for a in tous if a not in presentes)
        q = {"type": "factual", "text": "Hors", "reference_answer": "x", "answer_form": "free"}
        return json.dumps({"questions": [{**q, "anchor_ids": [hors]}]})

    env.script(sortie)
    res = _generer(corpus, repartition="factual=1")
    assert res.exit_code == 0, res.output
    assert "Ancrage hors de l'échantillon présenté" in res.output
    assert "Questions ajoutées : 0" in res.output


def test_cible_nulle_refusee(corpus: Path, env: Env) -> None:
    res = _generer(corpus, "--cible", "0")
    assert res.exit_code == 2 and "--cible" in res.output
    assert not (corpus.parent / "questions.yaml").exists()
