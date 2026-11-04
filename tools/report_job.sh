#!/usr/bin/env bash
# usage: bash tools/report_job.sh daily|weekly   (env: SLACK_WEBHOOK, optional REPORT_DATE)
set -euo pipefail
MODE="$1"
D="${REPORT_DATE:-}"
if [ -z "$D" ]; then D=$(TZ=Asia/Seoul date +%F); fi

python3 tools/make_world.py
python3 tools/build_report.py --mode "$MODE" --date "$D" --root . | tee report.json

git config user.name "ThreatPrism Bot"
git config user.email "threatprism-bot@users.noreply.github.com"
git add reports/
if ! git diff --cached --quiet; then
  git commit -m "Report: $MODE $D"
  for i in 1 2 3; do
    git pull --rebase origin main && git push origin HEAD:main && break || sleep 5
  done
fi

REPORT_KIND="$MODE" REPORT_JSON=report.json python3 tools/post_slack.py
