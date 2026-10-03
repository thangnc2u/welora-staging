"""Ticket "GP follow-up sau #246/#247", Phase 1 items 2–5.

2. N02-02 bank: exactly 6 core (q02f flipped to non-core, content unchanged), 12 × 4, draw 5 with ≥ 2 core.
3. Only ``hmac256:`` OTP rows are accepted (endpoint behaviour in tests/test_followup_244_245.py
   TestOtpHmac: an old-format row answers exactly like a wrong code).
4. WELORA_ENV=production refuses to start when the HMAC key source is dev or derived; staging / dev
   stay lenient (warning + /health source).
5. WELORA_ACADEMY_SESSION_CACHE_MAX documented in render.yaml as a comment only.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from welora import academy, otp_hash

ROOT = Path(__file__).resolve().parents[1]
CORE_N0202 = {"q02a", "q02c", "q02d", "q02g", "q02j", "q02l"}


class _Env(unittest.TestCase):
    KEYS = ("WELORA_ENV", "WELORA_OTP_HMAC_KEY", "WELORA_DB_URL")

    def setUp(self):
        self._prev = {k: os.environ.get(k) for k in self.KEYS}

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def env(self, **kv):
        for k, v in kv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestN0202SixCore(unittest.TestCase):
    def test_shape_and_core(self):
        bank = academy.QUESTIONS["N02-02"]
        self.assertEqual(len(bank), 12)
        self.assertTrue(all(len(q["choices"]) == 4 and len(set(q["choices"])) == 4 for q in bank))
        self.assertEqual({q["id"] for q in bank if q["hard"]}, CORE_N0202)
        q = next(q for q in bank if q["id"] == "q02f")
        self.assertFalse(q["hard"])
        self.assertEqual(q["choices"][q["answer"]], "Lập quỹ mục tiêu riêng và góp dần")  # content untouched
        self.assertEqual(academy.kuat_info("N02-02")["question_count"], 5)

    def test_draw_rules_unchanged(self):
        by_id = {q["id"]: q for q in academy.QUESTIONS["N02-02"]}
        for _ in range(60):
            served = academy._draw("N02-02")
            self.assertEqual(len(served), academy.KUAT_DRAW)
            self.assertGreaterEqual(sum(by_id[s["q"]]["hard"] for s in served), 2)
            self.assertTrue(academy.served_valid("N02-02", served))

    def test_every_bank_has_six_core(self):
        for nid, bank in academy.QUESTIONS.items():
            self.assertEqual(sum(q["hard"] for q in bank), 6, nid)


class TestLegacyFormatsRefused(unittest.TestCase):
    def test_only_hmac256_matches(self):
        h = otp_hash.code_hash("welora-phone-otp", "c1", "123456")
        self.assertTrue(otp_hash.matches("welora-phone-otp", "c1", h, "123456"))
        leg = otp_hash.legacy_hash("welora-phone-otp", "c1", "123456")
        for stored in (leg, leg[len("sha256:"):], "123456", ""):
            self.assertFalse(otp_hash.matches("welora-phone-otp", "c1", stored, "123456"), stored[:12])

    def test_callers_have_no_legacy_switch(self):
        for f in ("welora/auth.py", "welora/contact_verify.py", "welora/admin_bootstrap.py", "welora/otp_hash.py"):
            src = (ROOT / f).read_text(encoding="utf-8")
            self.assertNotIn("legacy_plain", src, f)
            self.assertNotIn("legacy_bare_hex", src, f)


class TestProductionKeyRequired(_Env):
    def test_matrix(self):
        for env_name in ("production", "prod", "PRODUCTION"):
            self.env(WELORA_ENV=env_name, WELORA_OTP_HMAC_KEY=None, WELORA_DB_URL=None)
            self.assertEqual(otp_hash.key_source(), "dev")
            with self.assertRaises(otp_hash.OtpKeyError) as e:
                otp_hash.require_production_key()
            self.assertIn("WELORA_OTP_HMAC_KEY", str(e.exception))
            self.assertIn("dev", str(e.exception))
            self.env(WELORA_DB_URL="sqlite:////tmp/x.db")
            self.assertEqual(otp_hash.key_source(), "derived")
            with self.assertRaises(otp_hash.OtpKeyError) as e:
                otp_hash.require_production_key()
            self.assertIn("derived", str(e.exception))
            self.env(WELORA_OTP_HMAC_KEY="k" * 48)
            otp_hash.require_production_key()  # env → starts
        for env_name in ("staging", "", "dev"):
            for db in (None, "sqlite:////tmp/x.db"):
                self.env(WELORA_ENV=env_name, WELORA_OTP_HMAC_KEY=None, WELORA_DB_URL=db)
                otp_hash.require_production_key()  # lenient
                with self.assertLogs("welora.otp_hash", level="WARNING"):
                    self.assertTrue(otp_hash.startup_check())

    def test_uvicorn_exits_in_production_without_key(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        d = tempfile.mkdtemp()
        env = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
        env.update({"PYTHONPATH": str(ROOT), "WELORA_ENV": "production", "WELORA_STORE": "sqlite",
                    "WELORA_DB_URL": f"sqlite:///{d}/prod.db", "WELORA_DEMO_AUTOSEED": "0"})
        p = subprocess.run([sys.executable, "-m", "uvicorn", "welora.api.app:app", "--host", "127.0.0.1",
                            "--port", str(port), "--no-proxy-headers"], cwd=str(ROOT), env=env,
                           capture_output=True, text=True, timeout=120)
        out = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, out[-2000:])
        self.assertIn("WELORA_OTP_HMAC_KEY is not set", out)
        self.assertIn("Application startup failed", out)


class TestDocs(unittest.TestCase):
    def test_render_yaml(self):
        y = (ROOT / "render.yaml").read_text(encoding="utf-8")
        lines = [l for l in y.splitlines() if "WELORA_ACADEMY_SESSION_CACHE_MAX" in l]
        self.assertTrue(lines)
        self.assertTrue(all(l.lstrip().startswith("#") for l in lines), lines)  # comment only, no value
        self.assertNotRegex(y, r"-\s*key:\s*WELORA_ACADEMY_SESSION_CACHE_MAX")
        self.assertRegex(y, r"REQUIRED in production")
        self.assertRegex(y, r"- key: WELORA_OTP_HMAC_KEY\n\s+sync: false")

    def test_readme(self):
        r = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("WELORA_OTP_HMAC_KEY", r)
        self.assertIn("WELORA_ENV=production", r)


if __name__ == "__main__":
    unittest.main()
