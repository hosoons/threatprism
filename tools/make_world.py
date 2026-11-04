#!/usr/bin/env python3
"""Generate tools/world110.json (country polygons with ISO alpha-2) from npm world-atlas. Needs node, npm, pycountry."""
import json, os, subprocess, tempfile
import pycountry

here = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
subprocess.run("npm init -y >/dev/null && npm i world-atlas@2 topojson-client@3 >/dev/null 2>&1", shell=True, cwd=tmp, check=True)
subprocess.run(["node", "-e", "const t=require('topojson-client'),w=require('world-atlas/countries-110m.json');"
                "require('fs').writeFileSync('g.json',JSON.stringify(t.feature(w,w.objects.countries)))"], cwd=tmp, check=True)
g = json.load(open(os.path.join(tmp, "g.json")))

def r(c):
    if isinstance(c[0], (int, float)): return [round(c[0], 1), round(c[1], 1)]
    return [r(x) for x in c]

out = []
for f in g["features"]:
    try: a2 = pycountry.countries.get(numeric=str(f["id"]).zfill(3)).alpha_2
    except Exception: a2 = None
    out.append({"a2": a2, "n": f["properties"].get("name"), "g": {"type": f["geometry"]["type"], "coordinates": r(f["geometry"]["coordinates"])}})
json.dump(out, open(os.path.join(here, "world110.json"), "w"), separators=(",", ":"))
print("world110.json", len(out))
