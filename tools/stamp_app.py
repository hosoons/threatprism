#!/usr/bin/env python3
"""Idempotent app stamp, run by tools/report_job.sh before the PDFs are built.

- writes the version from VERSION into the settings > info label of index.html
- keeps the threat-level legend in the app panel in sync with ops/levels.json (meaning of every level)
Re-running changes nothing when index.html is already up to date.
"""
import json, os, re, sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
idx_path = os.path.join(root, "index.html")
ver = open(os.path.join(root, "VERSION"), encoding="utf-8").read().strip()
cfg = json.load(open(os.path.join(root, "ops/levels.json"), encoding="utf-8"))
html = open(idx_path, encoding="utf-8").read()
orig = html

# 1) version label
html = re.sub(r'ThreatPrism v[0-9][0-9.]*', f'ThreatPrism v{ver}', html, count=1)

# 2) level meanings (JS object, regenerated every run between markers)
info = {k: {"ko": v["ko"], "step": v["step"], "range": v["range"], "meaning": v["meaning"]} for k, v in cfg["levels"].items()}
block = ("/*LEVEL_INFO:begin*/const LEVEL_INFO = " + json.dumps(info, ensure_ascii=False) + ";/*LEVEL_INFO:end*/")
if "/*LEVEL_INFO:begin*/" in html:
    html = re.sub(r'/\*LEVEL_INFO:begin\*/.*?/\*LEVEL_INFO:end\*/', lambda m: block, html, count=1, flags=re.S)
else:
    anchor = "function threatLevel(idx, items) {"
    assert anchor in html, "anchor not found"
    html = html.replace(anchor, block + "\n" + anchor, 1)

# 3) legend lines in the panel
old = "`<div class=\"tp-scale\">SEVERE 80↑ (또는 국내 통신사 직접 침해) · HIGH 65~79 · ELEVATED 50~64 · GUARDED 35~49 · LOW 35 미만</div>`;"
new = ("`<div class=\"tp-scale\">5단계: SEVERE 심각(80↑ 또는 국내 통신사 직접 침해) · HIGH 경계(65~79) · ELEVATED 주의(50~64) · GUARDED 관심(35~49) · LOW 정상(35 미만)</div>` +\n"
       "    `<div class=\"tp-scale\"><b>${esc(t.lv.label)}(${esc((LEVEL_INFO[t.lv.label] || {}).ko || '')})</b> = 5단계 중 ${(LEVEL_INFO[t.lv.label] || {}).step || ''}단계: ${esc((LEVEL_INFO[t.lv.label] || {}).meaning || '')}</div>` +\n"
       "    `<div class=\"tp-scale\">국가 사이버위기경보 5단계(정상·관심·주의·경계·심각)와 비교해 읽을 수 있게 만든 참고 지표이며 공식 경보가 아닙니다.</div>`;")
if old in html:
    html = html.replace(old, new, 1)

# 4) "최근 업데이트" = latest collection date (manifest), not the newest article date
a1 = "const days = await mr.json();"
b1 = "const days = await mr.json(); window.__lastCollect = (days || []).slice().sort().pop() || '';"
if a1 in html and "__lastCollect" not in html:
    html = html.replace(a1, b1, 1)
a2 = "document.getElementById('lastUpdate').textContent = dates.sort().reverse()[0];"
b2 = "document.getElementById('lastUpdate').textContent = window.__lastCollect || dates.sort().reverse()[0];"
if a2 in html:
    html = html.replace(a2, b2, 1)

# 5) severity chips: one fixed width (widest label CRITICAL, monospace) so all chips match
a3 = ".sev-chip { font-size: 10px; padding: 2px 7px; border-radius: 6px; font-weight: 600; font-family: var(--font-mono); text-transform: uppercase; }"
b3 = ".sev-chip { display: inline-block; box-sizing: border-box; width: calc(8ch + 16px); text-align: center; font-size: 10px; padding: 2px 0; border-radius: 6px; font-weight: 600; font-family: var(--font-mono); text-transform: uppercase; }"
if a3 in html:
    html = html.replace(a3, b3, 1)

if html != orig:
    open(idx_path, "w", encoding="utf-8").write(html)
    print("index.html updated for v" + ver)
else:
    print("index.html already up to date (v" + ver + ")")
