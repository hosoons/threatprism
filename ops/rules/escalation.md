# Escalation ladder: when the day is short of the quota

Quota (ops/rules/collection.md): total >= 14 items and the floors Korea >= 4, telecom >= 3, non-Anglo >= 3.
After every `pipeline.py select`, read /tmp/run/stats.json. If `needMore` is true (or the select line says so), climb the ladder.
Never lower a source gate, never invent or pad items, never publish unverified facts. Stop after round C and record the shortfall.

Round A: source upgrade (cheapest, rescues good stories that were only held for lack of a second source)
- /tmp/run/held.json lists held candidates (reason is not a blacklist hit). Spawn ONE agent "collector-upgrade"
  (ops/agents/collector-upgrade.md) -> /tmp/run/cand-upgrade.json. Run select again.

Round B: gap fill (parallel, max 3 agents, only for what is still missing)
- stats.gaps names the missing floor; stats.missingCategories names empty categories; total < 14 means more items of any kind.
  korea gap -> collector-kr · telecom gap or missing TEL/MKT -> collector-telecom-industry · total/VUL/INC/TCH -> collector-threat-global.
- Tell each agent exactly how many items of which kind are missing and that /tmp/run/seen.json and the items already in
  /tmp/run/cand-*.json must be skipped. Output /tmp/run/cand-extra-<agent>.json. Run select again.

Round C: wider window (last attempt)
- Same as round B, but the window is 96 hours (T1 sources 120 hours) whatever the weekday, queries name individual T1 sources
  (KISA 보호나라, 과기정통부, 개인정보위, CISA alerts, vendor PSIRT pages) and use WebSearch mode "extended". Run select again.

Notes
- Windows: Monday and the first working day after a public holiday start from the last working day (96 h; T1 120 h),
  because weekends and holidays produce few news items. Other days: 48 h (T1 72 h).
- Items published today before this run are kept: select merges with data/daily/<today>.json and dedupes against it.
- Held items blocked by the blacklist heuristics (look-alike, risky TLD...) are not rescued here; if a legitimate outlet is
  wrongly blocked, add it to SAFE in ops/sources.yaml (human review) instead.
- Run log: `pipeline.py runlog` writes the gaps and the final counts, so a persistent shortfall is visible in ops/runs/.
