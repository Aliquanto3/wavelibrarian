"""Génère une page HTML d'annotation lisible (autonome, hors ligne) à partir d'un paquet YAML.

Usage :
`uv run python scripts/page_annotation.py corpora/minicorpus/annotations/anael.yaml page.html`

La page garde la progression dans le navigateur et exporte `verdicts-<annotateur>.json`,
à reporter dans le paquet avec `scripts/importer_verdicts.py`.
"""

# ruff: noqa: E501 (page HTML embarquée)
import json
import sys

import yaml

src, out = sys.argv[1], sys.argv[2]
data = yaml.safe_load(open(src, encoding="utf-8"))
groups: dict[str, dict] = {}
for r in data["annotations"]:
    g = groups.setdefault(r["answer_id"], {"id": r["answer_id"], "criteria": []})
    for k in ("question", "reference_answer", "answer", "reference_passages", "context_passages"):
        if r.get(k) and not g.get(k):
            g[k] = r[k]
    g["criteria"].append(r["criterion"])
items = sorted(groups.values(), key=lambda g: (g["id"].rsplit("/", 1)[1], g["id"]))
payload = json.dumps({"annotator": data["annotator"], "items": items}, ensure_ascii=False)
payload = payload.replace("</", "<\\/")

HTML = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Annotation des Juges</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--mute:#6b6a66;--line:#e2e0da;--acc:#2f5d8a;--yes:#2e7d4f;--no:#b23b3b;--mark:#ffe58a;--soft:#eef2f6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#17181a;--card:#212225;--ink:#ecebe7;--mute:#a19f99;--line:#34353a;--acc:#7fb0e0;--yes:#5cc28a;--no:#e27272;--mark:#6b5a12;--soft:#2a2d33}}
:root[data-theme="dark"]{--bg:#17181a;--card:#212225;--ink:#ecebe7;--mute:#a19f99;--line:#34353a;--acc:#7fb0e0;--yes:#5cc28a;--no:#e27272;--mark:#6b5a12;--soft:#2a2d33}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
h1{font-size:20px;margin:0;flex:1}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin:4px 0 16px}.bar>i{display:block;height:100%;background:var(--acc)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:14px}
.lbl{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);margin:0 0 2px}
.q{font-size:18px;font-weight:600;margin:0 0 14px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:600px){.pair{grid-template-columns:1fr}}
.box{background:var(--soft);border-radius:8px;padding:10px 12px}.box p{margin:0;font-size:17px}
.crit{border-top:1px solid var(--line);padding:12px 0 4px}
.crit h3{margin:0;font-size:16px}.crit .help{color:var(--mute);font-size:14px;margin:2px 0 8px}
.btns{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:6px 14px;cursor:pointer}
button.y[aria-pressed=true]{background:var(--yes);color:#fff;border-color:var(--yes)}
button.n[aria-pressed=true]{background:var(--no);color:#fff;border-color:var(--no)}
input.note{flex:1;min-width:180px;font:inherit;font-size:14px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
details{margin-top:12px}summary{cursor:pointer;color:var(--acc)}
.ctx{font-size:14px;white-space:pre-wrap;background:var(--soft);border-radius:8px;padding:8px 10px;margin:8px 0}
mark{background:var(--mark);color:inherit}
nav{display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap}
.guide{font-size:14px}.guide li{margin:2px 0}
.done{color:var(--yes);font-weight:600}
</style></head><body><main>
<header><h1>Annotation des Juges</h1><span id="count"></span><button id="exp">Télécharger mes verdicts</button></header>
<div class="bar"><i id="prog"></i></div>
<details class="card guide" id="guide"><summary>Comment annoter (2 min de lecture)</summary>
<p>Le corpus est <b>fictif</b> (l'archipel de Vaelmor) : personne ne connaît les réponses, et ce n'est pas nécessaire. Chaque verdict est une <b>comparaison de textes</b> :</p>
<ul>
<li><b>Exacte</b> : la réponse du système dit-elle la même chose que la réponse attendue ? Une autre formulation compte comme exacte.</li>
<li><b>Complète</b> : contient-elle <i>tous</i> les éléments de la réponse attendue ? Il en manque un : Non.</li>
<li><b>Fidèle aux extraits</b> : tout ce qu'elle affirme se lit-il dans les extraits que le système a reçus (déroulez-les, les mots de la réponse y sont surlignés) ? On ne juge pas si c'est juste, seulement si rien n'est inventé.</li>
<li>Réponse « je ne sais pas » : Exacte Non, Complète Non, Fidèle Oui (elle n'affirme rien).</li>
</ul>
<p>Les Réponses sont triées par Question : la même Question revient pour plusieurs systèmes. Raccourcis : <b>←/→</b> pour naviguer. Votre progression est gardée dans ce navigateur. À la fin, « Télécharger mes verdicts » et prévenez Claude.</p></details>
<div id="view"></div>
<nav><button id="prev">← Précédente</button><button id="next">Suivante →</button></nav>
</main>
<script>
const DATA=__DATA__;
const KEY="wl-annot-"+DATA.annotator;
const LABELS={correctness:["Exacte ?","Dit-elle la même chose que la réponse attendue ?"],
completeness:["Complète ?","Contient-elle tous les éléments de la réponse attendue ?"],
faithfulness:["Fidèle aux extraits ?","Tout ce qu'elle affirme se lit-il dans les extraits reçus par le système (ci-dessous) ? On ne juge pas si c'est juste."]};
let st={};try{st=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
let pos=0;try{pos=+localStorage.getItem(KEY+"-pos")||0}catch(e){}
const total=DATA.items.reduce((s,i)=>s+i.criteria.length,0);
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(st));localStorage.setItem(KEY+"-pos",pos)}catch(e){}};
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const norm=s=>s.normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase();
function hl(text,answer){
  const words=[...new Set(norm(answer).match(/[a-z0-9]{4,}/g)||[])];
  let t=esc(text); if(!words.length) return t;
  const n=norm(t); let out="",i=0; const re=new RegExp("\\b("+words.join("|")+")","g"); let m;
  while((m=re.exec(n))){ // norm() garde les longueurs pour le latin courant
    let j=m.index; while(j<n.length&&/[a-z0-9]/.test(n[j]))j++;
    out+=t.slice(i,m.index)+"<mark>"+t.slice(m.index,j)+"</mark>"; i=j; re.lastIndex=j;}
  return out+t.slice(i);}
function render(){
  const it=DATA.items[pos]; const done=Object.values(st).filter(v=>v.verdict).length;
  document.getElementById("count").innerHTML=(done===total?'<span class="done">Terminé ✓ </span>':"")+`Réponse ${pos+1}/${DATA.items.length} · ${done}/${total} verdicts`;
  document.getElementById("prog").style.width=(100*done/total)+"%";
  const qid=it.id.split("/").pop();
  let h=`<div class="card"><p class="lbl">Question ${esc(qid)}</p><p class="q">${esc(it.question)}</p>
  <div class="pair"><div><p class="lbl">Réponse attendue</p><div class="box"><p>${esc(it.reference_answer)}</p></div></div>
  <div><p class="lbl">Réponse du système</p><div class="box"><p>${esc(it.answer)}</p></div></div></div>`;
  for(const c of it.criteria){const k=it.id+"|"+c, v=st[k]||{};
    h+=`<div class="crit"><h3>${LABELS[c][0]}</h3><p class="help">${LABELS[c][1]}</p><div class="btns">
    <button class="y" data-k="${esc(k)}" data-v="yes" aria-pressed="${v.verdict==="yes"}">Oui</button>
    <button class="n" data-k="${esc(k)}" data-v="no" aria-pressed="${v.verdict==="no"}">Non</button>
    <input class="note" data-k="${esc(k)}" placeholder="Note (facultative)" value="${esc(v.note||"")}"></div></div>`;}
  const ctx=it.context_passages||[];
  h+=`<details ${it.criteria.includes("faithfulness")?"open":""}><summary>Extraits reçus par le système (${ctx.length})</summary>${ctx.map(p=>`<div class="ctx">${hl(p,it.answer||"")}</div>`).join("")||"<p>Aucun extrait.</p>"}</details>`;
  const ref=it.reference_passages||[];
  if(ref.length) h+=`<details><summary>D'où vient la réponse attendue</summary>${ref.map(p=>`<div class="ctx">${esc(p)}</div>`).join("")}</details>`;
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
open(out, "w", encoding="utf-8").write(HTML.replace("__DATA__", payload))
print(out, len(items), "réponses")
