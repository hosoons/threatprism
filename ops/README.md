# ThreatPrism operations: agents and pipeline

```
[09:05 KST weekdays] Claude scheduled task = ORCHESTRATOR (sonnet)   (clock: ops/timeline.json)
  0  clone repo read-only -> /tmp/tp ; pipeline.py seen        (recent 7 days, no tokens)
  1  3 collector agents in parallel (sonnet, isolated context)
       collector-kr · collector-threat-global · collector-telecom-industry
       -> /tmp/run/cand-*.json  (web research + scoreFactors only)
  2  pipeline.py select       (short of quota? ops/rules/escalation.md: A upgrade held, B gap fill, C wider window)
                              source filter (sources.yaml tiers, blacklist, KEV, trust>=60, category gates)
                              -> score -> severity, dedupe, floors, ids  (no tokens)
  3  summary-writer agent     -> brief.json (+ weekly-brief.json on Mondays)
  3b mark collected; 4  wait for 09:35 (hold --until publish), stamp publishedAtKst, push data to GitHub (one commit) -> GitHub Actions builds PDFs, Pages, #daily-report
  5  wait for reports/ready/daily-{date}.json (git pull loop, no tokens)
  6  pipeline.py render       -> push.txt, email.html, slack.json, delay.json  (no tokens)
  6b delivery clock: notifications held until 09:45 KST (pipeline.py hold); render flags 발송 지연 when sent after 10:10 KST (target 09:45-10:00); runlog writes ops/runs/prod-<date>.json with actual step times and timeline deviations
  watchdogs: early 09:20 (no beacon / failed => RETRY) and late 10:08 (not sent/done => RETRY); see ops/runbook/production.md
  7  send: Claude push · one Gmail with BCC to subscribers · Slack #briefing
```

| file | role |
|---|---|
| `ops/timeline.json` | single source of the daily clock (09:05 start, 09:20 early watchdog, 09:35 publish, 09:45 send, 10:08 late watchdog, 10:10 delay limit) |
| `ops/runbook/production.md` | daily run procedure and clock table (reference; the executable steps live in the task prompts) |
| `ops/sources.yaml` | T1/T2 domain whitelist, SAFE (look-alike exemptions), BLOCK list (quarterly review) |
| `ops/rules/collection.md` | source tiers, verification, selection floors, candidate schema |
| `ops/rules/scoring.md` | 5-factor score, severity grades, threat index |
| `ops/rules/escalation.md` | what to do when the day is short of 14 items / floors |
| `ops/levels.json` | threat-level legend (5 steps) used by app, PDFs, push, e-mail, Slack |
| `ops/rules/summary.md` | consulting-style daily/weekly executive summary |
| `ops/agents/*.md` | agent specs read at run time (single source of truth) |
| `.claude/agents/*.md` | same agents as Claude Code subagent definitions (for local runs) |
| `ops/scripts/pipeline.py` | deterministic steps: seen / select / verify / hold / mark / stamp / render / runlog / timeline |
| `VERSION`, `CHANGELOG.md` | app version (shown in the app settings) and rollback reference commits |
| `ops/runs/` | run logs and test-run reports |

Secrets are never stored here: the Slack webhook lives only in the scheduled task prompt and in GitHub Secrets; subscribers live in the Google Sheet.
