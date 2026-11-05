# Scoring rubric (item score 0-100)

Every candidate carries `scoreFactors`; the pipeline script computes `score` and `severity`. Collectors only fill the factors.

| factor | max | values |
|---|---|---|
| target (영향 대상) | 30 | 30 telecom operator or critical infrastructure directly affected · 20 large Korean organisation · 10 ordinary company/public body abroad · 5 individuals/indirect |
| exploit (악용 상태) | 25 | 25 exploitation confirmed (CISA KEV, vendor/CERT confirmation, active campaign) · 15 public PoC · 5 exploitation possible only · 0 not applicable |
| technical (기술적 심각도) | 15 | CVSS ≥9.0 → 15 · 7.0-8.9 → 10 · 4.0-6.9 → 5 · for non-CVE incidents: service outage or mass data theft → 10-15, otherwise 5 |
| scale (피해 규모) | 15 | 15 ≥1M people / multiple countries / large outage · 8 medium · 3 small |
| domestic (국내 관련성) | 15 | 15 happened in Korea or product widely used in Korea · 8 Asia neighbour · 3 other |

Rules
- `nonThreat: true` for policy, market, technology or product-launch news: target is at most 10 and severity is capped at medium.
- `telcoBreach: true` only when a Korean telecom operator itself was breached; such an item is always critical.
- Grades: critical ≥75 · high 55-74 · medium 35-54 · low 20-34 · info <20.
- Threat index of a set = 0.7 × mean(top 5 scores) + 0.3 × max score. Levels: SEVERE ≥80 (or a Korean telecom breach) · HIGH 65-79 · ELEVATED 50-64 · GUARDED 35-49 · LOW <35.
