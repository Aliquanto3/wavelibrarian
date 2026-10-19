"""Reporte les verdicts exportés par la page d'annotation dans le paquet YAML.

Édition ligne à ligne : le reste du paquet est conservé tel quel.

Usage :
`uv run python scripts/importer_verdicts.py corpora/minicorpus/annotations/anael.yaml verdicts.json`
"""

import json
import sys

src_yaml, src_json = sys.argv[1], sys.argv[2]
verdicts = json.load(open(src_json, encoding="utf-8"))["verdicts"]
lines = open(src_yaml, encoding="utf-8").read().split("\n")
aid = crit = None
n = 0
for i, line in enumerate(lines):
    if line.startswith("- answer_id: "):
        aid = line[len("- answer_id: ") :].strip()
    elif line.startswith("  criterion: "):
        crit = line[len("  criterion: ") :].strip()
    elif line == "  verdict: ''":
        v = verdicts.get(f"{aid}|{crit}", {}).get("verdict")
        if v in ("yes", "no"):
            lines[i] = f"  verdict: {v}"
            n += 1
    elif line == "  note: ''":
        note = verdicts.get(f"{aid}|{crit}", {}).get("note", "").strip()
        if note:
            lines[i] = "  note: " + json.dumps(note, ensure_ascii=False)
open(src_yaml, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(n, "verdicts reportés")
