#!/usr/bin/env python3
"""Post a report summary to Slack via incoming webhook. env: SLACK_WEBHOOK, REPORT_JSON(path), optional REPORT_URL"""
import json, os, sys, time, urllib.request

def main():
    hook = os.environ.get("SLACK_WEBHOOK", "")
    if not hook:
        print("SLACK_WEBHOOK is empty (secret not set)"); sys.exit(1)
    r = json.load(open(os.environ["REPORT_JSON"], encoding="utf-8"))
    url = os.environ.get("REPORT_URL", "")
    if r.get("ok") and not url:
        pages = "https://hosoons.github.io/threatprism/" + r["path"]
        url = "https://github.com/hosoons/threatprism/blob/main/" + r["path"]  # fallback
        for _ in range(30):  # wait up to ~5 min for GitHub Pages
            try:
                if urllib.request.urlopen(pages, timeout=15).status == 200:
                    url = pages; break
            except Exception:
                pass
            time.sleep(10)
    if not r.get("ok"):
        text = f":information_source: ThreatPrism {os.environ.get('REPORT_KIND','')} 보고서: 수집 데이터가 없어 생성하지 못했습니다."
    else:
        kind = "일일" if r["mode"] == "daily" else "주간"
        head = f":bar_chart: *ThreatPrism {kind} 보안 인텔리전스 보고서* · {r['period']}"
        stat = f"총 {r['count']}건 · Critical {r['critical']} · High {r['high']} · 국내(KR) {r['kr']} · {r['countries']}개국"
        parts = [head, stat]
        if r.get("lines"):
            parts += ["", *[f"• {l}" for l in r["lines"]]]
        if r.get("top"):
            parts += ["", "*핵심 항목*", *[f"• {t}" for t in r["top"]]]
        parts += ["", f":page_facing_up: <{url}|{r['name']} 열기>"]
        text = "\n".join(parts)
    req = urllib.request.Request(hook, data=json.dumps({"text": text}).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
    if resp.status != 200 or body.strip() != "ok":
        print("Slack error", resp.status, body[:100]); sys.exit(1)
    print("Slack post ok")

if __name__ == "__main__":
    main()
