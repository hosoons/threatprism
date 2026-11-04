#!/usr/bin/env bash
# usage: bash tools/report_job.sh daily|weekly
#   daily : build the Daily PDF; on Mondays (KST) also build the Weekly PDF
#   weekly: build the Weekly PDF only (manual run)
# env: SLACK_WEBHOOK_DAILY, SLACK_WEBHOOK_WEEKLY, optional REPORT_DATE (YYYY-MM-DD)
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
git add reports/
if ! git diff --cached --quiet; then
  git commit -m "Report: $MODES $D"
  for i in 1 2 3; do
    git pull --rebase origin main && git push origin HEAD:main && break || sleep 5
  done
fi

for m in $MODES; do
  if [ "$m" = "daily" ]; then HOOK="${SLACK_WEBHOOK_DAILY:-}"; else HOOK="${SLACK_WEBHOOK_WEEKLY:-}"; fi
  SLACK_WEBHOOK="$HOOK" REPORT_KIND="$m" REPORT_JSON="report-$m.json" python3 tools/post_slack.py
done
