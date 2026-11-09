#!/usr/bin/env python3
"""ThreatPrism deterministic pipeline (no LLM tokens).

  seen    --repo R --date D --out O        recent titles/URLs (7 days) -> O/seen.json for collectors
  select  --repo R --date D --run O        candidates O/cand-*.json -> O/daily.json, O/manifest.json, O/stats.json, O/held.json
  render  --repo R --date D --run O [--daily-url U] [--weekly-url W] [--test] [--now YYYY-MM-DDTHH:MM]
                                           O/daily.json + O/brief.json -> O/email.html, O/slack.json, O/push.txt, O/delay.json
  runlog  --repo R --date D --run O [--collectors "a|b"] [--status "push=..;email=..;slack=..;pdf=..;errors=a|b"]
                                           prints the run log JSON (ops/runs/prod-<date>.json) incl. 발송 지연 flag
Scoring rules: ops/rules/scoring.md. Selection rules: ops/rules/collection.md. Shortfall handling: ops/rules/escalation.md.
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
MIN_TOTAL = 14
KST = dt.timezone(dt.timedelta(hours=9))
TARGET_HHMM = (10, 0)      # scheduled delivery target (KST)
DELAY_AFTER_HHMM = (10, 30)  # sending later than this is flagged as 발송 지연
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


# ---------- source filter: whitelist (ops/sources.yaml) -> blacklist heuristics -> cross-check / KEV ----------
TWO_LEVEL = {"co.kr", "or.kr", "go.kr", "ac.kr", "re.kr", "ne.kr", "co.uk", "gov.uk", "org.uk", "ac.uk", "com.au", "gov.au",
             "co.jp", "or.jp", "go.jp", "ne.jp", "com.sg", "gov.sg", "co.in", "gov.in", "com.br", "gov.br", "co.za", "com.cn", "gov.cn"}
RISKY_TLD = {"zip", "mov", "xyz", "top", "click", "buzz", "loan", "work", "gq", "tk", "ml", "cf", "ga"}
TIER_BASE = {"T1": 70, "T2": 60, "T3": 20}
TRUST_MIN = 60


def load_sources(repo):
    path = os.path.join(repo, "ops/sources.yaml")
    out = {"T1": set(), "T2": set(), "BLOCK": set(), "SAFE": set(), "unverified": set()}
    try:
        cur = None
        for raw in open(path, encoding="utf-8"):
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            if not line.startswith(" ") and line.endswith(":"):
                cur = line[:-1].strip()
                continue
            if cur in out and line.strip().startswith("- "):
                d = line.strip()[2:].strip().lower()
                out[cur].add(d)
                if "naver: unverified" in raw:
                    out["unverified"].add(d)
    except OSError:
        pass
    return out


def host_of(url):
    m = re.match(r"^(https?)://([^/:?#]+)", (url or "").strip().lower())
    return (m.group(1), m.group(2)) if m else ("", "")


def reg_domain(host):
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in TWO_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def in_list(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def tier_of(url, src):
    _, host = host_of(url)
    if in_list(host, src["T1"]):
        return "T1"
    if in_list(host, src["T2"]):
        return "T2"
    return "T3"


def lev(a, b):
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def blacklist_hit(url, src):
    scheme, host = host_of(url)
    if scheme != "https":
        return "not https"
    if re.fullmatch(r"[0-9.]+", host) or ":" in host:
        return "ip host"
    if "xn--" in host:
        return "punycode host"
    if host.rsplit(".", 1)[-1] in RISKY_TLD:
        return "risky tld"
    if in_list(host, src["BLOCK"]):
        return "blocked domain"
    rd = reg_domain(host)
    if not in_list(host, src["T1"] | src["T2"] | src["SAFE"]):
        for d in src["T1"] | src["T2"]:
            if len(rd) >= 6 and 0 < lev(rd, d) <= 2:
                return f"look-alike of {d}"
    return ""


def load_kev(path):
    d = load(path, {}) or {}
    return {v.get("cveID", "").upper() for v in d.get("vulnerabilities", [])}


CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.I)


def source_check(c, src, kev):
    """Returns (ok, info). info has tier, trust, kevMatch, reason."""
    urls = [c.get("sourceUrl")] + list(c.get("sources") or []) + [c.get("crossCheckUrl")] + list(c.get("crossCheckUrls") or [])
    urls = [u for i, u in enumerate(urls) if u and u not in urls[:i]]
    for u in urls:
        hit = blacklist_hit(u, src)
        if hit:
            return False, {"reason": f"blacklist: {hit} ({u[:60]})"}
    tiers = {}
    for u in urls:
        rd = reg_domain(host_of(u)[1])
        t = tier_of(u, src)
        if rd not in tiers or t < tiers[rd]:
            tiers[rd] = t
    ts = list(tiers.values())
    best = min(ts) if ts else "T3"
    indep = sum(1 for t in ts if t in ("T1", "T2"))
    cves = {x.upper() for x in CVE_RE.findall(" ".join([c.get("title", ""), c.get("summary", "")] + list(c.get("cves") or [])))}
    kev_match = bool(cves & kev)
    trust = TIER_BASE[best] + 15 * min(max(indep - 1, 0), 2) + (20 if kev_match else 0)
    cat = c.get("category")
    reason = ""
    if cat == "INC" and not ("T1" in ts or indep >= 2):
        reason = "INC needs a T1 source or two independent T2 sources"
    elif cat == "VUL" and not (kev_match or "T1" in ts):
        reason = "VUL needs a CISA KEV match or a T1 vendor/CERT source"
    elif cat == "REG" and "T1" not in ts:
        reason = "REG needs the government/regulator original (T1)"
    elif trust < TRUST_MIN:
        reason = f"trust {trust} < {TRUST_MIN}"
    pending = any(reg_domain(host_of(u)[1]) in src["unverified"] for u in urls)
    info = {"tier": best, "trust": trust, "kevMatch": kev_match, "independentSources": indep, "reason": reason, "naverUnverified": pending}
    return (not reason), info


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
    cands, bad, held = [], [], []
    src = load_sources(a.repo)
    kev = load_kev(a.kev) if a.kev else set()
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
            ok, info = source_check(c, src, kev)
            if not ok:
                held.append({"title": str(c.get("title"))[:60], "url": c.get("sourceUrl"), "category": c.get("category"), "country": c.get("country"), "file": os.path.basename(p), "candidate": c, **info})
                continue
            if info["kevMatch"]:
                c.setdefault("scoreFactors", {})["exploit"] = 25
            c["trust"], c["sourceTier"] = info["trust"], info["tier"]
            if info["kevMatch"]:
                c["kev"] = True
            if info["naverUnverified"]:
                c["sourcePending"] = True
            cands.append(grade(c))
    # a story that was held in one file but passed with better sources in another is no longer held
    ok_urls = {norm_url(c.get("sourceUrl")) for c in cands}
    held = [h for h in held if norm_url(h.get("url")) not in ok_urls]
    # dedupe against recent days and within the batch
    seen = recent(a.repo, a.date)
    seen_urls = {norm_url(i.get("sourceUrl")) for i in seen}
    pool = []
    for c in sorted(cands, key=lambda x: -x["score"]):
        if norm_url(c["sourceUrl"]) in seen_urls:  # same page already published (also for follow-ups: a follow-up must have its own URL)
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
            "summary", "tags", "score", "scoreFactors", "nonThreat", "telcoBreach", "followUpOf", "crossCheckUrl",
            "sources", "trust", "sourceTier", "kev", "sourcePending"]
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
        "date": a.date, "candidates": len(cands), "rejected": bad, "held": held, "kevEntries": len(kev), "afterDedupe": len(pool), "added": len(final), "total": len(allitems),
        "byCategory": {k: sum(1 for i in allitems if i["category"] == k) for k in CATS},
        "byRegion": {r: sum(1 for i in allitems if i["region"] == r) for r in REGIONS},
        "floors": floors, "threatIndex": idx, "threatLevel": lab,
        "severity": {s: sum(1 for i in allitems if i["severity"] == s) for s in SEV_RANK},
    }
    need = {"korea>=4": 4, "telecom>=3": 3, "non-anglo>=3": 3}
    stats["gaps"] = [{"floor": k, "have": v, "need": need[k]} for k, v in floors.items() if v < need[k]]
    stats["missingCategories"] = [k for k in CATS if stats["byCategory"][k] == 0]
    stats["minTotal"] = MIN_TOTAL
    stats["needMore"] = bool(len(allitems) < MIN_TOTAL or stats["gaps"])
    dump(stats, os.path.join(run, "stats.json"))
    # held candidates that a source-upgrade round may rescue (missing second source / T1 original)
    dump([h for h in held if not str(h.get("reason", "")).startswith("blacklist")], os.path.join(run, "held.json"))
    print(json.dumps({**{k: stats[k] for k in ("candidates", "afterDedupe", "added", "total", "threatIndex", "threatLevel", "floors", "kevEntries")}, "held": len(held), "needMore": stats["needMore"], "gaps": stats["gaps"]}, ensure_ascii=False))


def newest_weekly(repo):
    files = sorted(glob.glob(os.path.join(repo, "reports/weekly/Weekly_*.pdf")))
    return APP + "reports/weekly/" + os.path.basename(files[-1]) if files else ""


def levels(repo):
    return (load(os.path.join(repo, "ops/levels.json"), {}) or {}).get("levels", {})


def level_line(repo, lab):
    lv = levels(repo).get(lab)
    if not lv:
        return ""
    return f"{lab}({lv['ko']}) = 5단계 중 {lv['step']}단계: {lv['meaning']}"


def delay_info(now=None):
    """KST send time vs. the 10:00 target. Later than 10:30 => delayed (발송 지연)."""
    n = now or dt.datetime.now(KST)
    mins = n.hour * 60 + n.minute
    limit = DELAY_AFTER_HHMM[0] * 60 + DELAY_AFTER_HHMM[1]
    target = TARGET_HHMM[0] * 60 + TARGET_HHMM[1]
    return {"sentAtKst": n.strftime("%Y-%m-%d %H:%M"), "delayed": mins > limit, "lateMinutes": max(0, mins - target),
            "rule": f"기준 {TARGET_HHMM[0]:02d}:{TARGET_HHMM[1]:02d} KST, {DELAY_AFTER_HHMM[0]:02d}:{DELAY_AFTER_HHMM[1]:02d} 초과 시 발송 지연"}


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
    # Monday (weekly report goes out with the daily one): "Daily/Weekly Briefing"; Tue-Fri: "Daily Briefing"
    is_weekly = dt.date.fromisoformat(a.date).weekday() == 0 or bool(a.weekly_url)
    title = "Daily/Weekly Briefing" if is_weekly else "Daily Briefing"
    now = dt.datetime.fromisoformat(a.now).replace(tzinfo=KST) if a.now else None
    dl = delay_info(now)
    dump(dl, os.path.join(run, "delay.json"))
    dtag = "[발송 지연] " if dl["delayed"] else ""
    dnote = (f"발송 지연: {dl['sentAtKst'][-5:]} KST 발송 (기준 {TARGET_HHMM[0]:02d}:{TARGET_HHMM[1]:02d}, {DELAY_AFTER_HHMM[0]:02d}:{DELAY_AFTER_HHMM[1]:02d} 초과)") if dl["delayed"] else ""
    lvl = level_line(a.repo, lab)
    # push text
    head = top[0]["title"] if top else (items[0]["title"] if items else "")
    if len(head) > 40:
        head = head[:40] + "…"
    push = [f"{tag}{dtag}[ThreatPrism {title}] 오늘 {len(items)}건 · 위협지수 {idx} {lab} · 핵심: {head}"]
    push.append("일일 보고서 PDF: " + a.daily_url if a.daily_url else "일일 보고서 PDF: 생성 지연")
    if weekly:
        push.append("주간 보고서 PDF: " + weekly)
    if lvl:
        push.append("※ " + lvl)
    if dnote:
        push.append(dnote)
    push.append(APP)
    open(os.path.join(run, "push.txt"), "w", encoding="utf-8").write("\n".join(push))
    # slack (#briefing)
    sl = [f":threatprism: *{tag}{dtag}ThreatPrism {title} · {a.date}* · 위협지수 {idx} {lab}", ""]
    if dnote:
        sl += [f":warning: {dnote}", ""]
    for l in lines:
        lb, _, tx = str(l).partition(":")
        sl.append(f"*{lb.strip()}* {tx.strip()}" if tx else str(l))
    sl += ["", "*주요 항목 (High/Critical)*"]
    sl += [f"• [{CAT_KO.get(i['category'], i['category'])}·{i['country']}] {i['title']} — {i['source']}" for i in top[:5]]
    sl += ["", f"총 {len(items)}건 · 전체 내용과 출처는 대시보드에서 확인하세요."]
    if lvl:
        sl.append(f"_위협지수 안내: {lvl}_")
    sl.append(APP)
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
    delay_box = (f'<p style="font-size:12px;color:#b45309;background:#fef3c7;border:1px solid #fcd34d;border-radius:6px;padding:6px 10px;margin:4px 0 8px">{e(dnote)}</p>' if dnote else "")
    level_box = (f'<p style="font-size:12px;color:#444;background:#f3f4f6;border-radius:6px;padding:6px 10px;margin:8px 0">위협지수 안내 · {e(lvl)}<br>'
                 f'<span style="color:#888">산식: 상위 5건 점수 평균×0.7 + 최고 점수×0.3. 국가 사이버위기경보 5단계(정상·관심·주의·경계·심각)와 비교해 읽을 수 있게 만든 참고 지표이며 공식 경보가 아닙니다.</span></p>' if lvl else "")
    body = (f'<div style="font-family:Arial,sans-serif;color:#111;max-width:600px">'
            f'<div style="margin-bottom:8px"><b style="font-size:18px">{tag}{dtag}ThreatPrism {title}</b></div>{delay_box}'
            f'<p style="font-size:13px;color:#444;margin:4px 0 10px">{a.date} ({wd}) · 오늘 총 {len(items)}건 수집 · 위협지수 <b>{idx} {lab}</b></p>'
            f'{brief_html}<p style="font-size:14px;margin:14px 0 4px"><b>주요 항목</b></p><ul style="font-size:13px;line-height:1.5;padding-left:18px;margin:4px 0">{lis}</ul>'
            f'<p style="font-size:13px">카테고리: {cats}<br>지역: {regs}</p>{buttons}{level_box}'
            f'<p style="font-size:12px;color:#666">모든 항목은 검증된 공개 출처 기반이며 상세 내용은 앱에서 확인하세요.</p>'
            f'<p style="font-size:11px;color:#888">수신 거부는 앱의 알림 설정 &gt; 이메일 구독 목록에서 가능합니다.</p>{footer}</div>')
    open(os.path.join(run, "email.html"), "w", encoding="utf-8").write(body)
    open(os.path.join(run, "email-subject.txt"), "w", encoding="utf-8").write(f"{tag}{dtag}[ThreatPrism] {title} - {a.date}")
    print(json.dumps({"push_chars": len("\n".join(push)), "email_bytes": len(body.encode()), "slack_chars": len("\n".join(sl)), "threat": [idx, lab]}, ensure_ascii=False))


def cmd_runlog(a):
    """Assemble ops/runs/prod-<date>.json (no secrets, no e-mail addresses) from the run directory."""
    st = load(os.path.join(a.run, "stats.json"), {}) or {}
    dl = load(os.path.join(a.run, "delay.json"), {}) or {}
    kv = dict(x.split("=", 1) for x in a.status.split(";") if "=" in x)
    held = st.get("held", [])
    errs = []
    if st.get("needMore"):
        errs.append(f"수집 기준 미달: total {st.get('total')} < {MIN_TOTAL} 또는 floor 미충족 {st.get('gaps')}")
    if dl.get("delayed"):
        errs.append(f"발송 지연: {dl.get('sentAtKst')} KST 발송 ({dl.get('rule')})")
    log = {"date": a.date, "collectors": [x for x in a.collectors.split("|") if x],
           "stats": {k: st.get(k) for k in ("candidates", "afterDedupe", "added", "total", "threatIndex", "threatLevel", "floors", "kevEntries", "gaps", "missingCategories")},
           "held": len(held), "heldReasons": sorted({str(h.get("reason", ""))[:70] for h in held}),
           "delivery": {"sentAtKst": dl.get("sentAtKst"), "delayed": bool(dl.get("delayed")), "label": "발송 지연" if dl.get("delayed") else "정시", "lateMinutes": dl.get("lateMinutes"), "rule": dl.get("rule")},
           "pdf": kv.get("pdf", ""), "push": kv.get("push", ""), "email": kv.get("email", ""), "slack": kv.get("slack", ""), "errors": errs + [x for x in kv.get("errors", "").split("|") if x]}
    print(json.dumps(log, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seen", "select", "render", "runlog"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--run")
    ap.add_argument("--out")
    ap.add_argument("--daily-url", default="")
    ap.add_argument("--weekly-url", default="")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--now", default="", help="override KST send time for tests, e.g. 2026-11-09T11:05")
    ap.add_argument("--collectors", default="", help="runlog: one-line collector replies separated by |")
    ap.add_argument("--status", default="", help="runlog: push=..;email=..;slack=..;pdf=.. as k=v;k=v")
    ap.add_argument("--kev", default="", help="path to CISA known_exploited_vulnerabilities.json (cisagov/kev-data)")
    a = ap.parse_args()
    if a.cmd == "seen":
        a.out = a.out or a.run
        cmd_seen(a)
    elif a.cmd == "select":
        cmd_select(a)
    elif a.cmd == "runlog":
        cmd_runlog(a)
    else:
        cmd_render(a)


if __name__ == "__main__":
    main()
