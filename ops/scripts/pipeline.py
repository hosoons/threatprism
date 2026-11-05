#!/usr/bin/env python3
"""ThreatPrism deterministic pipeline (no LLM tokens).

  seen    --repo R --date D --out O        recent titles/URLs (7 days) -> O/seen.json for collectors
  select  --repo R --date D --run O        candidates O/cand-*.json -> O/daily.json, O/manifest.json, O/stats.json
  render  --repo R --date D --run O [--daily-url U] [--weekly-url W] [--test]
                                           O/daily.json + O/brief.json -> O/email.html, O/slack.json, O/push.txt
Scoring rules: ops/rules/scoring.md. Selection rules: ops/rules/collection.md.
"""
import argparse, datetime as dt, glob, html, json, os, re, sys

CATS = ["INC", "VUL", "REG", "MKT", "TCH", "TEL"]
CAT_KO = {"INC": "사건·사고", "VUL": "취약점·위협", "REG": "규제·컴플라이언스", "MKT": "시장·산업", "TCH": "기술 트렌드", "TEL": "통신사 특화"}
REGION_KO = {"Asia": "아시아", "Europe": "유럽", "North America": "북미", "South America": "남미", "Africa": "아프리카", "Middle East": "중동", "Oceania": "오세아니아"}
REGIONS = list(REGION_KO)
FMAX = {"target": 30, "exploit": 25, "technical": 15, "scale": 15, "domestic": 15}
ANGLO = {"US", "GB", "CA", "AU", "NZ", "IE"}
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
APP = "https://hosoons.github.io/threatprism/"
e = html.escape


def load(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def dump(obj, p, compact=False):
    with open(p, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)


def norm_url(u):
    u = (u or "").strip().lower()
    u = re.sub(r"^https?://(www\.)?", "", u)
    u = re.sub(r"[?#].*$", "", u)
    return u.rstrip("/")


def tokens(t):
    return {w for w in re.findall(r"[0-9a-z가-힣]+", (t or "").lower()) if len(w) > 1}


def similar(a, b):
    x, y = tokens(a), tokens(b)
    return bool(x and y) and len(x & y) / len(x | y) >= 0.6


def grade(item):
    f = item.get("scoreFactors") or {}
    f = {k: max(0, min(int(f.get(k, 0) or 0), m)) for k, m in FMAX.items()}
    if item.get("nonThreat"):
        f["target"] = min(f["target"], 10)
    s = sum(f.values())
    sev = "critical" if s >= 75 else "high" if s >= 55 else "medium" if s >= 35 else "low" if s >= 20 else "info"
    if item.get("nonThreat") and sev in ("critical", "high"):
        sev = "medium"
    if item.get("telcoBreach") and item.get("country") == "KR":
        sev = "critical"
    item["scoreFactors"], item["score"], item["severity"] = f, s, sev
    return item


def threat_index(items):
    sc = sorted((i.get("score", 12) for i in items), reverse=True)
    if not sc:
        return 0, "LOW"
    top = sc[:5]
    idx = round(0.7 * sum(top) / len(top) + 0.3 * sc[0])
    telco = any(i.get("telcoBreach") and i.get("country") == "KR" for i in items)
    lab = "SEVERE" if telco or idx >= 80 else "HIGH" if idx >= 65 else "ELEVATED" if idx >= 50 else "GUARDED" if idx >= 35 else "LOW"
    return idx, lab


def recent(repo, date, days=7):
    man = load(os.path.join(repo, "data/daily/manifest.json"), []) or []
    d0 = dt.date.fromisoformat(date)
    out = []
    for d in man:
        try:
            if 0 <= (d0 - dt.date.fromisoformat(d)).days <= days:
                out += load(os.path.join(repo, "data/daily", f"{d}.json"), []) or []
        except ValueError:
            pass
    return out


def cmd_seen(a):
    os.makedirs(a.out, exist_ok=True)
    rows = [{"id": i.get("id"), "title": i.get("title"), "url": i.get("sourceUrl")} for i in recent(a.repo, a.date)]
    dump(rows, os.path.join(a.out, "seen.json"))
    print(f"seen {len(rows)}")


REQ = ["title", "category", "country", "countryName", "region", "source", "sourceUrl", "date", "summary", "tags"]


def cmd_select(a):
    run = a.run
    cands, bad = [], []
    for p in sorted(glob.glob(os.path.join(run, "cand-*.json"))):
        arr = load(p, [])
        if not isinstance(arr, list):
            bad.append(f"{os.path.basename(p)}: not a list")
            continue
        for c in arr:
            miss = [k for k in REQ if not c.get(k)]
            if miss or c.get("category") not in CATS or not str(c.get("sourceUrl", "")).startswith("http"):
                bad.append(f"{os.path.basename(p)}: {str(c.get('title'))[:30]} missing {miss}")
                continue
            c["region"] = c["region"] if c["region"] in REGIONS else "Asia"
            c["tags"] = [str(t).strip().lower().replace(" ", "-") for t in c.get("tags", [])][:5]
            cands.append(grade(c))
    # dedupe against recent days and within the batch
    seen = recent(a.repo, a.date)
    seen_urls = {norm_url(i.get("sourceUrl")) for i in seen}
    pool = []
    for c in sorted(cands, key=lambda x: -x["score"]):
        if norm_url(c["sourceUrl"]) in seen_urls and not c.get("followUpOf"):
            continue
        if any(not c.get("followUpOf") and similar(c["title"], s.get("title")) for s in seen):
            continue
        if any(norm_url(c["sourceUrl"]) == norm_url(p["sourceUrl"]) or similar(c["title"], p["title"]) for p in pool):
            continue
        pool.append(c)
    # selection: all critical/high, then floors, then by score up to 18 (max 20)
    chosen = [c for c in pool if c["severity"] in ("critical", "high")][:20]
    rest = [c for c in pool if c not in chosen]
    ymd = a.date.replace("-", "")
    existing_today = load(os.path.join(a.repo, "data/daily", f"{a.date}.json"), []) or []

    def take(pred, need):
        # floors count items already published today plus the ones chosen now
        have = sum(1 for c in chosen if pred(c)) + sum(1 for c in existing_today if pred({**c, "tags": c.get("tags", []), "scoreFactors": c.get("scoreFactors") or {"target": 0}}))
        for c in list(rest):
            if have >= need or len(chosen) >= 20:
                break
            if pred(c):
                chosen.append(c); rest.remove(c); have += 1
        return have

    floors = {
        "korea>=4": take(lambda c: c["country"] == "KR", 4),
        "telecom>=3": take(lambda c: c["category"] == "TEL" or "telecom" in c["tags"] or c["scoreFactors"]["target"] == 30, 3),
        "non-anglo>=3": take(lambda c: c["country"] not in ANGLO, 3),
    }
    for k in CATS:
        take(lambda c, k=k: c["category"] == k, 1)
    for c in list(rest):
        if len(chosen) + len(existing_today) >= 18 and len(chosen) >= 1:
            break
        chosen.append(c); rest.remove(c)
    # merge with an existing file for today, continue the id sequence
    ymd = a.date.replace("-", "")
    prefix = f"inc-{ymd[:4]}-{ymd[4:]}-"
    existing = load(os.path.join(a.repo, "data/daily", f"{a.date}.json"), []) or []
    start = max([int(i["id"][-3:]) for i in existing if str(i.get("id", "")).startswith(prefix)] or [0])
    keep = ["title", "category", "severity", "country", "countryName", "region", "lat", "lng", "source", "sourceUrl", "date",
            "summary", "tags", "score", "scoreFactors", "nonThreat", "telcoBreach", "followUpOf", "crossCheckUrl"]
    final = []
    for n, c in enumerate(sorted(chosen, key=lambda x: (SEV_RANK[x["severity"]], -x["score"])), start + 1):
        o = {"id": f"{prefix}{n:03d}"}
        o.update({k: c[k] for k in keep if k in c and c[k] not in (None, "", False)})
        final.append(o)
    allitems = sorted(existing + final, key=lambda x: x["id"], reverse=True)
    dump(allitems, os.path.join(run, "daily.json"))
    man = load(os.path.join(a.repo, "data/daily/manifest.json"), []) or []
    man = sorted({*man, a.date}, reverse=True)
    dump(man, os.path.join(run, "manifest.json"), compact=True)
    idx, lab = threat_index(allitems)
    stats = {
        "date": a.date, "candidates": len(cands), "rejected": bad, "afterDedupe": len(pool), "added": len(final), "total": len(allitems),
        "byCategory": {k: sum(1 for i in allitems if i["category"] == k) for k in CATS},
        "byRegion": {r: sum(1 for i in allitems if i["region"] == r) for r in REGIONS},
        "floors": floors, "threatIndex": idx, "threatLevel": lab,
        "severity": {s: sum(1 for i in allitems if i["severity"] == s) for s in SEV_RANK},
    }
    dump(stats, os.path.join(run, "stats.json"))
    print(json.dumps({k: stats[k] for k in ("candidates", "afterDedupe", "added", "total", "threatIndex", "threatLevel", "floors")}, ensure_ascii=False))


def newest_weekly(repo):
    files = sorted(glob.glob(os.path.join(repo, "reports/weekly/Weekly_*.pdf")))
    return APP + "reports/weekly/" + os.path.basename(files[-1]) if files else ""


def cmd_render(a):
    run = a.run
    items = load(os.path.join(run, "daily.json"), None) or load(os.path.join(a.repo, "data/daily", f"{a.date}.json"), []) or []
    brief = load(os.path.join(run, "brief.json"), None) or load(os.path.join(a.repo, "data/briefing.json"), {}) or {}
    lines = brief.get("lines", []) if brief.get("date") == a.date else []
    weekly = a.weekly_url or newest_weekly(a.repo)
    idx, lab = threat_index(items)
    top = sorted([i for i in items if i["severity"] in ("critical", "high")], key=lambda x: (SEV_RANK[x["severity"]], -x.get("score", 0)))
    wd = "월화수목금토일"[dt.date.fromisoformat(a.date).weekday()]
    tag = "[TEST] " if a.test else ""
    # push text
    head = top[0]["title"] if top else (items[0]["title"] if items else "")
    if len(head) > 40:
        head = head[:40] + "…"
    push = [f"{tag}[ThreatPrism Daily Briefing] 오늘 {len(items)}건 · 위협지수 {idx} {lab} · 핵심: {head}"]
    push.append("일일 보고서 PDF: " + a.daily_url if a.daily_url else "일일 보고서 PDF: 생성 지연")
    if weekly:
        push.append("주간 보고서 PDF: " + weekly)
    push.append(APP)
    open(os.path.join(run, "push.txt"), "w", encoding="utf-8").write("\n".join(push))
    # slack (#briefing)
    sl = [f":threatprism: *{tag}ThreatPrism Daily Briefing · {a.date}* · 위협지수 {idx} {lab}", ""]
    for l in lines:
        lb, _, tx = str(l).partition(":")
        sl.append(f"*{lb.strip()}* {tx.strip()}" if tx else str(l))
    sl += ["", "*주요 항목 (High/Critical)*"]
    sl += [f"• [{CAT_KO.get(i['category'], i['category'])}·{i['country']}] {i['title']} — {i['source']}" for i in top[:5]]
    sl += ["", f"총 {len(items)}건 · 전체 내용과 출처는 대시보드에서 확인하세요.", APP]
    dump({"text": "\n".join(sl)}, os.path.join(run, "slack.json"))
    # email html (no images, bgcolor only)
    rows = "".join(
        f'<tr><td valign="top" style="width:76px;padding:3px 0;color:#1e3a8a;font-weight:bold">{e(l.partition(":")[0].strip())}</td>'
        f'<td style="padding:3px 0">{e(l.partition(":")[2].strip() or l)}</td></tr>' for l in map(str, lines))
    brief_html = (f'<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f3f6fd" style="border:1px solid #d6e0f7;border-radius:8px">'
                  f'<tr><td style="padding:10px 12px"><table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;line-height:1.5">{rows}</table></td></tr></table>') if rows else ""
    lis = "".join(f'<li><b>{e(i["title"])}</b> ({CAT_KO.get(i["category"])} · {e(i.get("countryName", ""))} · {i["severity"]} · 점수 {i.get("score", "-")})</li>' for i in top[:3])
    cats = " · ".join(f"{CAT_KO[k]} {sum(1 for i in items if i['category'] == k)}" for k in CATS)
    regs = " · ".join(f"{REGION_KO[r]} {n}" for r in REGIONS if (n := sum(1 for i in items if i['region'] == r)))
    btn = lambda url, label, mt: (f'<table cellpadding="0" cellspacing="0" style="margin:{mt}px 0 4px"><tr><td bgcolor="#1d6fd6" style="border-radius:8px;padding:9px 16px">'
                                  f'<a href="{e(url)}" style="color:#ffffff;font-weight:bold;font-size:13px;text-decoration:none;white-space:nowrap">&#128196; {label}</a></td></tr></table>')
    buttons = (btn(a.daily_url, "일일 보고서 PDF 열기", 12) if a.daily_url else
               '<p style="font-size:12px;color:#888">일일 보고서 PDF는 생성이 지연되어 Slack #daily-report 채널에 게시되면 확인할 수 있습니다.</p>')
    if weekly:
        buttons += btn(weekly, "주간 보고서 PDF 열기", 6)
    footer = ('<a href="https://hosoons.github.io/threatprism/" style="text-decoration:none;color:inherit"><table width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;margin:16px 0"><tr><td bgcolor="#0f1420" style="border:1px solid #2a3550;border-radius:12px;padding:16px"><table width="100%" cellpadding="0" cellspacing="0"><tr><td valign="middle" style="font-family:Arial,sans-serif"><a href="https://hosoons.github.io/threatprism/" style="text-decoration:none"><div style="font-size:22px;font-weight:bold;color:#ffffff">ThreatPrism</div><div style="font-size:11px;letter-spacing:2px;color:#8a94ad">SECURITY INTELLIGENCE</div></a></td><td align="right" valign="top"><table cellpadding="0" cellspacing="0"><tr><td bgcolor="#1d6fd6" style="border-radius:8px;padding:8px 14px"><a href="https://hosoons.github.io/threatprism/" style="color:#ffffff;font-weight:bold;font-size:13px;text-decoration:none;white-space:nowrap">앱 열기</a></td></tr></table></td></tr><tr><td colspan="2" style="padding-top:10px;font-size:13px"><a href="https://hosoons.github.io/threatprism/" style="color:#8ab4f8">https://hosoons.github.io/threatprism/</a></td></tr></table></td></tr></table></a>')
    body = (f'<div style="font-family:Arial,sans-serif;color:#111;max-width:600px">'
            f'<div style="margin-bottom:8px"><b style="font-size:18px">{tag}ThreatPrism Daily Briefing</b></div>'
            f'<p style="font-size:13px;color:#444;margin:4px 0 10px">{a.date} ({wd}) · 오늘 총 {len(items)}건 수집 · 위협지수 <b>{idx} {lab}</b></p>'
            f'{brief_html}<p style="font-size:14px;margin:14px 0 4px"><b>주요 항목</b></p><ul style="font-size:13px;line-height:1.5;padding-left:18px;margin:4px 0">{lis}</ul>'
            f'<p style="font-size:13px">카테고리: {cats}<br>지역: {regs}</p>{buttons}'
            f'<p style="font-size:12px;color:#666">모든 항목은 검증된 공개 출처 기반이며 상세 내용은 앱에서 확인하세요.</p>'
            f'<p style="font-size:11px;color:#888">수신 거부는 앱의 알림 설정 &gt; 이메일 구독 목록에서 가능합니다.</p>{footer}</div>')
    open(os.path.join(run, "email.html"), "w", encoding="utf-8").write(body)
    open(os.path.join(run, "email-subject.txt"), "w", encoding="utf-8").write(f"{tag}[ThreatPrism] Daily Briefing - {a.date}")
    print(json.dumps({"push_chars": len("\n".join(push)), "email_bytes": len(body.encode()), "slack_chars": len("\n".join(sl)), "threat": [idx, lab]}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seen", "select", "render"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--run")
    ap.add_argument("--out")
    ap.add_argument("--daily-url", default="")
    ap.add_argument("--weekly-url", default="")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if a.cmd == "seen":
        a.out = a.out or a.run
        cmd_seen(a)
    elif a.cmd == "select":
        cmd_select(a)
    else:
        cmd_render(a)


if __name__ == "__main__":
    main()
