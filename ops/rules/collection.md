# Collection rules (relevance first, balance as a floor)

Window: items published in the last 48 hours; up to 72 hours only for tier-1 (primary) sources.

Source filter (3 stages; ops/sources.yaml is the single source of truth, enforced by ops/scripts/pipeline.py)
1. Whitelist — tier by registrable domain of every URL on the item
   - T1 primary: government/CERT/regulators, vendor PSIRT advisories, carrier press rooms -> may stand alone
   - T2 vetted press: Korean press in the Naver news partnership (entries marked "naver: unverified" are provisional
     until the quarterly review), overseas press meeting the NewsGuard 9 criteria, security trade media, vendor research
   - any domain not listed = T3 (blogs, researcher social posts, small sites) -> discovery only
2. Blacklist — any hit discards the item: not https, raw IP host, punycode host, risky TLD, look-alike of a listed domain
   (edit distance 1-2), BLOCK list. Collectors also skip sites with no byline, no ownership/contact page, no corrections
   policy, AI mass-aggregators, and domains that look newly registered. Popularity (traffic rank) is never a trust signal.
   Google Web Risk / PhishTank / VirusTotal lookups are not wired in yet (they need an API key and network allow-listing).
3. Cross-check — category gates
   - VUL: CISA KEV match (cisagov/kev-data, cloned each run) or a T1 vendor/CERT advisory URL
   - INC: a T1 source, or two independent T2 domains; T3-only reports are held
   - REG: the government/regulator original URL (T1) is mandatory
Trust score = tier base (T1 70, T2 60, T3 20) + 15 per additional independent T1/T2 domain (max +30) + 20 for a KEV match.
Items below 60 or failing a gate are not shown; they are listed under `held` in stats.json. A KEV match sets exploit=25.

Verification
- Open every article; `sourceUrl` must be a page you actually opened in this run. Never guess URLs.
- Open only URLs taken from your own WebSearch results (exact copy). Typed or edited URLs trigger an approval prompt that nobody answers in a scheduled run.
- Put every confirming URL you opened in `crossCheckUrls` (vendor advisory, NVD/KEV page, government original, second outlet).
- List the CVE IDs in `cves`.
- Every fact in title/summary must be in the source.

Selection (done by the pipeline script, collectors just deliver good candidates)
- Ranked by score. All critical/high items are always kept.
- Floors: ≥4 Korea items, ≥3 telecom-related items, ≥3 items outside US/UK/CA/AU/NZ/IE, every category at least once when available.
- Total 15-20 items.
- Follow-ups: if a story continues an item from the last 7 days, set `followUpOf` to that item's id and summarise only the new facts.

Candidate JSON fields: title (Korean, ≤60 chars), category (INC VUL REG MKT TCH TEL), country (ISO alpha-2), countryName (Korean), region (Asia, Europe, North America, South America, Africa, Middle East, Oceania), lat, lng, source, sourceUrl, crossCheckUrls (list of confirming URLs you opened), cves (list, optional), date (article date YYYY-MM-DD), summary (Korean, 2-3 sentences), tags (3-5 English, lowercase, hyphenated, reuse common tags such as ransomware, zero-day, supply-chain, telecom, data-breach), scoreFactors {target, exploit, technical, scale, domestic}, nonThreat (bool), telcoBreach (bool), followUpOf (optional id).
