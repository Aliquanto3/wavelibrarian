"""Story 9.4 : paquet court, tirage stratifié, double annotation, page et import d'annotation."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from wavelibrarian.cli import app
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.report.importer import importer_verdicts
from wavelibrarian.report.lecture import lire_reponses
from wavelibrarian.report.page_annotation import donnees_de_page, generer_page
from wavelibrarian.report.paquet import (
    DONNEES_DE_REPONSE,
    exporter_depuis,
    exporter_paquet,
    lire_paquet,
    repartir,
)
from wavelibrarian.scoring.calibration import charger_dossier, charger_fichier, lire_yaml

RACINE = Path(__file__).resolve().parents[3] / "corpora" / "minicorpus"
ANAEL = RACINE / "annotations" / "anael.yaml"
DONNEES: dict[str, Any] = {
    "experiment_id": "exp-9-4",
    "seed": 42,
    "profile": "test",
    "corpus": str(RACINE / "corpus.yaml"),
    "questions": str(RACINE / "questions.yaml"),
    "split": "dev",
    "max_questions": 5,
    "tier": "all",
    "conditions": ["standard"],
    "retries": {"max_attempts": 1, "backoff_s": 0.0, "max_backoff_s": 0.0},
    "configurations": [
        {"id": "sans-contexte", "architecture": "no_context"},
        {"id": "bm25", "architecture": "bm25_only"},
    ],
}
CLES_COURTES = {"answer_id", "criterion", "verdict", "note"}
PASSAGES = ("context_passages", "reference_passages")


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("run-9-4")
    home = base / "wl_home"
    home.mkdir()
    chemin = base / "exp.yaml"
    chemin.write_text(yaml.safe_dump(DONNEES, allow_unicode=True), encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setenv("WL_HOME", str(home))
    try:
        res = CliRunner().invoke(app, ["run", str(chemin)])
        assert res.exit_code == 0, res.output
        (dossier,) = [d for d in (home / "runs").iterdir() if d.is_dir()]
    finally:
        mp.undo()
    return dossier


def _lignes(f: Path) -> list[dict[str, Any]]:
    return lire_paquet(f)["annotations"]


def _annoter(f: Path) -> None:
    """Remplit les verdicts (yes, no, na en rotation) et une note sur la première ligne."""
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    for i, a in enumerate(doc["annotations"]):
        a["verdict"] = ("yes", "no", "na")[i % 3]
    doc["annotations"][0]["note"] = "déjà là"
    f.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


# --- allocation -----------------------------------------------------------------------------


def test_repartir_proportionnel_et_somme_exacte() -> None:
    r = repartir({"a": 60, "b": 30, "c": 10}, 10)
    assert r == {"a": 6, "b": 3, "c": 1}
    r = repartir({"a": 50, "b": 30, "c": 20}, 7)
    assert sum(r.values()) == 7 and r == {"a": 4, "b": 2, "c": 1}


def test_repartir_au_moins_une_par_strate_non_vide() -> None:
    r = repartir({"a": 100, "b": 2, "c": 1, "d": 0}, 6)
    assert sum(r.values()) == 6
    assert r["b"] >= 1 and r["c"] >= 1 and "d" not in r
    assert r["a"] == 4


def test_repartir_moins_de_tirages_que_de_strates() -> None:
    # Les strates aux plus grands quotas passent d'abord ; égalité : ordre des noms.
    assert repartir({"a": 5, "b": 9, "c": 1}, 2) == {"a": 1, "b": 1, "c": 0}
    assert repartir({"a": 3, "b": 3}, 1) == {"a": 1, "b": 0}


def test_repartir_ne_depasse_pas_la_taille_des_strates() -> None:
    assert repartir({"a": 2, "b": 3}, 99) == {"a": 2, "b": 3}
    r = repartir({"a": 1, "b": 20}, 10)
    assert r["a"] == 1 and r["b"] == 9


# --- paquet court ---------------------------------------------------------------------------


def test_donnees_de_reponse_sur_la_premiere_ligne_seulement(run_dir: Path, tmp_path: Path) -> None:
    exporter_paquet(run_dir, tmp_path / "p", annotateurs=["a"], nombre=500)
    lignes = _lignes(tmp_path / "p" / "a.yaml")
    vues: set[str] = set()
    for a in lignes:
        if a["answer_id"] not in vues:
            vues.add(a["answer_id"])
            assert set(DONNEES_DE_REPONSE) <= set(a)
            assert all(isinstance(x, str) for x in a["cited_anchors"])
        else:
            assert set(a) == CLES_COURTES
    assert any(set(a) == CLES_COURTES for a in lignes)


def test_tirage_stratifie_repartition_et_stabilite(run_dir: Path, tmp_path: Path) -> None:
    p = exporter_paquet(run_dir, tmp_path / "a", annotateurs=["x"], nombre=6, graine=3)
    assert p.n_reponses == 6
    assert sum(r for r, _ in p.repartition.values()) == 6
    assert sum(d for _, d in p.repartition.values()) == p.n_eligibles
    assert all(" × " in k and 0 <= r <= d for k, (r, d) in p.repartition.items())
    n_strates = len(p.repartition)
    assert n_strates >= 2
    # Chaque strate non vide a une Réponse dès que N le permet.
    q = exporter_paquet(run_dir, tmp_path / "b", annotateurs=["x"], nombre=n_strates, graine=3)
    assert all(r >= 1 for r, _ in q.repartition.values())
    exporter_paquet(run_dir, tmp_path / "c", annotateurs=["x"], nombre=6, graine=3)
    assert (tmp_path / "a" / "x.yaml").read_bytes() == (tmp_path / "c" / "x.yaml").read_bytes()
    # Les Réponses tirées respectent l'allocation : décompte par Configuration.
    ids = {a["answer_id"] for a in _lignes(tmp_path / "a" / "x.yaml")}
    par_config: dict[str, int] = {}
    for i in ids:
        c = i.split("/")[1]
        par_config[c] = par_config.get(c, 0) + 1
    attendu: dict[str, int] = {}
    for k, (r, _) in p.repartition.items():
        attendu[k.split(" × ")[0]] = attendu.get(k.split(" × ")[0], 0) + r
    assert par_config == {c: n for c, n in attendu.items() if n}


def test_mesure_taille_par_reponse_sur_anael(tmp_path: Path) -> None:
    """anael.yaml (ancien format) relu puis ré-exporté en paquet court : plus petit, mêmes
    Réponses et Critères, même contenu."""
    avant = ANAEL.read_text(encoding="utf-8")
    p = exporter_depuis(ANAEL, tmp_path, annotateurs=["bob"], nombre=10_000)
    apres = (tmp_path / "bob.yaml").read_text(encoding="utf-8")
    assert p.n_reponses == 40 and p.n_lignes == 92
    assert len(apres) < 0.5 * len(avant)  # mesure de la spec : -63 %
    vieux, neuf = _lignes(ANAEL), _lignes(tmp_path / "bob.yaml")
    assert [(a["answer_id"], a["criterion"]) for a in neuf] == [
        (a["answer_id"], a["criterion"]) for a in vieux
    ]
    assert all(a["verdict"] == "" and a["note"] == "" for a in neuf)
    for ancien in vieux:
        premiere = next(a for a in neuf if a["answer_id"] == ancien["answer_id"])
        for cle in ("question", "reference_answer", "answer", "cited_anchors", *PASSAGES):
            if cle in ancien:  # Passages en clair sur la première ligne de l'ancien format
                assert premiere[cle] == ancien[cle]


def test_anael_reste_chargeable_tel_quel() -> None:
    ann = charger_dossier(ANAEL.parent)
    assert ann.annotateurs == ["anael"]
    assert len(ann.verdicts) == 92
    assert set(ann.verdicts.values()) <= {"yes", "no", "na"}


# --- double annotation ----------------------------------------------------------------------


def test_depuis_tire_les_lignes_annotees_par_critere(run_dir: Path, tmp_path: Path) -> None:
    src = tmp_path / "src"
    exporter_paquet(run_dir, src, annotateurs=["ana"], nombre=12, graine=1)
    _annoter(src / "ana.yaml")
    # Une ligne laissée vide ne doit jamais être tirée.
    doc = yaml.safe_load((src / "ana.yaml").read_text(encoding="utf-8"))
    doc["annotations"][1]["verdict"] = ""
    vide = (doc["annotations"][1]["answer_id"], doc["annotations"][1]["criterion"])
    (src / "ana.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    sources = _lignes(src / "ana.yaml")
    n_crit = {
        c: sum(1 for a in sources if a["criterion"] == c and a["verdict"])
        for c in ("correctness", "completeness", "faithfulness")
    }

    p = exporter_depuis(src / "ana.yaml", tmp_path / "dbl", annotateurs=["bob"], nombre=9, graine=5)
    neuf = _lignes(tmp_path / "dbl" / "bob.yaml")
    assert len(neuf) == p.n_lignes == 9
    assert (vide[0], vide[1]) not in {(a["answer_id"], a["criterion"]) for a in neuf}
    assert all(a["verdict"] == "" and a["note"] == "" for a in neuf)
    cles = {(a["answer_id"], a["criterion"]) for a in sources if a["verdict"]}
    assert {(a["answer_id"], a["criterion"]) for a in neuf} <= cles
    # Répartition par Critère : somme exacte, au moins une ligne par Critère annoté.
    assert sum(r for r, _ in p.repartition.values()) == 9
    assert {k: d for k, (_, d) in p.repartition.items()} == {c: n for c, n in n_crit.items() if n}
    assert all(r >= 1 for r, _ in p.repartition.values())
    # Données de la Réponse sur la première ligne retenue de chaque Réponse seulement.
    vues: set[str] = set()
    for a in neuf:
        if a["answer_id"] not in vues:
            vues.add(a["answer_id"])
            assert set(DONNEES_DE_REPONSE) <= set(a)
        else:
            assert set(a) == CLES_COURTES
    assert p.n_reponses == len(vues)
    # Stable à graine égale, différent sinon.
    exporter_depuis(src / "ana.yaml", tmp_path / "dbl2", annotateurs=["bob"], nombre=9, graine=5)
    assert (tmp_path / "dbl" / "bob.yaml").read_bytes() == (
        tmp_path / "dbl2" / "bob.yaml"
    ).read_bytes()


def test_depuis_refus(run_dir: Path, tmp_path: Path) -> None:
    src = tmp_path / "src"
    exporter_paquet(run_dir, src, annotateurs=["ana"], nombre=3)
    with pytest.raises(ConfigError, match="aucune ligne annotée"):
        exporter_depuis(src / "ana.yaml", tmp_path / "o1", annotateurs=["bob"])
    _annoter(src / "ana.yaml")
    with pytest.raises(ConfigError, match="a déjà annoté"):
        exporter_depuis(src / "ana.yaml", tmp_path / "o2", annotateurs=["Ana"])
    with pytest.raises(ConfigError, match="introuvable"):
        exporter_depuis(tmp_path / "absent.yaml", tmp_path / "o3", annotateurs=["bob"])
    with pytest.raises(ConfigError, match="au moins une ligne"):
        exporter_depuis(src / "ana.yaml", tmp_path / "o4", annotateurs=["bob"], nombre=0)
    exporter_depuis(src / "ana.yaml", tmp_path / "o5", annotateurs=["bob"])
    with pytest.raises(ConfigError, match="--ecraser"):
        exporter_depuis(src / "ana.yaml", tmp_path / "o5", annotateurs=["bob"])
    exporter_depuis(src / "ana.yaml", tmp_path / "o5", annotateurs=["bob"], ecraser=True)


def test_cli_depuis_et_repartition(run_dir: Path, tmp_path: Path, monkeypatch: Any) -> None:
    home = run_dir.parent.parent
    monkeypatch.setenv("WL_HOME", str(home))
    r = CliRunner().invoke(
        app,
        ["annotations", "exporter", run_dir.name, "--vers", str(tmp_path / "p"), "--nombre", "6"],
    )
    assert r.exit_code == 0, r.output
    assert "Répartition par strate (retenues / disponibles) :" in r.output
    assert re.search(r"  \S+ × \w+ : \d+ / \d+", r.output)
    _annoter(tmp_path / "p" / "anael.yaml")
    r = CliRunner().invoke(
        app,
        ["annotations", "exporter", "--depuis", str(tmp_path / "p" / "anael.yaml"),
         "--vers", str(tmp_path / "d"), "--annotateurs", "bob", "--nombre", "4"],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    assert "Paquet de 4 ligne(s)" in r.output and "  faithfulness : " in r.output
    both = CliRunner().invoke(
        app,
        [
            "annotations",
            "exporter",
            run_dir.name,
            "--depuis",
            "x.yaml",
            "--vers",
            str(tmp_path / "e"),
        ],
    )
    assert both.exit_code == 2 and "pas les deux" in both.output
    neither = CliRunner().invoke(app, ["annotations", "exporter", "--vers", str(tmp_path / "e")])
    assert neither.exit_code == 2


# --- page -----------------------------------------------------------------------------------

PIEGE = "</script><img src=x onerror=alert(1)> <!--   \" ' &amp;"


def _paquet_piege(chemin: Path, annotateur: str = "ana") -> Path:
    doc = {
        "annotator": annotateur,
        "annotations": [
            {
                "answer_id": "r1/bm25/standard/all/base/q-001",
                "criterion": "correctness",
                "verdict": "yes",
                "note": "SECRET-NOTE",
                "question": "Quelle " + PIEGE,
                "reference_answer": "REFERENCE-TEXTE",
                "answer": "Réponse " + PIEGE,
                "cited_anchors": ["d#p1"],
                "reference_passages": ["PASSAGE-REF"],
                "context_passages": ["EXTRAIT-CTX " + PIEGE],
            },
            {
                "answer_id": "r1/bm25/standard/all/base/q-001",
                "criterion": "faithfulness",
                "verdict": "no",
                "note": "",
            },
        ],
    }
    chemin.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return chemin


def _charge(html: str) -> dict[str, Any]:
    m = re.search(r"const DATA=(.*?);\nconst KEY", html, re.S)
    assert m
    return json.loads(m.group(1))


def test_page_autonome_a_l_aveugle_sans_surlignage(tmp_path: Path) -> None:
    n = generer_page(_paquet_piege(tmp_path / "p.yaml"), tmp_path / "sortie" / "page.html")
    assert n == 1
    html = (tmp_path / "sortie" / "page.html").read_text(encoding="utf-8")
    # Hors ligne : aucune ressource externe.
    assert not re.search(r"(src|href)\s*=\s*[\"']?(https?:)?//", html)
    assert "http://" not in html and "https://" not in html
    assert "@import" not in html and "<link" not in html
    # À l'aveugle : ni verdict ni note saisis dans la page.
    assert "SECRET-NOTE" not in html
    assert "verdict" not in _charge(html)["items"][0]
    # Sans surlignage.
    assert "<mark" not in html and "mark{" not in html and "hl(" not in html
    # Oui, non, sans objet ; consigne stricte d'étayage.
    for mot in ("Oui", "Non", "Sans objet", 'data-v="na"'):
        assert mot in html
    assert "Une Réponse fidèle à un extrait faux reste <b>fidèle</b>" in html
    assert "(vide, abstention) est <b>sans objet</b>" in html
    # Export attendu par l'importer.
    assert '"verdicts-"+DATA.annotator+".json"' in html


def test_page_echappe_le_contenu_non_fiable(tmp_path: Path) -> None:
    generer_page(_paquet_piege(tmp_path / "p.yaml"), tmp_path / "page.html")
    html = (tmp_path / "page.html").read_text(encoding="utf-8")
    # La charge ne peut pas fermer le <script> ni ouvrir un commentaire, ni couper une ligne JS.
    charge = html.split("const DATA=", 1)[1].split(";\nconst KEY", 1)[0]
    assert "<" not in charge and " " not in charge
    assert html.count("</script>") == 1  # celui de la page
    assert "<img src=x" not in html
    # Rien n'est perdu à l'aller-retour JSON.
    assert _charge(html)["items"][0]["answer"] == "Réponse " + PIEGE
    # Tout champ affiché passe par esc() ; le seul innerHTML construit n'insère que de l'échappé.
    rendu = html.split("function render()", 1)[1]
    nus = re.findall(r"(?<!esc\()it\.(?:question|answer|reference_answer)\b", rendu)
    assert nus == []  # question, réponse et référence ne sont jamais insérées sans esc()
    assert "esc(it.question)" in rendu and "esc(it.answer)" in rendu
    assert "${p}" not in rendu and "${v.note}" not in rendu
    assert 'const esc=s=>String(s??"").replace(/[&<>"\']/g' in html


def test_page_reference_seulement_pour_correctness_et_completeness(tmp_path: Path) -> None:
    generer_page(_paquet_piege(tmp_path / "p.yaml"), tmp_path / "page.html")
    html = (tmp_path / "page.html").read_text(encoding="utf-8")
    rendu = html.split("function render()", 1)[1]
    # La réponse attendue n'est écrite que dans la branche des Critères de référence.
    assert rendu.count("it.reference_answer") == 1 and rendu.count("it.reference_passages") == 1
    avant_else, apres_else = rendu.split("else {", 1)
    assert (
        "it.reference_answer" in avant_else
        and "reference" not in apres_else.split('h+=`<div class="btns"')[0]
    )
    assert 'const REF=new Set(["correctness","completeness"])' in html
    # Les extraits du Generator ne vont qu'au bloc fidélité.
    assert "it.context_passages" not in avant_else.split("for(const c")[1]


def test_page_lit_les_deux_formats(tmp_path: Path) -> None:
    d = donnees_de_page(ANAEL)
    assert d["annotator"] == "anael" and len(d["items"]) == 40
    assert all("verdict" not in i and "note" not in i for i in d["items"])
    assert all(i["question"] and i["criteria"] for i in d["items"])
    # Tri par Question puis identifiant.
    cles = [(i["id"].rsplit("/", 1)[-1], i["id"]) for i in d["items"]]
    assert cles == sorted(cles)
    # Nouveau format (données sur la première ligne seulement) : mêmes Réponses, même contenu.
    exporter_depuis(ANAEL, tmp_path, annotateurs=["bob"], nombre=10_000)
    n = donnees_de_page(tmp_path / "bob.yaml")
    assert [(i["id"], i["criteria"]) for i in n["items"]] == [
        (i["id"], i["criteria"]) for i in d["items"]
    ]
    assert [i.get("answer") for i in n["items"]] == [i.get("answer") for i in d["items"]]


def test_page_paquet_invalide(tmp_path: Path) -> None:
    f = tmp_path / "x.yaml"
    f.write_text("annotator: a\nannotations: []\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="liste non vide"):
        generer_page(f, tmp_path / "p.html")
    f.write_text(
        "annotator: a\nannotations:\n- {answer_id: r/c/s/t/b/q, criterion: bof}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="Critère"):
        generer_page(f, tmp_path / "p.html")
    r = CliRunner().invoke(app, ["annotations", "page", str(f), "--vers", str(tmp_path / "p.html")])
    assert r.exit_code == 2 and not (tmp_path / "p.html").exists()


# --- import ---------------------------------------------------------------------------------


def _verdicts_json(chemin: Path, paquet: Path, annotateur: str = "ana") -> dict[str, Any]:
    v: dict[str, Any] = {}
    for i, a in enumerate(_lignes(paquet)):
        cle = f"{a['answer_id']}|{a['criterion']}"
        v[cle] = {"verdict": ("yes", "no", "na")[i % 3], "note": ""}
    premiere = next(iter(v))
    v[premiere]["note"] = '  Note : avec "guillemets", deux-points: et é \\ accent  '
    chemin.write_text(json.dumps({"annotator": annotateur, "verdicts": v}), encoding="utf-8")
    return v


def test_import_aller_retour_ligne_a_ligne(run_dir: Path, tmp_path: Path) -> None:
    exporter_paquet(run_dir, tmp_path / "p", annotateurs=["ana"], nombre=5)
    paquet = tmp_path / "p" / "ana.yaml"
    avant = paquet.read_text(encoding="utf-8")
    v = _verdicts_json(tmp_path / "v.json", paquet)
    res = importer_verdicts(paquet, tmp_path / "v.json")
    apres = paquet.read_text(encoding="utf-8")
    assert res.verdicts == len(v) and res.notes == 1 and res.sans_verdict == 0
    assert res.inconnus == []
    # Seules les lignes verdict / note ont changé ; le reste est identique, dans l'ordre.
    la, lb = avant.split("\n"), apres.split("\n")
    assert len(la) == len(lb)
    diff = [(x, y) for x, y in zip(la, lb, strict=True) if x != y]
    assert len(diff) == len(v) + 1
    assert all(x.startswith(("  verdict: ", "  note: ")) for x, _ in diff)
    # Le paquet relu porte les verdicts et la note, et passe le chargeur de la 5.1.
    docs = _lignes(paquet)
    for a in docs:
        assert a["verdict"] == v[f"{a['answer_id']}|{a['criterion']}"]["verdict"]
    assert docs[0]["note"] == 'Note : avec "guillemets", deux-points: et é \\ accent'
    assert all(a["note"] == "" for a in docs[1:])
    ann = charger_fichier(paquet)
    assert len(ann) == len(v) and {"yes", "no", "na"} == set(ann.values())
    assert charger_dossier(paquet.parent).annotateurs == ["ana"]


def test_import_partiel_et_note_existante_conservee(tmp_path: Path) -> None:
    copie = tmp_path / "anael.yaml"
    copie.write_text(ANAEL.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    lignes = _lignes(copie)
    cible = lignes[0]
    avec_note = next(a for a in lignes if a["note"])
    vers = {
        f"{cible['answer_id']}|{cible['criterion']}": {"verdict": "na", "note": "Sans objet : x"},
        f"{avec_note['answer_id']}|{avec_note['criterion']}": {"verdict": "", "note": "écrasée"},
        "r/c/s/t/b/q-999|correctness": {"verdict": "yes"},
    }
    (tmp_path / "v.json").write_text(
        json.dumps({"annotator": "anael", "verdicts": vers}), encoding="utf-8"
    )
    res = importer_verdicts(copie, tmp_path / "v.json")
    assert res.verdicts == (0 if cible["verdict"] == "na" else 1)
    assert res.inconnus == ["r/c/s/t/b/q-999|correctness"]
    apres = _lignes(copie)
    assert apres[0]["verdict"] == "na"
    # Le reste du paquet est inchangé (notes déjà saisies comprises).
    for x, y in zip(lignes[1:], apres[1:], strict=True):
        assert x == y
    assert next(a for a in apres if a["note"] and a["answer_id"] == avec_note["answer_id"])
    assert len(charger_fichier(copie)) == 92


def test_import_refus_et_aucun_ecrit(run_dir: Path, tmp_path: Path) -> None:
    exporter_paquet(run_dir, tmp_path / "p", annotateurs=["ana"], nombre=2)
    paquet = tmp_path / "p" / "ana.yaml"
    avant = paquet.read_bytes()
    v = tmp_path / "v.json"
    _verdicts_json(v, paquet, annotateur="bob")
    with pytest.raises(ConfigError, match="verdicts de 'bob'"):
        importer_verdicts(paquet, v)
    v.write_text(
        json.dumps({"annotator": "ana", "verdicts": {"a|b": {"verdict": "peut-être"}}}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="verdict inconnu 'peut-être'"):
        importer_verdicts(paquet, v)
    v.write_text("{pas du json", encoding="utf-8")
    with pytest.raises(ConfigError, match="lecture impossible"):
        importer_verdicts(paquet, v)
    v.write_text('{"annotator": "ana"}', encoding="utf-8")
    with pytest.raises(ConfigError, match="verdicts"):
        importer_verdicts(paquet, v)
    assert paquet.read_bytes() == avant
    assert not list(paquet.parent.glob("*.tmp-import"))
    r = CliRunner().invoke(app, ["annotations", "importer", str(paquet), str(v)])
    assert r.exit_code == 2


def test_cli_page_puis_importer(run_dir: Path, tmp_path: Path) -> None:
    exporter_paquet(run_dir, tmp_path / "p", annotateurs=["ana"], nombre=3)
    paquet = tmp_path / "p" / "ana.yaml"
    r = CliRunner().invoke(
        app, ["annotations", "page", str(paquet), "--vers", str(tmp_path / "a.html")]
    )
    assert r.exit_code == 0 and "Page de 3 Réponse(s)" in r.output
    assert (tmp_path / "a.html").is_file()
    _verdicts_json(tmp_path / "v.json", paquet)
    r = CliRunner().invoke(app, ["annotations", "importer", str(paquet), str(tmp_path / "v.json")])
    assert r.exit_code == 0, r.output
    assert "0 ligne(s) sans verdict" in r.output
    assert len(charger_fichier(paquet)) == len(_lignes(paquet))


def test_scripts_retires() -> None:
    racine = Path(__file__).resolve().parents[3]
    assert not (racine / "scripts" / "page_annotation.py").exists()
    assert not (racine / "scripts" / "importer_verdicts.py").exists()


# --- revue : table des Passages, page filtrée, import robuste ---------------------------------


def test_table_des_passages_partagee_et_sans_perte(run_dir: Path, tmp_path: Path) -> None:
    """Chaque Passage une fois dans `passages` ; les lignes s'y réfèrent ; la relecture rend le
    texte exact reçu par les Juges (`context_texts`), sans troncature."""
    exporter_paquet(run_dir, tmp_path / "p", annotateurs=["a"], nombre=500)
    brut = lire_yaml(tmp_path / "p" / "a.yaml")
    assert list(brut)[:2] == ["annotator", "passages"]
    table = brut["passages"]
    assert table and all(set(e) <= {"anchor", "text"} for e in table.values())
    textes = [(e.get("anchor"), e["text"]) for e in table.values()]
    assert len(textes) == len(set(textes))  # chaque Passage une seule fois
    refs = [r for a in brut["annotations"] for r in a.get("context_passages", [])]
    assert len(refs) > len(table)  # des Passages se répètent d'une Réponse à l'autre
    assert all(re.fullmatch(r"S\d+ [0-9a-f]{8}", r) for r in refs)
    contextes = {a.answer_id: list(a.context_texts) for a in lire_reponses(run_dir).values()}
    n = 0
    for ligne in lire_paquet(tmp_path / "p" / "a.yaml")["annotations"]:
        if "context_passages" in ligne:
            assert ligne["context_passages"] == contextes[ligne["answer_id"]]
            n += 1
    assert n > 0
    # Le chargeur de la 5.1 ignore la table.
    _annoter(tmp_path / "p" / "a.yaml")
    assert len(charger_fichier(tmp_path / "p" / "a.yaml")) == len(brut["annotations"])


def test_reference_de_passage_inconnue_refusee(tmp_path: Path) -> None:
    doc = {
        "annotator": "ana",
        "passages": {"abcdef12": {"text": "x"}},
        "annotations": [
            {
                "answer_id": "r/c/s/t/b/q-1",
                "criterion": "faithfulness",
                "verdict": "",
                "note": "",
                "context_passages": ["S1 00000000"],
            }
        ],
    }
    (tmp_path / "p.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ConfigError, match="absent de la table"):
        generer_page(tmp_path / "p.yaml", tmp_path / "p.html")


def test_depuis_recopie_la_table_utile(run_dir: Path, tmp_path: Path) -> None:
    src = tmp_path / "src"
    exporter_paquet(run_dir, src, annotateurs=["ana"], nombre=12, graine=1)
    _annoter(src / "ana.yaml")
    exporter_depuis(src / "ana.yaml", tmp_path / "d", annotateurs=["bob"], nombre=2, graine=5)
    table_src = lire_yaml(src / "ana.yaml")["passages"]
    brut = lire_yaml(tmp_path / "d" / "bob.yaml")
    utiles = {r.split()[-1] for a in brut["annotations"] for k in PASSAGES for r in a.get(k, [])}
    assert set(brut["passages"]) == utiles  # seulement la table utile
    assert all(brut["passages"][k] == table_src[k] for k in utiles)  # mêmes clés, mêmes textes


def test_depuis_refuse_d_ecraser_sa_source(run_dir: Path, tmp_path: Path) -> None:
    src = tmp_path / "src"
    exporter_paquet(run_dir, src, annotateurs=["ana"], nombre=3)
    _annoter(src / "ana.yaml")
    copie = src / "bob.yaml"
    doc = lire_yaml(src / "ana.yaml")
    doc["annotator"] = "zoe"
    copie.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    avant = copie.read_bytes()
    with pytest.raises(ConfigError, match="serait écrasé"):
        exporter_depuis(copie, src, annotateurs=["bob"], ecraser=True)
    assert copie.read_bytes() == avant
    args = ["annotations", "exporter", "--depuis", str(copie), "--vers", str(src)]
    r = CliRunner().invoke(app, [*args, "--annotateurs", "bob", "--ecraser"])
    assert r.exit_code == 2 and copie.read_bytes() == avant


def test_depuis_answer_id_absent_refuse(tmp_path: Path) -> None:
    doc = {
        "annotator": "ana",
        "annotations": [{"criterion": "correctness", "verdict": "yes", "note": ""}],
    }
    (tmp_path / "s.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ConfigError, match="answer_id"):
        exporter_depuis(tmp_path / "s.yaml", tmp_path / "o", annotateurs=["bob"])


def test_page_sans_reference_pour_un_item_fidelite_seul(tmp_path: Path) -> None:
    doc = lire_yaml(_paquet_piege(tmp_path / "p.yaml"))
    doc["annotations"] = [{**doc["annotations"][0], "criterion": "faithfulness"}]
    (tmp_path / "f.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    (item,) = donnees_de_page(tmp_path / "f.yaml")["items"]
    assert "reference_answer" not in item and "reference_passages" not in item
    assert item["context_passages"]
    doc["annotations"] = [{**doc["annotations"][0], "criterion": "correctness"}]
    (tmp_path / "c.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    (item,) = donnees_de_page(tmp_path / "c.yaml")["items"]
    assert "context_passages" not in item and item["reference_answer"] == "REFERENCE-TEXTE"


def test_page_doublon_de_critere_et_answer_id_absent(tmp_path: Path) -> None:
    doc = lire_yaml(_paquet_piege(tmp_path / "p.yaml"))
    doc["annotations"].append(dict(doc["annotations"][1]))
    (tmp_path / "d.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigError, match="doublon"):
        donnees_de_page(tmp_path / "d.yaml")
    del doc["annotations"][2]["answer_id"]
    (tmp_path / "a.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigError, match="answer_id"):
        donnees_de_page(tmp_path / "a.yaml")
    with pytest.raises(ConfigError, match="paquet lui-même"):
        generer_page(tmp_path / "p.yaml", tmp_path / "p.yaml")


def _paquet_minimal(chemin: Path, newline: str = "\n") -> Path:
    texte = (
        "# entête\nannotator: ana\nannotations:\n"
        "- answer_id: r/c/s/t/b/q-1\n  criterion: correctness\n  verdict: ''\n  note: ''\n"
        "- answer_id: r/c/s/t/b/q-1\n  criterion: faithfulness\n  verdict: 'yes'\n  note: ''\n"
    )
    chemin.write_bytes(texte.replace("\n", newline).encode("utf-8"))
    return chemin


def _json(chemin: Path, verdicts: dict[str, Any]) -> Path:
    chemin.write_text(json.dumps({"annotator": "ana", "verdicts": verdicts}), encoding="utf-8")
    return chemin


@pytest.mark.parametrize(
    "note",
    [
        "a \\ b # c",
        'guillemets " et \\" mêlés',
        "fin\u0085de ligne NEL,   et  ",
        "contrôle \x07 et DEL \x7f",
        "  # commence par un dièse  ",
    ],
)
def test_import_notes_speciales_relues_a_l_identique(tmp_path: Path, note: str) -> None:
    paquet = _paquet_minimal(tmp_path / "p.yaml")
    v = _json(tmp_path / "v.json", {"r/c/s/t/b/q-1|correctness": {"verdict": "no", "note": note}})
    res = importer_verdicts(paquet, v)
    assert res.notes == 1
    assert lire_yaml(paquet)["annotations"][0]["note"] == note.strip()


def test_import_note_nulle_et_verdict_vide(tmp_path: Path) -> None:
    paquet = _paquet_minimal(tmp_path / "p.yaml")
    v = _json(
        tmp_path / "v.json",
        {
            "r/c/s/t/b/q-1|correctness": {"verdict": "yes", "note": None},
            "r/c/s/t/b/q-1|faithfulness": {"verdict": ""},  # vidé dans la page
        },
    )
    res = importer_verdicts(paquet, v)
    lignes = lire_yaml(paquet)["annotations"]
    assert lignes[0]["note"] == "" and "None" not in paquet.read_text(encoding="utf-8")
    assert lignes[1]["verdict"] == "yes"  # pas effacé...
    assert res.vides_conserves == ["r/c/s/t/b/q-1|faithfulness"]  # ...mais signalé
    r = CliRunner().invoke(app, ["annotations", "importer", str(paquet), str(v)])
    assert r.exit_code == 0 and "vidé(s) dans la page, conservé(s)" in r.output


def test_import_garde_les_fins_de_ligne_crlf(tmp_path: Path) -> None:
    paquet = _paquet_minimal(tmp_path / "p.yaml", newline="\r\n")
    v = _json(tmp_path / "v.json", {"r/c/s/t/b/q-1|correctness": {"verdict": "na", "note": "n"}})
    importer_verdicts(paquet, v)
    octets = paquet.read_bytes()
    assert octets.count(b"\r\n") == octets.count(b"\n") == 11
    assert b'  verdict: na\r\n  note: "n"\r\n' in octets
    assert not list(tmp_path.glob("*.tmp-import"))


def test_import_entree_sans_answer_id_en_tete_refusee(tmp_path: Path) -> None:
    """Une entrée qui ne commence pas par `answer_id` ne reçoit pas le verdict de la
    précédente : l'import est refusé, rien n'est écrit."""
    paquet = tmp_path / "p.yaml"
    paquet.write_text(
        "annotator: ana\nannotations:\n"
        "- answer_id: r/q-1\n  criterion: correctness\n  verdict: ''\n  note: ''\n"
        "- criterion: completeness\n  answer_id: r/q-1\n  verdict: ''\n  note: ''\n",
        encoding="utf-8",
    )
    avant = paquet.read_bytes()
    v = _json(
        tmp_path / "v.json",
        {"r/q-1|correctness": {"verdict": "yes"}, "r/q-1|completeness": {"verdict": "no"}},
    )
    with pytest.raises(ConfigError, match="non reconnues"):
        importer_verdicts(paquet, v)
    assert paquet.read_bytes() == avant


def test_table_collision_de_cle_courte_deterministe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deux Passages dont les empreintes partagent 8 caractères : le second prend 16 caractères,
    dans l'ordre d'insertion, et chacun se relit à l'identique."""
    import wavelibrarian.report.paquet as mod

    empreintes = {"un": "abcdef0011111111", "deux": "abcdef0022222222"}
    monkeypatch.setattr(mod, "sha16", lambda _p, _a, texte: empreintes[texte])
    cles = []
    for _ in range(2):
        t = mod.TablePassages()
        cles.append((t.contexte("[S1] (d#1) un"), t.reference("deux"), t.reference("un", "d#1")))
        assert t.entrees == {
            "abcdef00": {"anchor": "d#1", "text": "un"},
            "abcdef0022222222": {"text": "deux"},
        }
        doc = {
            "passages": t.entrees,
            "annotations": [
                {"context_passages": [cles[-1][0]], "reference_passages": [cles[-1][1]]}
            ],
        }
        relu = mod.resoudre_passages(doc)["annotations"][0]
        assert relu == {"context_passages": ["[S1] (d#1) un"], "reference_passages": ["deux"]}
    assert cles[0] == cles[1] == ("S1 abcdef00", "abcdef0022222222", "abcdef00")


def test_import_aller_retour_table_multiligne(tmp_path: Path) -> None:
    """Table `passages` à textes multilignes et caractères YAML spéciaux (y compris des lignes
    qui ressemblent à `- answer_id:` ou `verdict:`) : seules les lignes verdict et note changent,
    les Passages se relisent à l'identique."""
    from wavelibrarian.report.paquet import ENTETE, TablePassages, _Dumper

    t = TablePassages()
    ctx = [
        t.contexte("[S1] (doc#a) l1  \n  verdict: no\n- answer_id: zz\n\ttab"),
        t.contexte("[S2] (doc#b) " + "mot " * 40 + "criterion: faithfulness " + "x " * 40),
        t.contexte("brut: # pas un commentaire \"q\" 'q'   fin"),
    ]
    ref = [t.reference("ref\n- answer_id: r/q-1\n  criterion: correctness", "doc#r")]
    lignes: list[dict[str, Any]] = [
        {"answer_id": "r/q-1", "criterion": "correctness", "verdict": "", "note": ""},
        {"answer_id": "r/q-1", "criterion": "faithfulness", "verdict": "", "note": ""},
    ]
    lignes[0].update(context_passages=ctx, reference_passages=ref)
    corps = yaml.dump(
        {"annotator": "ana", "passages": t.entrees, "annotations": lignes},
        Dumper=_Dumper,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )
    paquet = tmp_path / "ana.yaml"
    paquet.write_text(ENTETE + corps, encoding="utf-8", newline="\n")
    avant_txt, avant = paquet.read_text(encoding="utf-8"), lire_paquet(paquet)
    v = _json(
        tmp_path / "v.json",
        {
            "r/q-1|correctness": {"verdict": "yes", "note": "a\nb: #c"},
            "r/q-1|faithfulness": {"verdict": "na"},
        },
    )
    importer_verdicts(paquet, v)
    apres = lire_paquet(paquet)
    assert (
        apres["annotations"][0]["context_passages"] == avant["annotations"][0]["context_passages"]
    )
    assert (
        apres["annotations"][0]["reference_passages"]
        == avant["annotations"][0]["reference_passages"]
    )
    assert [(x["verdict"], x["note"]) for x in apres["annotations"]] == [
        ("yes", "a\nb: #c"),
        ("na", ""),
    ]
    a, b = avant_txt.split("\n"), paquet.read_text(encoding="utf-8").split("\n")
    assert len(a) == len(b)
    assert sum(x != y for x, y in zip(a, b, strict=True)) == 3
    assert len(charger_fichier(paquet)) == 2
