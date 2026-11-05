#!/usr/bin/env python3
"""ThreatPrism report builder: daily / weekly PDF from data/daily/*.json (HTML -> PDF via Chromium)."""
import argparse, base64, collections, datetime as dt, html, json, os, sys

SEV = ["critical", "high", "medium", "low", "info"]
SEV_KO = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "info": "Info"}
SEV_COLOR = {"critical": "#d92d20", "high": "#f79009", "medium": "#eab308", "low": "#16a34a", "info": "#2f6fe4"}
CAT = ["INC", "VUL", "REG", "MKT", "TCH", "TEL"]
CAT_KO = {"INC": "사건·사고", "VUL": "취약점·위협", "REG": "규제·컴플라이언스", "MKT": "시장·산업", "TCH": "기술 트렌드", "TEL": "통신사 특화"}
REGIONS = ["Asia", "Europe", "North America", "Middle East", "Oceania", "South America", "Africa"]
REGION_KO = {"Asia": "아시아", "Europe": "유럽", "North America": "북미", "Middle East": "중동", "Oceania": "오세아니아", "South America": "남미", "Africa": "아프리카"}
WD = "월화수목금토일"
e = html.escape

def kst_today():
    return (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(hours=9)).date()

def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def sev_key(i): return SEV.index(i.get("severity")) if i.get("severity") in SEV else 9

def logo_b64(root):
    for n in ("icon-192.png", "logo.png"):
        p = os.path.join(root, n)
        if os.path.exists(p):
            return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()
    return ""

CSS = """
@page { size: A4; margin: 14mm 13mm 16mm 13mm; }
* { box-sizing: border-box; }
body { font-family: 'Noto Sans CJK KR','Noto Sans KR','Noto Sans CJK JP','Malgun Gothic',sans-serif; color:#111827; font-size:9.6pt; line-height:1.5; margin:0; }
.hdr { background:#0f1420; color:#fff; border-radius:10px; padding:14px 18px; display:flex; align-items:center; gap:14px; }
.hdr img { width:46px; height:46px; border-radius:10px; }
.hdr .t { font-size:17pt; font-weight:700; line-height:1.2; }
.hdr .s { font-size:8.5pt; color:#9aa7c7; letter-spacing:1.5px; }
.hdr .d { margin-left:auto; text-align:right; font-size:10pt; color:#cfd8f0; }
h2 { font-size:12pt; margin:16px 0 6px; padding-left:8px; border-left:4px solid #2f6fe4; page-break-after:avoid; }
.box { background:#f3f6fd; border:1px solid #d6e0f7; border-radius:8px; padding:10px 14px; }
.box p { margin:3px 0; }
.kpis { display:flex; gap:8px; margin-top:10px; }
.kpi { flex:1; border:1px solid #e5e7eb; border-radius:8px; padding:8px 10px; text-align:center; }
.kpi b { display:block; font-size:19pt; line-height:1.2; }
.kpi span { font-size:8pt; color:#6b7280; }
table { width:100%; border-collapse:collapse; font-size:8.8pt; }
th { background:#eef2fb; text-align:left; padding:4px 6px; border-bottom:1px solid #cbd5e1; font-weight:600; }
td { padding:4px 6px; border-bottom:1px solid #eef0f4; vertical-align:top; }
tr { page-break-inside:avoid; }
.num { text-align:right; white-space:nowrap; }
.pill { display:inline-block; color:#fff; font-size:7.5pt; font-weight:700; border-radius:9px; padding:0 7px; line-height:1.55; }
.bar { height:9px; border-radius:4px; display:inline-block; vertical-align:middle; }
.card { border:1px solid #e5e7eb; border-left:5px solid #999; border-radius:6px; padding:7px 10px; margin:6px 0; page-break-inside:avoid; }
.card .ct { font-weight:700; font-size:10pt; }
.card .m { color:#6b7280; font-size:8pt; margin:1px 0 3px; }
.card .sm { font-size:9pt; }
.muted { color:#6b7280; font-size:8pt; }
a { color:#1d4ed8; text-decoration:none; word-break:break-all; }
.two { display:flex; gap:12px; page-break-inside:avoid; break-inside:avoid; } .two > div { flex:1; }
.foot { margin-top:14px; font-size:7.5pt; color:#9ca3af; border-top:1px solid #e5e7eb; padding-top:5px; }
.day { background:#f3f4f6; font-weight:700; }
"""

def pill(sev):
    return f'<span class="pill" style="background:{SEV_COLOR.get(sev,"#6b7280")}">{SEV_KO.get(sev,sev)}</span>'

def counts(items, key, order):
    c = collections.Counter(i.get(key) for i in items)
    return [(k, c.get(k, 0)) for k in order] + [(k, v) for k, v in c.items() if k not in order]


SEVRANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
TINT = {"critical": "#f4a6a0", "high": "#f9cf8f", "medium": "#f3e08a", "low": "#a8dcb8", "info": "#a9c4f5"}

def world_map(items):
    here = os.path.dirname(os.path.abspath(__file__))
    world = load(os.path.join(here, "world110.json"), [])
    if not world: return ""
    W, H, LAT0, LAT1 = 1000, 390, 80.0, -48.0
    def px(lon, lat): return (lon + 180) / 360 * W, (LAT0 - lat) / (LAT0 - LAT1) * H
    top, cnt = {}, collections.Counter()
    for i in items:
        c = i.get("country")
        if not c: continue
        cnt[c] += 1
        if c not in top or SEVRANK.get(i.get("severity"), 0) > SEVRANK.get(top[c], 0): top[c] = i.get("severity")
    def ring(r):
        pts = [px(x, y) for x, y in r]
        return "M" + "L".join(f"{a:.0f},{b:.0f}" for a, b in pts) + "Z"
    paths = ""
    for f in world:
        g = f["g"]; polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        d = "".join(ring(r) for poly in polys for r in poly)
        sev = top.get(f.get("a2"))
        fill = TINT[sev] if sev else "#c9d2e0"
        stroke = SEV_COLOR[sev] if sev else "#ffffff"
        sw = 1.2 if sev else 0.4
        paths += f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" fill-rule="evenodd"/>'
    # markers: aggregate by country using mean lat/lng
    pos = collections.defaultdict(list)
    for i in items:
        if i.get("country") and i.get("lat") is not None and i.get("lng") is not None:
            pos[i["country"]].append((i["lng"], i["lat"]))
    marks = ""
    for c, n in cnt.most_common()[::-1]:
        if c not in pos: continue
        lng = sum(p[0] for p in pos[c]) / len(pos[c]); lat = sum(p[1] for p in pos[c]) / len(pos[c])
        x, y = px(lng, lat); r = 7 + min(n, 12) * 1.1
        col = SEV_COLOR[top[c]]
        marks += (f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r+4:.1f}" fill="{col}" opacity="0.18"/>'
                  f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}" fill="{col}" stroke="#fff" stroke-width="1.5"/>'
                  f'<text x="{x:.0f}" y="{y+4:.0f}" font-size="12" font-weight="700" fill="#fff" text-anchor="middle" font-family="Noto Sans CJK KR">{n}</text>')
    leg = "".join(f'<span style="display:inline-block;margin-right:10px"><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:{SEV_COLOR[s]};vertical-align:middle"></span> {SEV_KO[s]}</span>' for s in SEV[:4])
    nctry = len(cnt)
    return (f'<h2>발생 지역 지도</h2><div style="border:1px solid #e5e7eb;border-radius:8px;padding:6px;background:#f4f8ff">'
            f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg">{paths}{marks}</svg>'
            f'<div class="muted" style="padding:2px 6px">{leg} · 원 크기·숫자 = 국가별 건수, 색 = 해당 국가의 최고 심각도 · 발생 {nctry}개국</div></div>')

TXTCOL = {"critical": "#b42318", "high": "#b45309", "medium": "#854d0e", "low": "#166534", "info": "#1d4ed8"}

def country_table(items):
    top, cnt, names = {}, collections.Counter(), {}
    for i in items:
        c = i.get("country")
        if not c: continue
        cnt[c] += 1; names[c] = i.get("countryName") or c
        if c not in top or SEVRANK.get(i.get("severity"), 0) > SEVRANK.get(top[c], 0): top[c] = i.get("severity")
    rows = ""
    for c, n in sorted(cnt.items(), key=lambda x: (-x[1], names[x[0]]))[:10]:
        col = TXTCOL.get(top[c], "#111827")
        rows += f'<tr><td style="color:{col};font-weight:700">{e(names[c])}</td><td class="num" style="color:{col};font-weight:700">{n}</td></tr>'
    return f'<table><tr><th>국가 Top 10</th><th class="num">건수</th></tr>{rows}</table><div class="muted" style="margin-top:2px">색 = 해당 국가의 최고 심각도</div>'

def sev_table(items):
    c = collections.Counter(i.get("severity") for i in items)
    mx = max([c.get(s, 0) for s in SEV] + [1])
    rows = "".join(f'<tr><td>{pill(s)}</td><td class="num">{c.get(s,0)}</td><td><span class="bar" style="width:{int(100*c.get(s,0)/mx)}%;background:{SEV_COLOR[s]}"></span></td></tr>' for s in SEV)
    return f'<table><tr><th style="width:70px">심각도</th><th class="num" style="width:40px">건수</th><th></th></tr>{rows}</table>'

def cat_table(items):
    rows = ""
    c = collections.Counter(i.get("category") for i in items)
    for k in CAT:
        rows += f'<tr><td>{k} {CAT_KO[k]}</td><td class="num">{c.get(k,0)}</td></tr>'
    return f'<table><tr><th>카테고리</th><th class="num">건수</th></tr>{rows}</table>'

def region_table(items):
    c = collections.Counter(i.get("region") for i in items)
    rows = "".join(f'<tr><td>{REGION_KO.get(k,k)}</td><td class="num">{v}</td></tr>' for k, v in sorted(c.items(), key=lambda x: -x[1]))
    return f'<table><tr><th>지역</th><th class="num">건수</th></tr>{rows}</table>'

def cards(items):
    out = ""
    for i in items:
        col = SEV_COLOR.get(i.get("severity"), "#999")
        out += (f'<div class="card" style="border-left-color:{col}"><div class="ct">{pill(i.get("severity"))} {e(i.get("title",""))}</div>'
                f'<div class="m">{e(i.get("category",""))} · {e(i.get("countryName",""))} · {e(i.get("source",""))} · {e(i.get("date",""))}</div>'
                f'<div class="sm">{e(i.get("summary",""))}</div></div>')
    return out or '<p class="muted">해당 항목 없음</p>'

def feed_table(items):
    rows = ""
    for i in sorted(items, key=lambda x: (CAT.index(x["category"]) if x.get("category") in CAT else 9, sev_key(x))):
        rows += (f'<tr><td style="width:34px">{e(i.get("category",""))}</td><td>{e(i.get("title",""))}</td>'
                 f'<td style="width:54px">{e(i.get("countryName",""))}</td><td style="width:52px">{pill(i.get("severity"))}</td>'
                 f'<td style="width:78px">{e(i.get("source",""))}</td></tr>')
    return f'<table><tr><th>구분</th><th>제목</th><th>국가</th><th>심각도</th><th>출처</th></tr>{rows}</table>'

def sources_table(items):
    rows, seen = "", set()
    n = 0
    for i in sorted(items, key=lambda x: x.get("id", "")):
        u = i.get("sourceUrl")
        if not u or u in seen: continue
        seen.add(u); n += 1
        rows += f'<tr><td class="num" style="width:22px">{n}</td><td style="width:92px">{e(i.get("source",""))}</td><td><a href="{e(u)}">{e(u)}</a></td><td style="width:62px">{e(i.get("date",""))}</td></tr>'
    return f'<table><tr><th>#</th><th>출처</th><th>URL</th><th>날짜</th></tr>{rows}</table>'

def wrap(logo, title, sub, right, body, gen):
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{e(title)}</title><style>{CSS}</style></head><body>'
            f'<div class="hdr"><img src="{logo}"><div><div class="t">{e(title)}</div><div class="s">{e(sub)}</div></div><div class="d">{right}</div></div>'
            f'{body}<div class="foot">Generated by ThreatPrism · {e(gen)} · 공개 출처 기반 자동 수집·정리 자료이며 출처 원문 확인 필요 · https://hosoons.github.io/threatprism/</div></body></html>')

def kpis(items, extra=None):
    c = collections.Counter(i.get("severity") for i in items)
    kr = sum(1 for i in items if i.get("country") == "KR")
    tiles = [("총 수집", len(items), "#111827"), ("Critical", c.get("critical", 0), SEV_COLOR["critical"]), ("High", c.get("high", 0), SEV_COLOR["high"]), ("국내(KR)", kr, "#2f6fe4")]
    if extra: tiles += extra
    return '<div class="kpis">' + "".join(f'<div class="kpi"><b style="color:{col}">{v}</b><span>{k}</span></div>' for k, v, col in tiles) + '</div>'

def daily(root, date, gen):
    items = load(os.path.join(root, "data/daily", f"{date}.json"), [])
    if not items: return None
    br = load(os.path.join(root, "data/briefing.json"), {})
    lines = br.get("lines", []) if br.get("date") == date else []
    wd = WD[date_obj(date).weekday()]
    summ = "".join(f"<p>{e(l)}</p>" for l in lines) or "<p>당일 요약문 없음</p>"
    ch = sorted([i for i in items if i.get("severity") in ("critical", "high")], key=lambda x: (sev_key(x), x.get("id", "")))
    body = (f'<h2>Executive Summary</h2><div class="box">{summ}</div>{kpis(items)}'
            f'{world_map(items)}<h2>분포 현황</h2><div class="two"><div>{sev_table(items)}</div><div>{cat_table(items)}</div></div><div class="two" style="margin-top:10px"><div>{region_table(items)}</div><div>{country_table(items)}</div></div>'
            f'<h2>핵심 항목 (Critical · High)</h2>{cards(ch)}'
            f'<h2>전체 항목</h2>{feed_table(items)}'
            f'<h2>참조 출처</h2>{sources_table(items)}')
    return wrap(logo_b64(root), "ThreatPrism 일일 보안 인텔리전스 보고서", "DAILY SECURITY INTELLIGENCE REPORT", f"{date} ({wd})<br>수집 {len(items)}건", body, gen), items

def date_obj(s): return dt.date.fromisoformat(s)


# ---------- weekly correlation section ----------
GENERIC_TAGS = {"korea", "south korea", "kr", "usa", "us", "united states", "china", "japan", "europe", "eu", "uk",
                "india", "global", "asia", "world", "news", "security", "cybersecurity"}

def norm_tags(i):
    return sorted({str(t).strip().lower() for t in (i.get("tags") or []) if str(t).strip()})

def bubble_matrix(items):
    """Category x region bubbles: size = count, colour = highest severity in the cell."""
    regs = [r for r in REGIONS if any(i.get("region") == r for i in items)] or REGIONS[:4]
    cell = collections.defaultdict(list)
    for i in items:
        cell[(i.get("category"), i.get("region"))].append(i)
    mx = max([len(v) for v in cell.values()] or [1])
    cw, rh, lw, th = 74, 38, 120, 26
    W = lw + cw * len(regs) + 52
    H = th + rh * len(CAT) + 8
    out = [f'<svg width="100%" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="font-family:sans-serif">']
    for ci, r in enumerate(regs):
        x = lw + cw * ci + cw / 2
        out.append(f'<text x="{x}" y="16" font-size="10" text-anchor="middle" fill="#374151">{e(REGION_KO.get(r, r))}</text>')
    out.append(f'<text x="{lw + cw * len(regs) + 26}" y="16" font-size="10" text-anchor="middle" fill="#374151" font-weight="700">합계</text>')
    for ri, k in enumerate(CAT):
        y = th + rh * ri + rh / 2
        if ri % 2 == 0:
            out.append(f'<rect x="0" y="{th + rh * ri}" width="{W}" height="{rh}" fill="#f8fafc"/>')
        out.append(f'<text x="4" y="{y + 4}" font-size="10" fill="#111827">{k} {e(CAT_KO[k])}</text>')
        tot = 0
        for ci, r in enumerate(regs):
            v = cell.get((k, r), [])
            tot += len(v)
            if not v:
                continue
            top = max(v, key=lambda i: SEVRANK.get(i.get("severity"), 0)).get("severity")
            rad = 4 + 13 * (len(v) / mx) ** 0.5
            x = lw + cw * ci + cw / 2
            out.append(f'<circle cx="{x}" cy="{y}" r="{rad:.1f}" fill="{SEV_COLOR.get(top, "#6b7280")}" fill-opacity="0.78"/>')
            out.append(f'<text x="{x}" y="{y + 3.5}" font-size="9.5" text-anchor="middle" fill="#ffffff" font-weight="700">{len(v)}</text>')
        out.append(f'<text x="{lw + cw * len(regs) + 26}" y="{y + 4}" font-size="10" text-anchor="middle" fill="#111827" font-weight="700">{tot}</text>')
    out.append('</svg>')
    legend = " ".join(f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{SEV_COLOR[s]};margin:0 3px 0 8px"></span>{SEV_KO[s]}' for s in SEV)
    return "".join(out) + f'<div class="muted" style="margin-top:2px">원 크기 = 건수, 색 = 해당 칸의 최고 심각도 · {legend}</div>'

def tag_heatmap(items, n=10):
    """Lower-triangle co-occurrence of the top tags (number of items carrying both tags)."""
    cnt = collections.Counter(t for i in items for t in norm_tags(i))
    top = [t for t, _ in cnt.most_common(n)]
    if len(top) < 2:
        return '<p class="muted">태그 데이터가 부족합니다.</p>'
    co = collections.Counter()
    for i in items:
        ts = [t for t in norm_tags(i) if t in top]
        for a in range(len(ts)):
            for b in range(a + 1, len(ts)):
                co[(ts[a], ts[b])] += 1
                co[(ts[b], ts[a])] += 1
    mx = max([v for v in co.values()] or [1])
    head = "".join(f'<th style="text-align:center;font-size:7.5pt;padding:3px 2px;writing-mode:vertical-rl;transform:rotate(180deg);height:70px">{e(t)}</th>' for t in top)
    rows = ""
    for a_i, a in enumerate(top):
        cells = ""
        for b_i, b in enumerate(top):
            if b_i > a_i:
                cells += '<td style="border:none"></td>'
            elif a == b:
                cells += f'<td style="text-align:center;background:#e5e7eb;color:#374151;font-size:8pt">{cnt[a]}</td>'
            else:
                v = co.get((a, b), 0)
                alpha = 0 if not v else 0.18 + 0.82 * v / mx
                col = "#ffffff" if alpha > 0.55 else "#1f2937"
                cells += f'<td style="text-align:center;background:rgba(47,111,228,{alpha:.2f});color:{col};font-size:8pt">{v or ""}</td>'
        rows += f'<tr><td style="white-space:nowrap;font-size:8pt">{e(a)} <span class="muted">({cnt[a]})</span></td>{cells}</tr>'
    return (f'<table style="table-layout:fixed"><tr><th style="width:150px">태그 (건수)</th>{head}</tr>{rows}</table>'
            '<div class="muted" style="margin-top:2px">칸 숫자 = 같은 항목에 두 태그가 함께 붙은 횟수 (진할수록 많음), 대각선 = 태그 건수</div>')

def tag_flows(items, k=3):
    """Top connected flows: tags shared by several items (prefer spread over days/countries), de-duplicated."""
    by = collections.defaultdict(list)
    for i in items:
        for t in norm_tags(i):
            if t not in GENERIC_TAGS:
                by[t].append(i)
    def day(i):
        x = (i.get("id") or "").split("-")
        return f"{x[1]}-{x[2][:2]}-{x[2][2:]}" if len(x) >= 3 and len(x[2]) == 4 else i.get("date", "")
    cand = []
    for t, arr in by.items():
        if len(arr) < 2:
            continue
        days = {day(i) for i in arr}; ctry = {i.get("countryName") or i.get("country") for i in arr}
        score = len(arr) * 2 + len(days) + len(ctry) + sum(SEVRANK.get(i.get("severity"), 0) for i in arr) / 4
        cand.append((score, t, arr, days, ctry))
    cand.sort(key=lambda c: -c[0])
    picked = []
    for c in cand:
        ids = {i.get("id") for i in c[2]}
        if any(len(ids & {i.get("id") for i in p[2]}) / len(ids) > 0.6 for p in picked):
            continue
        picked.append(c)
        if len(picked) == k:
            break
    if not picked:
        return '<p class="muted">이번 주에는 2건 이상 공통 태그로 묶인 흐름이 없습니다.</p>'
    rows = ""
    for n, (_, t, arr, days, ctry) in enumerate(picked, 1):
        arr = sorted(arr, key=lambda i: (sev_key(i), i.get("id", "")))
        cats = collections.Counter(i.get("category") for i in arr)
        span = f"{min(days)} ~ {max(days)}" if len(days) > 1 else min(days)
        items_html = "".join(f'<div>· {pill(i.get("severity"))} {e(i.get("title", ""))} <span class="muted">({e(i.get("countryName") or i.get("country") or "")})</span></div>' for i in arr[:4])
        more = f'<div class="muted">외 {len(arr) - 4}건</div>' if len(arr) > 4 else ""
        rows += (f'<tr><td style="width:22px"><b>{n}</b></td><td style="width:150px"><b>#{e(t)}</b><div class="muted">{len(arr)}건 · {e(span)}</div>'
                 f'<div class="muted">{" · ".join(f"{c} {v}" for c, v in cats.most_common())}</div>'
                 f'<div class="muted">{e(", ".join(sorted(x for x in ctry if x))[:60])}</div></td><td>{items_html}{more}</td></tr>')
    return (f'<table><tr><th>#</th><th>공통 태그 · 규모</th><th>묶인 항목</th></tr>{rows}</table>'
            '<div class="muted" style="margin-top:2px">같은 태그를 공유하는 항목 묶음. 건수·지속 일수·국가 수·심각도로 순위를 매기고 많이 겹치는 묶음은 하나만 표시</div>')

def correlation_section(items):
    return (f'<h2>한 주의 연관관계</h2>'
            f'<div style="page-break-inside:avoid"><div style="font-weight:700;margin:4px 0">① 카테고리 × 지역: 어떤 위협이 어디에 몰렸나</div>{bubble_matrix(items)}</div>'
            f'<div style="page-break-inside:avoid;margin-top:10px"><div style="font-weight:700;margin:4px 0">② 태그 동시출현: 무엇과 함께 움직였나</div>{tag_heatmap(items)}</div>'
            f'<div style="margin-top:10px"><div style="font-weight:700;margin:4px 0">③ 이번 주 연결된 흐름 Top 3</div>{tag_flows(items)}</div>')

def weekly(root, end, gen):
    end_d = date_obj(end); start_d = end_d - dt.timedelta(days=6)
    man = load(os.path.join(root, "data/daily/manifest.json"), [])
    dates = sorted(d for d in man if start_d <= date_obj(d) <= end_d)
    items, per = [], {}
    for d in dates:
        arr = load(os.path.join(root, "data/daily", f"{d}.json"), [])
        per[d] = arr; items += arr
    if not items: return None
    cs = collections.Counter(i.get("category") for i in items)
    top_cat = cs.most_common(1)[0]
    cc = collections.Counter(i.get("countryName") for i in items)
    top_c = cc.most_common(3)
    sev = collections.Counter(i.get("severity") for i in items)
    ch = sorted([i for i in items if i.get("severity") in ("critical", "high")], key=lambda x: (sev_key(x), x.get("id", "")), reverse=False)
    kr = [i for i in items if i.get("country") == "KR"]
    summary = [
        f"기간 내 총 {len(items)}건 수집: Critical {sev.get('critical',0)}건 · High {sev.get('high',0)}건 · Medium {sev.get('medium',0)}건",
        f"최다 카테고리: {top_cat[0]} {CAT_KO.get(top_cat[0],'')} {top_cat[1]}건 / 국내(KR) {len(kr)}건",
        "상위 국가: " + ", ".join(f"{n} {v}건" for n, v in top_c),
    ]
    box = "".join(f"<p>· {e(s)}</p>" for s in summary)
    # per-day table
    rows = ""
    for d in dates:
        a = per[d]; c = collections.Counter(i.get("severity") for i in a)
        rows += f'<tr><td>{d} ({WD[date_obj(d).weekday()]})</td><td class="num">{len(a)}</td><td class="num">{c.get("critical",0)}</td><td class="num">{c.get("high",0)}</td><td class="num">{c.get("medium",0)}</td><td class="num">{c.get("low",0)+c.get("info",0)}</td></tr>'
    daytab = f'<table><tr><th>수집일</th><th class="num">건수</th><th class="num">Critical</th><th class="num">High</th><th class="num">Medium</th><th class="num">Low·Info</th></tr>{rows}</table>'
    # category x region
    hdr = "".join(f'<th class="num">{REGION_KO[r]}</th>' for r in REGIONS)
    xr = ""
    for k in CAT:
        c = collections.Counter(i.get("region") for i in items if i.get("category") == k)
        xr += f'<tr><td>{k} {CAT_KO[k]}</td>' + "".join(f'<td class="num">{c.get(r,0)}</td>' for r in REGIONS) + f'<td class="num"><b>{cs.get(k,0)}</b></td></tr>'
    cross = f'<table><tr><th>카테고리</th>{hdr}<th class="num">합계</th></tr>{xr}</table>'
    body = (f'<h2>Executive Summary</h2><div class="box">{box}</div>{kpis(items, [("수집일수", len(dates), "#6b7280")])}'
            f'<h2>일자별 추이</h2>{daytab}'
            f'{world_map(items)}<h2>분포 현황</h2><div class="two"><div>{sev_table(items)}</div><div>{country_table(items)}</div></div>'
            f'{correlation_section(items)}'
            f'<h2>핵심 항목 (Critical · High) {len(ch)}건</h2>{cards(ch)}'
            f'<h2>국내(KR) 동향 {len(kr)}건</h2>{feed_table(kr) if kr else "<p class=muted>해당 항목 없음</p>"}'
            f'<h2>전체 항목 (일자별)</h2>' + "".join(f'<div class="day" style="padding:3px 6px;margin-top:6px">{d} ({WD[date_obj(d).weekday()]}) · {len(per[d])}건</div>{feed_table(per[d])}' for d in reversed(dates)) +
            f'<h2>참조 출처</h2>{sources_table(items)}')
    right = f"{start_d} ~ {end_d}<br>{len(dates)}일 · {len(items)}건"
    return wrap(logo_b64(root), "ThreatPrism 주간 보안 인텔리전스 보고서", "WEEKLY SECURITY INTELLIGENCE REPORT", right, body, gen), items, start_d

def to_pdf(html_text, out):
    from playwright.sync_api import sync_playwright
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".html"
    open(tmp, "w", encoding="utf-8").write(html_text)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("file://" + os.path.abspath(tmp))
        pg.pdf(path=out, format="A4", print_background=True, display_header_footer=True,
               header_template="<span></span>",
               footer_template='<div style="font-size:7px;width:100%;text-align:center;color:#9ca3af"><span class="pageNumber"></span> / <span class="totalPages"></span></div>',
               margin={"top": "14mm", "bottom": "16mm", "left": "13mm", "right": "13mm"})
        b.close()
    os.remove(tmp)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["daily", "weekly"], required=True)
    ap.add_argument("--date", default=str(kst_today()))
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    gen = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M KST")
    if a.mode == "daily":
        r = daily(a.root, a.date, gen)
        if not r: print(json.dumps({"ok": False, "reason": "no data"})); sys.exit(0)
        h, items = r; rel = f"reports/daily/Daily_{a.date}.pdf"
    else:
        r = weekly(a.root, a.date, gen)
        if not r: print(json.dumps({"ok": False, "reason": "no data"})); sys.exit(0)
        h, items, s = r; rel = f"reports/weekly/Weekly_{s}_{a.date}.pdf"
    to_pdf(h, os.path.join(a.root, rel))
    sev = collections.Counter(i.get("severity") for i in items)
    br = load(os.path.join(a.root, "data/briefing.json"), {})
    lines = br.get("lines", []) if (a.mode == "daily" and br.get("date") == a.date) else []
    top = [i.get("title", "") for i in sorted(items, key=lambda x: (sev_key(x), x.get("id", ""))) if i.get("severity") in ("critical", "high")][:5]
    kr = sum(1 for i in items if i.get("country") == "KR")
    print(json.dumps({"ok": True, "mode": a.mode, "date": a.date, "path": rel, "name": os.path.basename(rel), "count": len(items), "critical": sev.get("critical", 0), "high": sev.get("high", 0), "kr": kr, "countries": len({i.get("country") for i in items}), "lines": lines, "top": top, "period": (f"{s} ~ {a.date}" if a.mode == "weekly" else a.date)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
