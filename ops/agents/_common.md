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
- CROSS-CHECK STEP (mandatory before writing the file): for every INC or VUL candidate run ONE more WebSearch for the same
  story (CVE ID, product or victim name) and add from those results a second, different outlet or the vendor/CERT/government
  page to `crossCheckUrls` (open it first). Korean stories: look for the same story in another Korean outlet (연합뉴스, 전자신문,
  데일리시큐, 지디넷코리아, 보안뉴스 etc.) or the KISA/과기정통부/개인정보위 notice. If no second source exists, still deliver
  it; the pipeline will hold it. Because roughly half of single-source items are held, deliver about 50% more candidates than
  your target count, and include TEL/MKT/TCH/REG items, which pass with one T2 source (REG needs the government original).
- Skip anything already listed in the "recent titles/URLs" file given in your task unless it is a genuine follow-up (then set followUpOf).
- Quality over quantity: return at most the number of candidates stated for your scope, best first. Fill scoreFactors honestly from the article facts.
- Final reply (keep it to one line to save tokens): "done N candidates" or "failed: reason".
