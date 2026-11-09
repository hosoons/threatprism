# Agent: collector-upgrade (source upgrade round)
Input: /tmp/run/held.json, an array of held candidates {title, url, reason, category, candidate:{...full candidate...}}.
Goal: rescue held stories by finding the missing confirmation. Do NOT change facts to fit; only add sources you opened.
For each held item (best score first, at most 12):
- reason "INC needs a T1 source or two independent T2 sources": WebSearch the victim/product/CVE + Korean/English keywords; open a
  second, different T2 outlet or a T1 notice (KISA, 과기정통부, 개인정보위, the company's own notice, vendor advisory); add it to crossCheckUrls.
- reason "VUL needs a CISA KEV match or a T1 vendor/CERT source": search the vendor/project advisory page (vendor PSIRT, project security page,
  CISA alert, KISA 보호나라) and add the opened URL; add the CVE IDs to `cves`.
- reason "REG needs the government/regulator original (T1)": search the ministry/regulator press release (korea.kr, 과기정통부, 개인정보위, 금융위, gov.uk ...) and add the opened URL.
- reason "trust < 60": add an independent T1/T2 confirmation.
Rules: follow ops/agents/_common.md (open only URLs that appeared in your own WebSearch results; never type URLs). Keep the original candidate fields
(title, summary, scoreFactors...), update summary only with facts present in the sources, and extend crossCheckUrls. If nothing is found, skip the item.
Write the rescued candidates (same schema as the other cand files) to /tmp/run/cand-upgrade.json. Reply with one line: "done N upgraded of M".
Model: sonnet.
