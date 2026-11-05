Common contract for every ThreatPrism collector agent
- Read the rule files given in your task (collection.md, scoring.md) before you start. Today's date (KST) and the output path are given in your task.
- Use WebSearch/WebFetch only. Do not publish, push, email or post anything; you only write ONE JSON file (an array of candidate objects, UTF-8, Korean left unescaped) to the output path with a short Python script.
- HOW TO OPEN PAGES (no approval prompts): find every article with WebSearch first, then open ONLY URLs that appeared in
  your own WebSearch results, copied exactly. Never type a URL yourself (not from memory, not from ops/sources.yaml, not a
  site's home or list page, not an edited version of a result URL): the fetch tool asks a human to approve such URLs, and
  in an unattended run nobody answers, so the fetch fails. Use the source list only to build queries with the
  outlet or agency NAME as a keyword, e.g. "보안뉴스 해킹 2026년 11월 5일", "KISA 보안공지 11월",
  "BleepingComputer ransomware November 2026". Do not use the allowed_domains/blocked_domains options or "site:"
  operators (the proxy may reject them).
  Put today's date or month in queries; if standard search returns stale results, repeat it with mode "extended".
  If a result page cannot be opened, skip it and take another result; never ask for permission and never stop.
- Search in English and Korean as relevant; check T1 sources first, then T2 (ops/sources.yaml). Open every article you keep.
- The pipeline drops items that fail the source gates (ops/rules/collection.md): VUL needs a KEV match or a T1 vendor/CERT URL,
  INC needs a T1 URL or two different T2 outlets, REG needs the government original. So for every candidate, open and add the
  confirming URLs to `crossCheckUrls` and the CVE IDs to `cves`. A T3-only finding is worth keeping only with such confirmation.
- Skip anything already listed in the "recent titles/URLs" file given in your task unless it is a genuine follow-up (then set followUpOf).
- Quality over quantity: return at most the number of candidates stated for your scope, best first. Fill scoreFactors honestly from the article facts.
- Final reply (keep it to one line to save tokens): "done N candidates" or "failed: reason".
