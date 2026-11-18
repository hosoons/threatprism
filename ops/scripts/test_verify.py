#!/usr/bin/env python3
"""Offline tests for `pipeline.py verify` (and the verify-drop hook in `select`). Run: python3 ops/scripts/test_verify.py"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PIPE = os.path.join(HERE, "pipeline.py")
FIX = {"/2026/1xxx/CVE-2026-1000.json": "PUBLISHED", "/2026/1xxx/CVE-2026-1001.json": "REJECTED", "/2026/2xxx/CVE-2026-2000.json": "PUBLISHED",
       "/2026/0xxx/CVE-2026-0042.json": "PUBLISHED", "/2026/12xxx/CVE-2026-12345.json": "PUBLISHED",
       "/2026/3xxx/CVE-2026-3000.json": {"state": "PUBLISHED", "datePublished": "2098-12-20T00:00:00.000Z", "scores": [9.8]},
       "/2026/3xxx/CVE-2026-3001.json": {"state": "PUBLISHED", "datePublished": "2098-01-01T00:00:00.000Z", "scores": [7.5]}}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        st = FIX.get(self.path)
        if st is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.end_headers()
        if isinstance(st, dict):
            body = {"cveMetadata": {"state": st["state"], "datePublished": st["datePublished"]},
                    "containers": {"cna": {"metrics": [{"cvssV3_1": {"baseScore": x}} for x in st["scores"]]}}}
        else:
            body = {"cveMetadata": {"state": st}}
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *a):
        pass


def item(n, cat, url, tier, title, **kw):
    d = {"id": f"inc-2099-0101-{n:03d}", "title": title, "category": cat, "severity": "high", "country": "US", "region": "North America", "source": "x",
         "sourceUrl": url, "date": "2099-01-01", "summary": title, "tags": ["a"], "score": 60, "scoreFactors": {"target": 10, "exploit": 0, "technical": 0, "scale": 0, "domestic": 0},
         "trust": 70, "sourceTier": tier}
    d.update(kw)
    return d


class VerifyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo, self.run = os.path.join(self.tmp, "repo"), os.path.join(self.tmp, "run")
        os.makedirs(os.path.join(self.repo, "ops")); os.makedirs(os.path.join(self.repo, "data/daily")); os.makedirs(self.run)
        shutil.copy(os.path.join(REPO, "ops/sources.yaml"), os.path.join(self.repo, "ops/sources.yaml"))
        json.dump([], open(os.path.join(self.repo, "data/daily/manifest.json"), "w"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def verify(self, items, link=None, base=None):
        json.dump(items, open(os.path.join(self.run, "daily.json"), "w"))
        json.dump({}, open(os.path.join(self.run, "stats.json"), "w"))
        cmd = [sys.executable, PIPE, "verify", "--repo", self.repo, "--date", "2099-01-01", "--run", self.run, "--cve-base", base or self.base]
        if link is not None:
            lp = os.path.join(self.run, "linkcheck.json"); json.dump(link, open(lp, "w")); cmd += ["--linkcheck", lp]
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = {i["id"]: i for i in json.load(open(os.path.join(self.run, "daily.json")))}
        return out, json.load(open(os.path.join(self.run, "stats.json")))

    def test_cve_rules_grades_and_links(self):
        items = [
            item(1, "VUL", "https://thehackernews.com/a", "T2", "fake cve CVE-2026-9999 exploited"),          # unknown CVE, T2, no KEV -> drop
            item(2, "VUL", "https://www.cisa.gov/b", "T1", "advisory CVE-2026-9998"),                          # unknown CVE but T1 -> keep, flag
            item(3, "INC", "https://www.lightreading.com/c", "T2", "breach CVE-2026-1001"),                    # rejected CVE on INC -> keep, flag
            item(4, "TCH", "https://www.etnews.com/d", "T2", "tech story"),                                    # link dead -> drop
            item(5, "INC", "https://www.reuters.com/e", "T2", "incident"),                                     # link ok -> linkChecked
            item(6, "REG", "https://www.korea.kr/f", "T1", "policy"),                                          # grade A
            item(7, "VUL", "https://thehackernews.com/g", "T2", "real CVE-2026-1000 and CVE-2026-0042 CVE-2026-12345"),  # all ok -> verified
            item(8, "VUL", "https://thehackernews.com/h", "T2", "kev one CVE-2026-9997", kev=True),            # unknown but KEV -> keep, flag
            item(9, "MKT", "https://unlisted-site.example/i", "T3", "market"),                                  # grade E, mismatch -> drop
        ]
        link = [{"url": "https://www.etnews.com/d", "status": "dead", "note": "404"}, {"url": "https://www.reuters.com/e", "status": "ok"},
                {"url": "https://unlisted-site.example/i", "status": "mismatch", "note": "title not on page"}, {"url": "https://www.cisa.gov/b", "status": "blocked"}]
        out, st = self.verify(items, link)
        ids = lambda n: f"inc-2099-0101-{n:03d}"
        self.assertNotIn(ids(1), out); self.assertNotIn(ids(4), out); self.assertNotIn(ids(9), out)
        self.assertEqual(out[ids(2)]["cveUnverified"], ["CVE-2026-9998"])
        self.assertEqual(out[ids(3)]["cveUnverified"], ["CVE-2026-1001"])
        self.assertTrue(out[ids(5)]["linkChecked"]); self.assertEqual(out[ids(6)]["sourceGrade"], "A"); self.assertEqual(out[ids(5)]["sourceGrade"], "C")
        self.assertTrue(out[ids(7)]["cveVerified"]); self.assertNotIn("cveVerified", out[ids(8)])
        self.assertEqual(st["verify"]["dropped"], 3); self.assertEqual(st["total"], 6)
        self.assertEqual(len(json.load(open(os.path.join(self.run, "verify-drop.json")))), 3)
        self.assertTrue(st["needMore"])  # 6 items < 14

    def test_cvss_claim_is_cross_checked_and_old_cve_noted(self):
        items = [item(1, "VUL", "https://www.cisa.gov/a", "T1", "Vendor fixes CVE-2026-3000 (CVSS 9.8)"),
                 item(2, "VUL", "https://www.cisa.gov/b", "T1", "Vendor fixes CVE-2026-3000 (CVSS 6.1)"),
                 item(3, "VUL", "https://www.cisa.gov/c", "T1", "Old bug CVE-2026-3001 resurfaces (CVSS 7.5)"),
                 item(4, "VUL", "https://www.cisa.gov/d", "T1", "Vendor fixes CVE-2026-3000", kev=True)]
        out, st = self.verify(items)
        self.assertNotIn("cvssMismatch", out["inc-2099-0101-001"])           # claimed 9.8 == record 9.8
        self.assertEqual(out["inc-2099-0101-002"]["cvssMismatch"], {"claimed": [6.1], "record": [9.8]})  # flagged, not dropped
        self.assertEqual(len(out), 4)
        self.assertGreater(out["inc-2099-0101-003"]["cveAgeDays"], 180)      # CVE record is a year old
        self.assertNotIn("cveAgeDays", out["inc-2099-0101-004"])             # KEV listing exempts
        self.assertNotIn("cveAgeDays", out["inc-2099-0101-001"])             # published 12 days before the item
        self.assertEqual(st["verify"]["cvssMismatch"], 1)

    def test_cvss_claim_parsing(self):
        sys.path.insert(0, HERE)
        import pipeline as P
        self.assertEqual(P.cvss_claims("악용(CVSS 10.0)"), [10.0])
        self.assertEqual(P.cvss_claims("CVSS 4.0 9.2 인증 없는 RCE"), [9.2])
        self.assertEqual(P.cvss_claims("CVSS v3.1: 7.5, CVSS 8.8"), [7.5, 8.8])
        self.assertEqual(P.cvss_claims("CVSS 9.8"), [9.8])
        self.assertEqual(P.cvss_claims("점수 없음"), [])

    def test_no_record_scores_means_no_cvss_flag(self):
        out, _ = self.verify([item(1, "VUL", "https://www.cisa.gov/a", "T1", "Bug CVE-2026-2000 (CVSS 9.1)")])
        self.assertNotIn("cvssMismatch", out["inc-2099-0101-001"])

    def test_network_down_never_blocks(self):
        items = [item(1, "VUL", "https://thehackernews.com/a", "T2", "x CVE-2026-9999")]
        out, st = self.verify(items, base="http://127.0.0.1:9")  # closed port
        self.assertIn("inc-2099-0101-001", out)
        self.assertEqual(st["verify"]["cve"]["unchecked"], 1); self.assertEqual(st["verify"]["dropped"], 0)
        self.assertNotIn("cveUnverified", out["inc-2099-0101-001"])

    def test_published_items_are_not_rechecked(self):
        json.dump([item(1, "VUL", "https://thehackernews.com/a", "T2", "old CVE-2026-9999")], open(os.path.join(self.repo, "data/daily/2099-01-01.json"), "w"))
        out, st = self.verify([item(1, "VUL", "https://thehackernews.com/a", "T2", "old CVE-2026-9999")])
        self.assertIn("inc-2099-0101-001", out); self.assertEqual(st["verify"]["checkedItems"], 0)

    def test_select_skips_dropped_urls(self):
        json.dump(["https://thehackernews.com/a"], open(os.path.join(self.run, "verify-drop.json"), "w"))
        cand = {"title": "t", "category": "INC", "country": "US", "countryName": "미국", "region": "North America", "source": "THN", "sourceUrl": "https://thehackernews.com/a",
                "crossCheckUrls": ["https://www.bleepingcomputer.com/b"], "date": "2099-01-01", "summary": "s", "tags": ["a"], "scoreFactors": {"target": 10, "exploit": 0, "technical": 0, "scale": 0, "domestic": 0}}
        json.dump([cand], open(os.path.join(self.run, "cand-x.json"), "w"))
        r = subprocess.run([sys.executable, PIPE, "select", "--repo", self.repo, "--date", "2099-01-01", "--run", self.run], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.load(open(os.path.join(self.run, "stats.json")))
        self.assertEqual(st["candidates"], 0); self.assertIn("verify-drop", st["held"][0]["reason"])


class TimelineTest(unittest.TestCase):
    def pipe(self, *args):
        return subprocess.run([sys.executable, PIPE, *args], capture_output=True, text=True)

    def test_timeline_file_is_consistent(self):
        t = json.load(open(os.path.join(REPO, "ops/timeline.json")))
        m = lambda k: int(t[k][:2]) * 60 + int(t[k][3:])
        order = ["production", "preflightDeadline", "earlyWatchdog", "dataReady", "publishFrom", "sendFrom", "runlogBy", "target", "lateWatchdog", "delayAfter"]
        self.assertEqual([m(k) for k in order], sorted(m(k) for k in order), "clock points must be in chronological order")
        self.assertGreaterEqual(m("earlyWatchdog") - m("preflightDeadline"), 5)   # watchdog looks after the beacon deadline
        self.assertLess(m("preflightDeadline") - m("production"), 10)             # preflight takes <= ~8 min
        self.assertGreater(m("lateWatchdog"), m("runlogBy"))                      # late watchdog never overlaps a healthy run
        self.assertGreaterEqual(m("sendFrom") - m("publishFrom"), 8)              # room for the PDF build
        s = open(PIPE, encoding="utf-8").read()
        self.assertNotIn("DELAY_AFTER_HHMM = (10, 10)", s)                        # constants come from the timeline file

    def test_hold_points(self):
        self.assertEqual(self.pipe("hold", "--repo", REPO, "--date", "2099-01-01", "--now", "2099-01-01T09:30").stdout.strip(), "WAIT 16")
        self.assertEqual(self.pipe("hold", "--repo", REPO, "--date", "2099-01-01", "--now", "2099-01-01T09:45").stdout.strip(), "READY")
        self.assertEqual(self.pipe("hold", "--repo", REPO, "--date", "2099-01-01", "--until", "publish", "--now", "2099-01-01T09:30").stdout.strip(), "WAIT 6")
        self.assertEqual(self.pipe("hold", "--repo", REPO, "--date", "2099-01-01", "--until", "publish", "--now", "2099-01-01T09:36").stdout.strip(), "READY")

    def run_log(self, marks, mode):
        tmp = tempfile.mkdtemp()
        try:
            for step, now in marks:
                self.assertEqual(self.pipe("mark", "--repo", REPO, "--date", "2099-01-01", "--run", tmp, "--step", step, "--now", "2099-01-01T" + now).returncode, 0)
            r = self.pipe("runlog", "--repo", REPO, "--date", "2099-01-01", "--run", tmp, "--mode", mode, "--status", "pdf=generated")
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_runlog_timeline_on_time_and_deviations(self):
        ok = self.run_log([("start", "09:05"), ("beacon", "09:09"), ("collected", "09:28"), ("published", "09:36"), ("pdfReady", "09:38"), ("sent", "09:45")], "PRODUCTION")
        self.assertEqual(ok["timeline"]["deviations"], [])
        self.assertEqual(ok["timeline"]["actual"]["published"], "09:36")
        bad = self.run_log([("beacon", "09:16"), ("published", "09:50"), ("pdfReady", "09:52"), ("sent", "09:44")], "PRODUCTION")
        txt = " | ".join(bad["timeline"]["deviations"])
        for needle in ("비콘", "앱 반영 09:50", "PDF 준비", "발송이 앱 반영보다 먼저", "발송 09:44"):
            self.assertIn(needle, txt)
        retry = self.run_log([("published", "09:31"), ("pdfReady", "09:33"), ("sent", "09:45")], "RETRY")   # a rescue may publish before 09:35
        self.assertEqual(retry["timeline"]["deviations"], [])

    def test_stamp_writes_publish_time(self):
        tmp = tempfile.mkdtemp()
        try:
            for n in ("brief.json", "briefing.json"):
                json.dump({"date": "2099-01-01", "lines": ["x"]}, open(os.path.join(tmp, n), "w"))
            r = self.pipe("stamp", "--repo", REPO, "--date", "2099-01-01", "--run", tmp, "--now", "2099-01-01T09:36")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.load(open(os.path.join(tmp, "briefing.json")))["publishedAtKst"], "2099-01-01 09:36")
            self.assertEqual(json.load(open(os.path.join(tmp, "times.json")))["published"], "09:36:00")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
