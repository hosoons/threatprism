#!/usr/bin/env bash
# usage: bash tools/report_job.sh daily|weekly
#   daily : build the Daily PDF; on Mondays (KST) also build the Weekly PDF
#   weekly: build the Weekly PDF only (manual run)
# env: SLACK_WEBHOOK_DAILY, SLACK_WEBHOOK_WEEKLY, optional REPORT_DATE (YYYY-MM-DD)
# Order: build -> commit PDFs -> wait until live on GitHub Pages -> write ready marker -> post to Slack
set -euo pipefail
MODE="$1"
D="${REPORT_DATE:-}"
if [ -z "$D" ]; then D=$(TZ=Asia/Seoul date +%F); fi

# Guard 1: never build or mark "ready" without the day's data file (the first publish push may arrive before it).
# The daily-report workflow also triggers on data/daily/*.json, so the later push builds the report.
INPUT_HASH=$( (cat data/briefing.json "data/daily/$D.json" 2>/dev/null || true) | sha256sum | cut -c1-16)
if [ "$MODE" = "daily" ] && [ ! -s "data/daily/$D.json" ]; then
  echo "data/daily/$D.json missing - skip (the push that adds it will rebuild)"; exit 0
fi
# Guard 2: same inputs already built and marked ready -> skip (avoids duplicate PDF/Slack posts on push triggers; manual runs always build)
if [ "${GITHUB_EVENT_NAME:-}" = "push" ] && [ -f "reports/ready/$MODE-$D.json" ] \
   && grep -q "\"inputHash\": \"$INPUT_HASH\"" "reports/ready/$MODE-$D.json" && grep -q "_url" "reports/ready/$MODE-$D.json"; then
  echo "report for $D already built from identical inputs - skip"; exit 0
fi

MODES="$MODE"
if [ "$MODE" = "daily" ] && [ "$(date -d "$D" +%u)" = "1" ]; then MODES="daily weekly"; fi

python3 tools/make_world.py
for m in $MODES; do
  python3 tools/build_report.py --mode "$m" --date "$D" --root . | tee "report-$m.json"
done

git config user.name "ThreatPrism Bot"
git config user.email "threatprism-bot@users.noreply.github.com"

# stamp app version (VERSION) and threat-level legend (ops/levels.json) into index.html; idempotent
python3 tools/stamp_app.py .
git add index.html
if ! git diff --cached --quiet; then
  git commit -m "App: stamp v$(cat VERSION)"
fi

push_retry() {
  for i in 1 2 3; do
    if git pull --rebase origin main && git push origin HEAD:main; then return 0; fi
    sleep 5
  done
  return 1
}

git add reports/
if ! git diff --cached --quiet; then
  git commit -m "Report: $MODES $D"
fi
push_retry

# wait (max ~7 min) until every PDF is reachable on GitHub Pages
PAGES="https://hosoons.github.io/threatprism"
READY=true
for m in $MODES; do
  P=$(python3 -c "import json;print(json.load(open('report-$m.json')).get('path',''))")
  if [ -z "$P" ]; then continue; fi
  ok=0
  for i in $(seq 1 42); do
    if curl -fsI -o /dev/null "$PAGES/$P"; then ok=1; break; fi
    sleep 10
  done
  if [ "$ok" != "1" ]; then READY=false; fi
done

# ready marker: the Claude briefing task waits for this file before it sends push/email
mkdir -p reports/ready
INPUT_HASH="$INPUT_HASH" READY="$READY" MODES="$MODES" MODE="$MODE" D="$D" python3 - <<'PY'
import json, os, datetime
pages = "https://hosoons.github.io/threatprism/"
blob = "https://github.com/hosoons/threatprism/blob/main/"
ready = os.environ["READY"] == "true"
out = {"date": os.environ["D"], "ready": ready, "inputHash": os.environ.get("INPUT_HASH", ""),
       "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
for m in os.environ["MODES"].split():
    r = json.load(open(f"report-{m}.json", encoding="utf-8"))
    if r.get("ok"):
        out[m + "_url"] = (pages if ready else blob) + r["path"]
# Guard 3: a marker without any report URL means nothing was built - do not write it
if not any(k.endswith("_url") for k in out):
    print("no report built - ready marker not written")
    raise SystemExit(0)
with open(f"reports/ready/{os.environ['MODE']}-{os.environ['D']}.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
PY
git add reports/ready
if ! git diff --cached --quiet; then
  git commit -m "Report ready: $MODE $D"
  push_retry
fi

for m in $MODES; do
  if [ "$m" = "daily" ]; then HOOK="${SLACK_WEBHOOK_DAILY:-}"; else HOOK="${SLACK_WEBHOOK_WEEKLY:-}"; fi
  SLACK_WEBHOOK="$HOOK" REPORT_KIND="$m" REPORT_JSON="report-$m.json" python3 tools/post_slack.py
done
