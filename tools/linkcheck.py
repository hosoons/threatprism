#!/usr/bin/env python3
"""URL 생존·평판 점검 (GitHub Actions 러너에서 실행; 샌드박스는 외부망이 막혀 있음).
flag only: 결과는 data/linkcheck/<date>.json 에 기록, 게시를 막지 않음.
검사: HTTP 상태, 최종 도메인(리다이렉트 이탈), TLS 오류, 소프트404 제목, 도메인 등록 나이(RDAP, 키 불필요),
선택: Google Safe Browsing (환경변수 GSB_API_KEY 있을 때만).
"""
import json, os, re, ssl, sys, time, urllib.request, urllib.error, urllib.parse, concurrent.futures as cf
from datetime import datetime, timezone

UA = "Mozilla/5.0 (compatible; ThreatPrismLinkCheck/1.0; +https://hosoons.github.io/threatprism/)"
SECOND_LEVEL = {"co.kr", "or.kr", "go.kr", "ne.kr", "ac.kr", "co.uk", "org.uk", "com.au", "co.jp", "com.cn"}
SOFT404 = re.compile(r"(404|not found|page not found|페이지를 찾을 수 없|존재하지 않)", re.I)
RDAP = os.environ.get("RDAP_BASE", "https://rdap.org/domain/")
NEW_DOMAIN_DAYS = 90

def reg_domain(host):
    parts = host.lower().strip(".").split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host

def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = r.read(40000).decode("utf-8", "ignore")
            return {"status": r.status, "final": r.geturl(), "body": body}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "final": e.geturl() or url, "body": ""}
    except ssl.SSLError as e:
        return {"status": 0, "final": url, "error": "tls:" + str(e)[:80], "body": ""}
    except Exception as e:
        msg = str(e)
        return {"status": 0, "final": url, "error": ("tls:" if "CERTIFICATE" in msg.upper() else "net:") + msg[:80], "body": ""}

def domain_age_days(domain, timeout=15):
    try:
        req = urllib.request.Request(RDAP + domain, headers={"User-Agent": UA, "Accept": "application/rdap+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        for ev in data.get("events", []):
            if ev.get("eventAction") == "registration":
                d = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                return (datetime.now(timezone.utc) - d).days
    except Exception:
        pass
    return None

def safe_browsing(urls):
    key = os.environ.get("GSB_API_KEY")
    if not key or not urls:
        return {}
    body = json.dumps({"client": {"clientId": "threatprism", "clientVersion": "1.0"},
        "threatInfo": {"threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
        "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"],
        "threatEntries": [{"url": u} for u in urls]}}).encode()
    try:
        req = urllib.request.Request("https://safebrowsing.googleapis.com/v4/threatMatches:find?key=" + key,
                                     data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            m = json.load(r).get("matches", [])
        return {x["threat"]["url"]: x["threatType"] for x in m}
    except Exception:
        return {}

def check_url(url):
    t0 = time.time()
    r = fetch(url)
    host_in = urllib.parse.urlparse(url).hostname or ""
    host_out = urllib.parse.urlparse(r["final"]).hostname or ""
    flags = []
    if r["status"] == 0: flags.append(r.get("error", "net:unknown").split(":")[0] + "-error")
    elif r["status"] >= 400: flags.append("http-%d" % r["status"])
    if r["status"] and reg_domain(host_in) != reg_domain(host_out): flags.append("redirect-offdomain")
    m = re.search(r"<title[^>]*>(.*?)</title>", r.get("body", ""), re.I | re.S)
    title = re.sub(r"\s+", " ", m.group(1)).strip()[:100] if m else ""
    if r["status"] == 200 and title and SOFT404.search(title) and len(r.get("body", "")) < 30000: flags.append("soft-404?")
    return {"url": url, "status": r["status"], "finalHost": host_out, "title": title, "flags": flags,
            "ms": int((time.time() - t0) * 1000), "_domain": reg_domain(host_out or host_in)}

def collect_urls(items):
    out = []
    for it in items:
        us = [it.get("sourceUrl")] + list(it.get("crossCheckUrls") or [])
        for u in us:
            if u and u.startswith("http") and u not in [x[0] for x in out]:
                out.append((u, it["id"]))
    return out

def run(daily_path, out_path):
    items = json.load(open(daily_path))
    pairs = collect_urls(items)
    with cf.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda p: check_url(p[0]), pairs))
    for (u, iid), res in zip(pairs, results): res["id"] = iid
    ages = {}
    for d in sorted({r["_domain"] for r in results}):
        ages[d] = domain_age_days(d)
    gsb = safe_browsing([r["url"] for r in results])
    for r in results:
        age = ages.get(r["_domain"]); r["domainAgeDays"] = age
        if age is not None and age < NEW_DOMAIN_DAYS: r["flags"].append("new-domain<%dd" % NEW_DOMAIN_DAYS)
        if r["url"] in gsb: r["flags"].append("safebrowsing:" + gsb[r["url"]])
        del r["_domain"]
    bad = [r for r in results if r["flags"]]
    summary = {"checked": len(results), "flagged": len(bad), "dead": sum(1 for r in results if r["status"] == 0 or r["status"] >= 400),
               "safeBrowsing": "on" if os.environ.get("GSB_API_KEY") else "off"}
    doc = {"date": os.path.basename(daily_path)[:10], "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "summary": summary, "results": results}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(doc, open(out_path, "w"), ensure_ascii=False, indent=1)
    return doc

if __name__ == "__main__":
    daily, out = sys.argv[1], sys.argv[2]
    d = run(daily, out); print(json.dumps(d["summary"], ensure_ascii=False))
