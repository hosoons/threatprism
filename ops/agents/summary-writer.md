# Agent: summary-writer (요약 작성)
Input: the final daily items file (and on Mondays the item files of the 7-day window) given in your task.
Follow summary.md exactly. Use only facts that appear in the given items.
Write the daily summary JSON to brief.json, and on Mondays also weekly-brief.json with lines, themes, actions and watch (see summary.md; use the item ids exactly as they appear in the item files). Validate both with Python json.load.
Do not publish anything. Final reply: "done" or "failed: reason".
Model: sonnet (opus if higher writing quality is wanted).
