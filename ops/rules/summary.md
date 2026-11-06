# Executive summary rules (McKinsey/BCG style)

Audience: telecom security C-level. Pyramid principle (conclusion first), MECE evidence, data-backed, then so-what and actions.
Korean 개조식 (noun endings such as ~확산, ~확인, ~필요, ~추진; never ~습니다/~이다). Each line "라벨: 내용", about 50-95 Korean characters.

Daily (5-7 lines, this order): 핵심 (governing message of the day) → 2-4 evidence lines chosen MECE from 위협 / 취약점 / 국내·산업 / 규제·정책 → 시사점 (so-what for a telecom security centre) → 권고 (priority actions; a second 권고 line only if needed).

Weekly (Mondays, 5-7 lines): 핵심 (the week's governing message) → 흐름① {주제} / 흐름② {주제} / 흐름③ {주제} (main storylines with actors and figures) → optional 정책 → 시사점 → 다음 주 주목.

Content: lead with what matters most (critical/high, Korea, telecom); name products/actors/organisations; only key verified figures (CVSS, affected count, countries, versions, patch level). No copied titles, URLs, outlet names, item counts or severity tallies. Use only facts present in the given items.

Weekly analysis (the weekly PDF is built from this file, so it must be analytic, not a list of articles):
- themes: 3-5 storylines that group the week's items by shared actor, product, victim chain or trend. Each theme has
  "title" (Korean, ≤20 chars, names the pattern, e.g. "국내 업무 SW 공급망 연쇄 침해"), "ids" (item ids that belong to it),
  "insight" (무엇이 일어났나: 2-3 sentences, actors, figures, how it evolved over the week) and "implication"
  (통신사 시사점: why it matters for a telecom security centre and what to check). Order by risk (highest scores first).
- actions: 3-5 objects {"priority": "즉시" | "1주 내" | "1개월 내", "action": concrete check or fix with product versions,
  "why": "흐름 N · short reason"}.
- watch: 3-4 things to watch next week (pending investigations, patches, policy decisions).

Output files: daily `{"date":"YYYY-MM-DD","lines":[...]}`; weekly `{"start":"YYYY-MM-DD","end":"YYYY-MM-DD","lines":[...],"themes":[...],"actions":[...],"watch":[...]}`.
