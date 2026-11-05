# Executive summary rules (McKinsey/BCG style)

Audience: telecom security C-level. Pyramid principle (conclusion first), MECE evidence, data-backed, then so-what and actions.
Korean 개조식 (noun endings such as ~확산, ~확인, ~필요, ~추진; never ~습니다/~이다). Each line "라벨: 내용", about 50-95 Korean characters.

Daily (5-7 lines, this order): 핵심 (governing message of the day) → 2-4 evidence lines chosen MECE from 위협 / 취약점 / 국내·산업 / 규제·정책 → 시사점 (so-what for a telecom security centre) → 권고 (priority actions; a second 권고 line only if needed).

Weekly (Mondays, 5-7 lines): 핵심 (the week's governing message) → 흐름① {주제} / 흐름② {주제} / 흐름③ {주제} (main storylines with actors and figures) → optional 정책 → 시사점 → 다음 주 주목.

Content: lead with what matters most (critical/high, Korea, telecom); name products/actors/organisations; only key verified figures (CVSS, affected count, countries, versions, patch level). No copied titles, URLs, outlet names, item counts or severity tallies. Use only facts present in the given items.

Output files: daily `{"date":"YYYY-MM-DD","lines":[...]}`; weekly `{"start":"YYYY-MM-DD","end":"YYYY-MM-DD","lines":[...]}`.
