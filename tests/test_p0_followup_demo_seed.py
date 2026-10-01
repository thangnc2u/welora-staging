"""P0 follow-up #3 — demo seed P1–P6: one transaction, idempotent, lock-guarded, after every deploy.

Runs on SQLite by default and on real PostgreSQL when WELORA_TEST_POSTGRES_URL is set
(tests/_db_target.py — that database's public schema is reset per test). Each DB scenario runs in a
fresh interpreter (tests/_followup_dbmode.py) because the OS stores are chosen at import time.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests._db_target import db_env
from tests._followup_dbmode import run_scenario
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {  # identical to main d6fe797 right after a seed (only now also after a restart)
    "P1": ["not_passed", True],
    "P2": ["passed", True],
    "P3": ["passed", False],
    "P4": ["not_passed", True],
    "P5": ["not_passed", True],
    "P6": ["passed", False],
}


class _SeedBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="welora-seed-")
        self.env = {"WELORA_GUEST_DEMO": "1", "WELORA_ENV": "staging", **db_env(self.tmp)}

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_s(self, name: str, **extra: str) -> dict:
        return run_scenario(name, {**self.env, **extra})


class TestDemoSeedAtomic(_SeedBase):
    def test_idempotent_and_gate_stable_after_restart(self):
        out = self.run_s("seed_idempotent")
        c1, c2, c3 = out["counts"]
        self.assertEqual(c1, c2)
        self.assertEqual(c2, c3)
        self.assertGreaterEqual(c1["users"], 8)  # 6 persona aliases + 2 fixture personas
        self.assertEqual(out["rich_gates"], ["passed"] * 3 + ["not_passed"] * 3)  # P2 ×3, P4 ×3
        self.assertEqual(out["fixture_personas"], ["P2", "P4"])
        self.assertEqual(out["email"], "partner@welora.demo")
        self.assertEqual(out["gates_hot"], EXPECTED)
        # fresh instance (no process memory) reads the same gates — P2 no longer mastery_missing
        self.assertEqual(out["gates_cold"], EXPECTED)

    def test_readers_never_see_partial_state(self):
        out = self.run_s("seed_no_flap")
        self.assertEqual(out["errors"], [])
        self.assertEqual(set(out["seen"]["P2"]), {"passed|True"}, out["seen"])
        self.assertEqual(set(out["seen"]["P4"]), {"not_passed|True"}, out["seen"])
        self.assertGreater(sum(out["seen"]["P2"].values()), 0)

    def test_failure_rolls_back_everything_and_startup_continues(self):
        out = self.run_s("seed_rollback")
        self.assertEqual(out["raised"], "RuntimeError")
        self.assertEqual(out["startup"]["status"], "failed")  # logged, not raised
        self.assertEqual(out["before"], out["after"])
        self.assertEqual(out["g_before"], EXPECTED)
        self.assertEqual(out["g_after"], EXPECTED)

    def test_concurrent_instance_lock_skips(self):
        out = self.run_s("seed_locked")
        self.assertEqual(out["locked"], "SeedLocked")
        self.assertEqual(out["startup"]["status"], "skipped")
        self.assertEqual(out["after_release"], "passed")

    def test_startup_lifespan_seeds_in_background(self):
        out = self.run_s("lifespan_autoseed")
        self.assertEqual(out["health_demo_seed"], "ok")
        self.assertEqual(out["gates_cold"], EXPECTED)


class TestDemoSeedRespectsFlag(_SeedBase):
    def test_guest_demo_off_never_seeds(self):
        out = self.run_s("seed_disabled", WELORA_GUEST_DEMO="0")
        self.assertEqual(out["run"].get("reason"), "demo_seed_disabled")
        self.assertEqual(out["wanted"], [False, "WELORA_GUEST_DEMO=0"])
        self.assertEqual(out["startup"]["status"], "skipped")
        self.assertFalse(out["counts"].get("users"))  # nothing written (tables not even created)

    def test_autoseed_skips_production_and_opt_out(self):
        from welora import demo_seed_runner as r

        keys = ("WELORA_GUEST_DEMO", "WELORA_ENV", "WELORA_DEMO_AUTOSEED")
        prev = {k: os.environ.get(k) for k in keys}
        try:
            os.environ.update({"WELORA_GUEST_DEMO": "1", "WELORA_ENV": "production", "WELORA_DEMO_AUTOSEED": "1"})
            self.assertEqual(r.autoseed_wanted(), (False, "WELORA_ENV=production"))
            self.assertIsNone(r.start_background_seed())
            os.environ["WELORA_ENV"] = "staging"
            os.environ["WELORA_DEMO_AUTOSEED"] = "0"
            self.assertEqual(r.autoseed_wanted(), (False, "WELORA_DEMO_AUTOSEED=0"))
            os.environ["WELORA_DEMO_AUTOSEED"] = "1"
            os.environ["WELORA_GUEST_DEMO"] = "0"
            self.assertEqual(r.autoseed_wanted(), (False, "WELORA_GUEST_DEMO=0"))
            os.environ["WELORA_GUEST_DEMO"] = "1"
            self.assertEqual(r.autoseed_wanted(), (True, ""))
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        src = (ROOT / "welora" / "demo_seed_runner.py").read_text(encoding="utf-8")
        self.assertIn("pg_try_advisory_xact_lock", src)
        self.assertIn("ambient_transaction", src)


if __name__ == "__main__":
    unittest.main()
