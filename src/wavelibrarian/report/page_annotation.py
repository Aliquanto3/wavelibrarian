"""Page HTML d'annotation, autonome (hors ligne), à l'aveugle (FR-38, story 9.4).

`wl annotations page <paquet.yaml> --vers <page.html>` lit un paquet (nouveau format court ou
ancien format à lignes complètes) et écrit une page sans dépendance externe. Leçons de la
réannotation du 2026-10-26 : aucun verdict de Juge ni verdict déjà saisi dans la page, aucun
surlignage des mots de la Réponse, réponse de référence montrée pour `correctness` et
`completeness` seulement, consigne stricte d'étayage pour `faithfulness`, trois verdicts par
Critère (oui, non, sans objet). La progression est gardée dans le navigateur ; le bouton
d'export télécharge `verdicts-<annotateur>.json`, que `wl annotations importer` reporte dans le
paquet. Les Réponses viennent d'un LLM : tout contenu est échappé côté page, et la charge JSON
est protégée contre la fermeture de `<script>`.
"""

import json
from pathlib import Path
from typing import Any

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.report.paquet import lire_paquet

CLES_REPONSE = ("question", "reference_answer", "answer", "reference_passages", "context_passages")
# Données montrées seulement si l'item a l'un de ces Critères (la charge JSON reste à l'aveugle
# et ne porte pas la réponse attendue d'un item `faithfulness` seul).
REFERENCE = frozenset({"correctness", "completeness"})
CLES_SELON_CRITERE = {
    "reference_answer": REFERENCE,
    "reference_passages": REFERENCE,
    "context_passages": frozenset({"faithfulness"}),
}


def donnees_de_page(paquet: Path) -> dict[str, Any]:
    """`{annotator, items}` : une entrée par Réponse (`id`, `criteria`, données de la Réponse
    prises sur n'importe laquelle de ses lignes), triées par Question puis identifiant. Ni
    verdict ni note : la page est à l'aveugle."""
    doc = lire_paquet(paquet)
    if not isinstance(doc, dict):
        raise ConfigError("paquet", f"{paquet.name} : un mapping est attendu à la racine")
    annotateur = doc.get("annotator")
    lignes = doc.get("annotations")
    if not isinstance(annotateur, str) or not annotateur.strip():
        raise ConfigError("annotator", f"{paquet.name} : annotateur manquant ou vide")
    if not isinstance(lignes, list) or not lignes:
        raise ConfigError("annotations", f"{paquet.name} : une liste non vide est attendue")
    groupes: dict[str, dict[str, Any]] = {}
    for i, ligne in enumerate(lignes):
        if not isinstance(ligne, dict):
            raise ConfigError(f"annotations[{i}]", f"{paquet.name} : un mapping est attendu")
        aid = ligne.get("answer_id")
        critere = ligne.get("criterion")
        if not isinstance(aid, str) or not aid or critere not in LIBELLES:
            raise ConfigError(
                f"annotations[{i}]", f"{paquet.name} : answer_id ou Critère manquant ou inconnu"
            )
        g = groupes.setdefault(aid, {"id": aid, "criteria": []})
        for cle in CLES_REPONSE:
            if ligne.get(cle) and not g.get(cle):
                g[cle] = ligne[cle]
        if critere in g["criteria"]:  # refusé aussi par le chargeur de la story 5.1
            raise ConfigError(f"annotations[{i}]", f"{paquet.name} : doublon {aid} pour {critere}")
        g["criteria"].append(critere)
    for g in groupes.values():
        for cle, criteres in CLES_SELON_CRITERE.items():
            if not criteres.intersection(g["criteria"]):
                g.pop(cle, None)
    items = sorted(groupes.values(), key=lambda g: (g["id"].rsplit("/", 1)[-1], g["id"]))
    return {"annotator": annotateur, "items": items}


def generer_page(paquet: Path, vers: Path) -> int:
    """Écrit la page `vers` ; rend le nombre de Réponses. `ConfigError` si le paquet est invalide."""
    donnees = donnees_de_page(paquet)
    if vers.exists() and vers.samefile(paquet):
        raise ConfigError("vers", f"{vers} est le paquet lui-même : choisir un fichier .html")
    charge = json.dumps(donnees, ensure_ascii=False).replace("<", "\\u003c")
    # U+2028 / U+2029 terminent une ligne en JavaScript ancien : on les échappe aussi.
    charge = charge.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    vers.parent.mkdir(parents=True, exist_ok=True)
    vers.write_text(HTML.replace("__DATA__", charge), encoding="utf-8", newline="\n")
    return len(donnees["items"])


LIBELLES = {
    "correctness": (
        "Exacte ?",
        "Dit-elle la même chose que la réponse attendue ? Une autre formulation compte comme exacte.",
    ),
    "completeness": (
        "Complète ?",
        "Contient-elle tous les éléments de la réponse attendue ? Il en manque un : Non.",
    ),
    "faithfulness": (
        "Étayée par les extraits ?",
        "Tout ce que la Réponse affirme se lit-il dans les extraits reçus par le système ? "
        "On ne juge pas si c'est juste.",
    ),
}

# ruff: noqa: E501 (page HTML embarquée)
HTML = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Annotation des Juges</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--mute:#6b6a66;--line:#e2e0da;--acc:#2f5d8a;--yes:#2e7d4f;--no:#b23b3b;--na:#6b6a66;--soft:#eef2f6}
@media (prefers-color-scheme:dark){:root{--bg:#17181a;--card:#212225;--ink:#ecebe7;--mute:#a19f99;--line:#34353a;--acc:#7fb0e0;--yes:#5cc28a;--no:#e27272;--na:#a19f99;--soft:#2a2d33}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
h1{font-size:20px;margin:0;flex:1}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin:4px 0 16px}.bar>i{display:block;height:100%;background:var(--acc)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:14px}
.lbl{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);margin:0 0 2px}
.q{font-size:18px;font-weight:600;margin:0 0 14px}
.box{background:var(--soft);border-radius:8px;padding:10px 12px;margin-bottom:10px}.box p{margin:0;font-size:17px;white-space:pre-wrap}
.crit{border-top:1px solid var(--line);padding:12px 0 4px}
.crit h3{margin:0;font-size:16px}.crit .help{color:var(--mute);font-size:14px;margin:2px 0 8px}
.strict{background:var(--soft);border-left:4px solid var(--acc);border-radius:6px;padding:8px 12px;font-size:14px;margin:6px 0 10px}.strict li{margin:2px 0}
.btns{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:6px 14px;cursor:pointer}
button.y[aria-pressed=true]{background:var(--yes);color:#fff;border-color:var(--yes)}
button.n[aria-pressed=true]{background:var(--no);color:#fff;border-color:var(--no)}
button.s[aria-pressed=true]{background:var(--na);color:#fff;border-color:var(--na)}
input.note{flex:1;min-width:180px;font:inherit;font-size:14px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
details{margin-top:12px}summary{cursor:pointer;color:var(--acc)}
.ctx{font-size:14px;white-space:pre-wrap;background:var(--soft);border-radius:8px;padding:8px 10px;margin:8px 0}
nav{display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap}
.guide{font-size:14px}.guide li{margin:2px 0}
.done{color:var(--yes);font-weight:600}
</style></head><body><main>
<header><h1>Annotation des Juges</h1><span id="count"></span><button id="exp">Télécharger mes verdicts</button></header>
<div class="bar"><i id="prog"></i></div>
<details class="card guide" id="guide"><summary>Comment annoter (2 min de lecture)</summary>
<p>Le corpus est <b>fictif</b> : personne ne connaît les réponses, et ce n'est pas nécessaire. Chaque verdict est une <b>comparaison de textes</b>. Vous ne voyez aucun verdict de Juge : annotez à l'aveugle.</p>
<ul>
<li><b>Exacte</b> : la Réponse dit-elle la même chose que la réponse attendue ? Une autre formulation compte comme exacte.</li>
<li><b>Complète</b> : contient-elle <i>tous</i> les éléments de la réponse attendue ? Il en manque un : Non.</li>
<li><b>Étayée</b> : seuls les extraits comptent, pas la réponse attendue, et rien n'est surligné. Oui si tout ce que la Réponse affirme se lit dans les extraits. Non si elle affirme quelque chose qu'ils ne disent pas. Une Réponse fidèle à un extrait faux reste fidèle.</li>
<li><b>Sans objet</b> : le Critère ne s'applique pas. Une Réponse qui n'affirme rien (vide, « je ne sais pas ») est sans objet en fidélité.</li>
</ul>
<p>Les Réponses sont triées par Question. Raccourcis : <b>←/→</b> pour naviguer. Votre progression est gardée dans ce navigateur. À la fin, « Télécharger mes verdicts ».</p></details>
<div id="view"></div>
<nav><button id="prev">← Précédente</button><button id="next">Suivante →</button></nav>
</main>
<script>
const DATA=__DATA__;
const KEY="wl-annot-"+DATA.annotator;
const LABELS={correctness:["Exacte ?","Dit-elle la même chose que la réponse attendue ?"],
completeness:["Complète ?","Contient-elle tous les éléments de la réponse attendue ?"],
faithfulness:["Étayée par les extraits ?","Tout ce que la Réponse affirme se lit-il dans les extraits reçus par le système ? On ne juge pas si c'est juste."]};
const STRICT='<ul class="strict"><li>Seuls les extraits ci-dessous comptent ; la réponse attendue n\'entre pas en jeu.</li><li>Une Réponse qui n\'affirme rien (vide, abstention) est <b>sans objet</b>.</li><li>Une Réponse fidèle à un extrait faux reste <b>fidèle</b> : on ne juge pas la vérité.</li><li><b>Non</b> si elle affirme ce qu\'aucun extrait ne dit.</li></ul>';
let st={};try{st=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
let pos=0;try{pos=+localStorage.getItem(KEY+"-pos")||0}catch(e){}
if(!(pos>=0&&pos<DATA.items.length))pos=0;
const total=DATA.items.reduce((s,i)=>s+i.criteria.length,0);
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(st));localStorage.setItem(KEY+"-pos",pos)}catch(e){}};
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const REF=new Set(["correctness","completeness"]);
function render(){
  const it=DATA.items[pos]; const done=Object.values(st).filter(v=>v.verdict).length;
  document.getElementById("count").innerHTML=(done===total?'<span class="done">Terminé ✓ </span>':"")+`Réponse ${pos+1}/${DATA.items.length} · ${done}/${total} verdicts`;
  document.getElementById("prog").style.width=(100*done/total)+"%";
  const qid=it.id.split("/").pop();
  let h=`<div class="card"><p class="lbl">Question ${esc(qid)}</p><p class="q">${esc(it.question)}</p>
  <p class="lbl">Réponse du système</p><div class="box"><p>${esc(it.answer)}</p></div>`;
  const ctx=it.context_passages||[], ref=it.reference_passages||[];
  for(const c of it.criteria){const k=it.id+"|"+c, v=st[k]||{};
    h+=`<div class="crit"><h3>${esc(LABELS[c][0])}</h3><p class="help">${esc(LABELS[c][1])}</p>`;
    if(REF.has(c)){
      h+=`<p class="lbl">Réponse attendue</p><div class="box"><p>${esc(it.reference_answer)}</p></div>`;
      if(ref.length) h+=`<details><summary>D'où vient la réponse attendue</summary>${ref.map(p=>`<div class="ctx">${esc(p)}</div>`).join("")}</details>`;}
    else {h+=STRICT+`<details open><summary>Extraits reçus par le système (${ctx.length})</summary>${ctx.map(p=>`<div class="ctx">${esc(p)}</div>`).join("")||"<p>Aucun extrait.</p>"}</details>`;}
    h+=`<div class="btns" style="margin-top:8px">
    <button class="y" data-k="${esc(k)}" data-v="yes" aria-pressed="${v.verdict==="yes"}">Oui</button>
    <button class="n" data-k="${esc(k)}" data-v="no" aria-pressed="${v.verdict==="no"}">Non</button>
    <button class="s" data-k="${esc(k)}" data-v="na" aria-pressed="${v.verdict==="na"}">Sans objet</button>
    <input class="note" data-k="${esc(k)}" placeholder="Note (facultative)" value="${esc(v.note||"")}"></div></div>`;}
  document.getElementById("view").innerHTML=h+"</div>";
  document.getElementById("prev").disabled=pos===0; document.getElementById("next").disabled=pos===DATA.items.length-1;}
document.addEventListener("click",e=>{const b=e.target.closest("button[data-v]");if(!b)return;
  const k=b.dataset.k; st[k]={...(st[k]||{}),verdict:st[k]?.verdict===b.dataset.v?"":b.dataset.v}; save(); render();});
document.addEventListener("input",e=>{if(!e.target.matches("input.note"))return; const k=e.target.dataset.k; st[k]={...(st[k]||{}),note:e.target.value}; save();});
const go=d=>{pos=Math.max(0,Math.min(DATA.items.length-1,pos+d)); save(); render(); scrollTo(0,0);};
document.getElementById("prev").onclick=()=>go(-1); document.getElementById("next").onclick=()=>go(1);
document.addEventListener("keydown",e=>{if(e.target.matches("input"))return; if(e.key==="ArrowLeft")go(-1); if(e.key==="ArrowRight")go(1);});
document.getElementById("exp").onclick=()=>{const blob=new Blob([JSON.stringify({annotator:DATA.annotator,verdicts:st},null,1)],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="verdicts-"+DATA.annotator+".json"; a.click();};
if(!Object.keys(st).length) document.getElementById("guide").open=true;
render();
</script></body></html>"""
