#!/usr/bin/env python3
"""Build the source back-data registry (grade per source) from ops/sources.yaml + published daily data.
Output: data/sources/registry.json and data/sources/registry.csv   Run: python3 ops/scripts/build_registry.py --repo .
Grades are derived only from objective, checkable attributes (tier, source kind, Naver status, observed usage)."""
import argparse, csv, glob, json, os, re, sys, datetime as dt
sys.path.insert(0, os.path.dirname(__file__))
import pipeline as P

# kind <- the section comment above each yaml entry
KIND_RULES = [("government suffix", "gov"), ("government", "gov"), ("vendor psirt", "vendor"), ("vendor/project", "vendor"),
              ("carriers", "carrier"), ("vendor threat research", "research"), ("korean press", "press-kr"),
              ("international press", "press-intl")]
GRADE = {  # kind -> (grade, scope, rationale)
    "gov": ("A", "general", "정부·CERT·규제기관·표준기구 원문(1차 출처). 단독 게시 가능"),
    "vendor": ("B", "own-products", "제조사 PSIRT·보안공지(1차 출처). 자사 제품 한정 권위"),
    "carrier": ("B", "own-company", "통신사 공식 보도자료(1차 출처). 자사 사안 한정 권위"),
    "research": ("C", "general", "보안 벤더 위협 리서치(2차). 교차 확인 시 신뢰 가산"),
    "press-intl": ("C", "general", "주요 통신·보안 전문 매체(2차). 교차 확인 시 신뢰 가산"),
    "press-kr": ("D", "general", "국내 언론(2차). 네이버 뉴스 제휴 미확인 → 분기 검증 대상"),
}
COUNTRY = {"kr": "KR", "uk": "GB", "jp": "JP", "in": "IN", "sg": "SG", "au": "AU", "eu": "EU"}


def parse(repo):
    """yaml -> {domain: {tier, kind, naverUnverified}}"""
    out, tier, kind = {}, None, ""
    for raw in open(os.path.join(repo, "ops/sources.yaml"), encoding="utf-8"):
        s = raw.rstrip()
        if not s.strip():
            continue
        if not s.startswith(" ") and s.endswith(":") and not s.startswith("#"):
            tier = s[:-1].strip(); continue
        if s.strip().startswith("#"):
            low = s.strip().lower()
            for k, v in KIND_RULES:
                if k in low:
                    kind = v; break
            continue
        if tier in ("T1", "T2") and s.strip().startswith("- "):
            d = s.split("#", 1)[0].strip()[2:].strip().lower()
            k = kind or ("gov" if tier == "T1" else "press-intl")
            if "naver: unverified" in raw: k = "press-kr"
            out[d] = {"tier": tier, "kind": k, "naverUnverified": "naver: unverified" in raw}
    return out


def country(d):
    last = d.split(".")[-1]
    return COUNTRY.get(last) or ("KR" if d.endswith(".kr") else "US/INT")


def usage(repo):
    u = {}
    for f in sorted(glob.glob(os.path.join(repo, "data/daily/2026-*.json"))):
        day = os.path.basename(f)[:-5]
        try: items = json.load(open(f, encoding="utf-8"))
        except Exception: continue
        for it in items if isinstance(items, list) else []:
            urls = [it.get("sourceUrl")] + list(it.get("sources") or []) + list(it.get("crossCheckUrls") or [])
            seen = set()
            for url in filter(None, urls):
                rd = P.reg_domain(P.host_of(url)[1])
                if rd in seen: continue
                seen.add(rd); e = u.setdefault(rd, {"items": 0, "primary": 0, "last": "", "trust": []})
                e["items"] += 1; e["last"] = max(e["last"], day)
                if url == it.get("sourceUrl"): e["primary"] += 1
                if it.get("trust") is not None: e["trust"].append(it["trust"])
    return u


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", default="."); a = ap.parse_args()
    reg, use = parse(a.repo), usage(a.repo)
    ver = re.search(r"version:\s*(\S+)", open(os.path.join(a.repo, "ops/sources.yaml"), encoding="utf-8").read())
    rows = []
    for d, m in sorted(reg.items()):
        g, scope, why = GRADE[m["kind"]]
        key = P.reg_domain(d) if d.count(".") > 1 and P.reg_domain(d) != d else d
        e = use.get(d) or use.get(key) or {}
        rows.append({"domain": d, "tier": m["tier"], "grade": g, "kind": m["kind"], "scope": scope, "country": country(d),
                     "baseTrust": P.TIER_BASE[m["tier"]], "rationale": why,
                     "naver": "unverified" if m["naverUnverified"] else ("n/a" if m["kind"] != "press-kr" else "verified"),
                     "usedItems": e.get("items", 0), "usedAsPrimary": e.get("primary", 0), "lastSeen": e.get("last", ""),
                     "avgTrust": round(sum(e["trust"]) / len(e["trust"]), 1) if e.get("trust") else None,
                     "lastReviewed": "", "reviewNote": ""})
    tot = sum(r["usedItems"] for r in rows)
    meta = {"generated": dt.date.today().isoformat(), "sourcesYamlVersion": ver.group(1) if ver else "",
            "count": len(rows), "byGrade": {g: sum(1 for r in rows if r["grade"] == g) for g in "ABCD"},
            "usedItemsTotal": tot, "unlistedDomainsSeen": sorted(k for k in use if not any(k == r["domain"] or r["domain"].endswith("." + k) or k.endswith("." + r["domain"]) for r in rows)),
            "gradeScale": {"A": "T1 정부·CERT·규제·표준", "B": "T1 제조사 PSIRT·통신사 공식", "C": "T2 전문매체·벤더 리서치", "D": "T2 국내 언론(네이버 제휴 미확인)", "E": "미등록(T3) — 단독 게시 불가"},
            "note": "등급은 등록 속성(티어·유형·제휴 상태)에서 기계적으로 산출. 평판 점수·외부 지표는 포함하지 않음"}
    os.makedirs(os.path.join(a.repo, "data/sources"), exist_ok=True)
    json.dump({"meta": meta, "sources": rows}, open(os.path.join(a.repo, "data/sources/registry.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(a.repo, "data/sources/registry.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
