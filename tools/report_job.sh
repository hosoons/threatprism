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
READY="$READY" MODES="$MODES" MODE="$MODE" D="$D" python3 - <<'PY'
import json, os, datetime
pages = "https://hosoons.github.io/threatprism/"
blob = "https://github.com/hosoons/threatprism/blob/main/"
ready = os.environ["READY"] == "true"
out = {"date": os.environ["D"], "ready": ready,
       "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
for m in os.environ["MODES"].split():
    r = json.load(open(f"report-{m}.json", encoding="utf-8"))
    if r.get("ok"):
        out[m + "_url"] = (pages if ready else blob) + r["path"]
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
