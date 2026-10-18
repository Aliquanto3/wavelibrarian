"""Story 7.4 : Architecture `agentic` (outils search/read/list, bornes de pas et de coût)."""

import hashlib
import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.agentic import Agentic
from wavelibrarian.core.errors import ConfigError, NonConformantOutput
from wavelibrarian.core.types import ParsedCorpus, QuestionInput
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.runner.context import Context as RunCtx


@pytest.fixture
def ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    provider = FakeProvider()
    c = RunCtx.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-1", seed=1, providers={"fake": provider}
    )
    c.parser = "markdown"
    c.provider = provider  # type: ignore[attr-defined]
    with c:
        yield c


@pytest.fixture
def index(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> Path:
    with ctx.scope(post="indexing"):
        _arch(ctx).index(minicorpus, tmp_path / "i")
    return tmp_path / "i"


def _arch(ctx: RunCtx, **params: Any) -> Any:
    return ctx.build("architecture", ComponentSpec(name="agentic", params=params))


def _question() -> QuestionInput:
    return QuestionInput(
        question_id="q-001", text="Depuis quand Bram Oskelle est-il en poste ?", lang="fr"
    )


def _repondre(ctx: RunCtx, dossier: Path, **p: Any) -> Any:
    arch = _arch(ctx, **p)
    arch.load(dossier)
    with ctx.scope(post="query", question_id="q-001"):
        return arch, arch.answer(_question())


def _spans(ctx: RunCtx, prefixe: str = "agent.step") -> list[dict[str, Any]]:
    chemin = ctx.run_dir / "traces.jsonl"
    lignes = chemin.read_text(encoding="utf-8").splitlines() if chemin.exists() else []
    return [s for s in map(json.loads, lignes) if s["wl.step"].startswith(prefixe)]


def _script(ctx: RunCtx, sortie: Any) -> None:
    ctx.provider.script("agent_step", "agent.step*", sortie)  # type: ignore[attr-defined]


def _action(action: str, **args: Any) -> str:
    return json.dumps({"action": action, "args": args})


def _empreintes(dossier: Path) -> dict[Path, str]:
    return {
        f: hashlib.sha256(f.read_bytes()).hexdigest() for f in dossier.rglob("*") if f.is_file()
    }


def test_enregistrement_et_capacites() -> None:
    assert registry.get("architecture", "agentic") is Agentic
    assert Agentic.capabilities.retrieval_method == "provided"
    assert {"max_steps", "max_cost_per_question", "k"} <= Agentic.query_params


def test_defauts_des_bornes(ctx: RunCtx) -> None:
    p = _arch(ctx).params
    assert p.max_steps == 8
    assert p.max_cost_per_question.amount == Decimal("0.05")
    assert p.max_cost_per_question.currency == "USD"


def test_outils_en_lecture_seule_et_limites_au_corpus(
    ctx: RunCtx, index: Path, minicorpus: ParsedCorpus
) -> None:
    avant = _empreintes(index)
    arch = _arch(ctx)
    arch.load(index)
    trouves = arch._outil_search("Bram Oskelle poste")
    existants = {a for d in minicorpus.documents for a in d.anchors}
    assert trouves and {r["id"] for r in trouves} <= existants
    lu = arch._outil_read(trouves[0]["id"])
    assert lu == [{"id": trouves[0]["id"], "text": minicorpus.anchor_text(trouves[0]["id"])}]
    docs = arch._outil_list()
    assert {d["id"] for d in docs} == {d.doc_id for d in minicorpus.documents}
    assert _empreintes(index) == avant


def test_read_d_un_ancrage_inconnu_renvoie_un_message_sans_exception(
    ctx: RunCtx, index: Path
) -> None:
    arch = _arch(ctx)
    arch.load(index)
    res = arch._outil_read("nope#h/x")
    assert len(res) == 1 and res[0]["id"] == "nope#h/x" and "inconnu" in res[0]["text"]


def test_question_factuelle_search_read_answer_et_citation_valide(
    ctx: RunCtx, index: Path, minicorpus: ParsedCorpus
) -> None:
    _, rep = _repondre(ctx, index)
    existants = {a for d in minicorpus.documents for a in d.anchors}
    assert [s["wl.step"] for s in _spans(ctx)] == ["agent.step1", "agent.step2", "agent.step3"]
    assert {s["wl.post"] for s in _spans(ctx)} == {"query"}
    assert rep.retrieval_method == "provided" and not rep.abstained
    assert rep.citations and {c.anchor_id for c in rep.citations} <= existants
    assert rep.invalid_citations == 0
    assert len(rep.retrieved) == 1  # un seul extrait lu
    assert rep.retrieved[0].passage.anchor_ids[0] == rep.citations[0].anchor_id
    assert set(rep.context_anchor_ids) == {c.anchor_id for c in rep.citations}


def test_extraits_lus_dans_l_ordre_de_lecture(ctx: RunCtx, index: Path) -> None:
    arch = _arch(ctx)
    arch.load(index)
    anchors = list(arch._ancrages)[:3]
    assert len(anchors) == 3
    ordre = [anchors[2], anchors[0], anchors[1], anchors[0]]
    etapes = [_action("read", id=a) for a in ordre] + [
        _action("answer", answer="ok", citations=[anchors[1]])
    ]
    _script(ctx, lambda req: etapes[req.inputs["step"] - 1])
    with ctx.scope(post="query", question_id="q-001"):
        rep = arch.answer(_question())
    assert [s.passage.anchor_ids[0] for s in rep.retrieved] == [anchors[2], anchors[0], anchors[1]]
    assert [c.anchor_id for c in rep.citations] == [anchors[1]]


def test_citation_d_un_ancrage_non_lu_retiree_et_comptee(ctx: RunCtx, index: Path) -> None:
    arch = _arch(ctx)
    arch.load(index)
    a, b = list(arch._ancrages)[:2]
    etapes = [
        _action("read", id=a),
        _action("answer", answer="x", citations=[a, b, b, "zzz"]),
    ]
    _script(ctx, lambda req: etapes[req.inputs["step"] - 1])
    with ctx.scope(post="query", question_id="q-001"):
        rep = arch.answer(_question())
    assert [c.anchor_id for c in rep.citations] == [a]
    assert rep.invalid_citations == 2


def test_read_inconnu_cote_agent_message_renvoye_puis_reponse(ctx: RunCtx, index: Path) -> None:
    vus: list[list[dict[str, str]]] = []

    def agent(req: Any) -> str:
        vus.append(req.inputs["last_results"])
        if req.inputs["step"] == 1:
            return _action("read", id="nope#h/x")
        return _action("answer", answer="", citations=[], abstain=True)

    _script(ctx, agent)
    _, rep = _repondre(ctx, index)
    assert "inconnu" in vus[1][0]["text"]
    assert rep.abstained and rep.retrieved == ()


def test_list_renvoie_les_documents(ctx: RunCtx, index: Path, minicorpus: ParsedCorpus) -> None:
    vus: list[list[dict[str, str]]] = []

    def agent(req: Any) -> str:
        vus.append(req.inputs["last_results"])
        if req.inputs["step"] == 1:
            return _action("list")
        return _action("answer", answer="", citations=[], abstain=True)

    _script(ctx, agent)
    _repondre(ctx, index)
    assert {r["id"] for r in vus[1]} == {d.doc_id for d in minicorpus.documents}


def test_aucun_resultat_le_faux_llm_s_abstient_a_l_etape_2(ctx: RunCtx, index: Path) -> None:
    arch = _arch(ctx)
    arch.load(index)
    with ctx.scope(post="query", question_id="q-001"):
        rep = arch.answer(QuestionInput(question_id="q-001", text="zzzqqq xxyyww", lang="fr"))
    assert rep.abstained and rep.retrieved == ()
    assert len(_spans(ctx)) == 2


def test_max_steps_8_au_plus_8_appels_puis_abstention(ctx: RunCtx, index: Path) -> None:
    _script(ctx, _action("search", query="Bram"))
    _, rep = _repondre(ctx, index, max_steps=8)
    assert [s["wl.step"] for s in _spans(ctx)] == [f"agent.step{n}" for n in range(1, 9)]
    assert rep.abstained and rep.citations == ()
    # défaut : 8
    _, rep2 = _repondre(ctx, index)
    assert len(_spans(ctx)) == 16 and rep2.abstained


def test_max_steps_plus_petit(ctx: RunCtx, index: Path) -> None:
    _script(ctx, _action("list"))
    _, rep = _repondre(ctx, index, max_steps=3)
    assert len(_spans(ctx)) == 3 and rep.abstained


def test_borne_de_cout_avant_chaque_appel_et_identique_avec_cache(ctx: RunCtx, index: Path) -> None:
    _repondre(ctx, index)  # mesure : coût fictif des 3 étapes
    couts = [Decimal(s["wl.cost_uncached"]) for s in _spans(ctx)]
    assert len(couts) == 3 and all(c > 0 for c in couts)
    borne = couts[0] + couts[1] - Decimal("0.0000000001")
    amount = {"amount": str(borne), "currency": "USD"}
    avant = len(_spans(ctx))
    _, rep = _repondre(ctx, index, max_cost_per_question=amount)
    nouveaux = _spans(ctx)[avant:]
    assert [s["wl.step"] for s in nouveaux] == ["agent.step1", "agent.step2"]  # pas d'étape 3
    assert rep.abstained and rep.citations == ()
    # Cache de réponses : mêmes appels servis du cache, coût réel nul, comportement identique.
    avant = len(_spans(ctx))
    _, rep2 = _repondre(ctx, index, max_cost_per_question=amount)
    rejeu = _spans(ctx)[avant:]
    assert [s["wl.step"] for s in rejeu] == ["agent.step1", "agent.step2"]
    assert all(Decimal(s["wl.cost"]) == 0 for s in rejeu)
    assert [s["wl.cost_uncached"] for s in rejeu] == [s["wl.cost_uncached"] for s in nouveaux]
    assert rep2 == rep


def test_borne_de_cout_nulle_aucun_appel(ctx: RunCtx, index: Path) -> None:
    _, rep = _repondre(ctx, index, max_cost_per_question={"amount": "0", "currency": "USD"})
    assert _spans(ctx) == [] and rep.abstained


@pytest.mark.parametrize(
    "sortie",
    [
        json.dumps({"action": "fly", "args": {}}),
        _action("search"),
        _action("search", query=""),
        _action("read", id=3),
        _action("list", x=1),
        _action("answer", citations=[]),
        "pas du json",
    ],
)
def test_sortie_non_conforme_reessayee_une_fois_puis_erreur(
    ctx: RunCtx, index: Path, sortie: str
) -> None:
    _script(ctx, sortie)
    arch = _arch(ctx)
    arch.load(index)
    with ctx.scope(post="query", question_id="q-001"), pytest.raises(NonConformantOutput):
        arch.answer(_question())
    assert [s["wl.step"] for s in _spans(ctx)] == ["agent.step1", "agent.step1"]


def test_fenetre_reduit_les_resultats_avec_avertissement(
    ctx: RunCtx, index: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    arch = _arch(ctx)
    arch.load(index)
    gros = [{"id": "a", "text": "mot " * 2000}]
    monkeypatch.setattr(arch, "_fenetre", lambda: 1000)
    with caplog.at_level(logging.WARNING, logger="wavelibrarian.architectures.agentic"):
        h, r = arch._tenir(_question(), 3, ["étape 1 : search {} -> 1 résultat(s)"], gros)
    assert any("réduit" in m.getMessage() for m in caplog.records)
    tok = ctx.tokenizer_for(arch._modele)
    assert tok.count(r[0]["text"]) < tok.count(gros[0]["text"])
    assert tok.count(arch._contenu(_question(), 3, h, r)) <= 1000


def test_fenetre_sans_place_pour_la_question_erreur_de_configuration(
    ctx: RunCtx, index: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arch = _arch(ctx)
    arch.load(index)
    monkeypatch.setattr(arch, "_fenetre", lambda: 100)
    with pytest.raises(ConfigError):
        arch._tenir(_question(), 1, [], [])


def test_fenetre_ecarte_l_historique_ancien(
    ctx: RunCtx, index: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arch = _arch(ctx)
    arch.load(index)
    monkeypatch.setattr(arch, "_fenetre", lambda: 1000)
    historique = [f"étape {n} : search {{}} -> " + "mot " * 50 for n in range(1, 30)]
    h, _ = arch._tenir(_question(), 30, historique, [])
    assert 0 < len(h) < len(historique) and h == historique[-len(h) :]


def test_index_key_ne_depend_pas_des_bornes(ctx: RunCtx) -> None:
    assert _arch(ctx).index_key() == _arch(ctx, max_steps=2, k=3).index_key()
