# Collection rules (relevance first, balance as a floor)

Window: items published in the last 48 hours; up to 72 hours only for tier-1 (primary) sources.

Source tiers
- Tier 1 (check FIRST, every run): CISA KEV new entries, KISA 보호나라 보안공지, vendor security advisories (Cisco, Fortinet, Ivanti, Palo Alto, Ericsson, Nokia, Samsung, Microsoft, Google, Apple), 과기정통부·개인정보위 보도자료, SKT·KT·LG U+ press rooms, national CERTs/regulators (NCSC, ENISA, FCC, JPCERT, CERT-In, CSA Singapore, ACSC).
- Tier 2: specialist media (The Hacker News, BleepingComputer, SecurityWeek, Dark Reading, Help Net Security, The Record, The Register, Light Reading, Telecompaper; 보안뉴스, 데일리시큐, ZDNet Korea, 전자신문, 아이티데일리) and vendor research (Mandiant, Microsoft TI, CrowdStrike, Unit 42, Check Point, Kaspersky, ESET, Talos).
- Tier 3: general press (Reuters, Bloomberg, AP, BBC, FT, WSJ, NYT, 연합뉴스, 주요 일간지) — mainly for cross-checking.
- Never: anonymous blogs, social media, forums, content farms, unclear press-release wires, AI-generated summaries.

Verification
- Open every article; `sourceUrl` must be a page you actually opened in this run. Never guess URLs.
- Items you would score high/critical need two independent sources or one tier-1 source (put the second URL in `crossCheckUrl`).
- Every fact in title/summary must be in the source.

Selection (done by the pipeline script, collectors just deliver good candidates)
- Ranked by score. All critical/high items are always kept.
- Floors: ≥4 Korea items, ≥3 telecom-related items, ≥3 items outside US/UK/CA/AU/NZ/IE, every category at least once when available.
- Total 15-20 items.
- Follow-ups: if a story continues an item from the last 7 days, set `followUpOf` to that item's id and summarise only the new facts.

Candidate JSON fields: title (Korean, ≤60 chars), category (INC VUL REG MKT TCH TEL), country (ISO alpha-2), countryName (Korean), region (Asia, Europe, North America, South America, Africa, Middle East, Oceania), lat, lng, source, sourceUrl, crossCheckUrl (optional), date (article date YYYY-MM-DD), summary (Korean, 2-3 sentences), tags (3-5 English, lowercase, hyphenated, reuse common tags such as ransomware, zero-day, supply-chain, telecom, data-breach), tier (1-3), scoreFactors {target, exploit, technical, scale, domestic}, nonThreat (bool), telcoBreach (bool), followUpOf (optional id).
