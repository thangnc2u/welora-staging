"""P2 OS Persist Mode C — SQLite write → clear memory → reload → assert.

DoD:
- Persist proposal / pending_cool_off / pending_dual / confirmed / undone + companion
- Survive restart (process reload sim)
- Schema version / migration
- Mode C API + L-* / cool-off / dual unchanged
- No Hard Deny / TARGET_MONTHS / CORE / bank / Postgres
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from welora.agent import HARD, PRIORITY, CONFIDENCE_THRESHOLD, run_hard_deny_suite
from welora.fixtures import load_pair, reset_all_stores
from welora.mode_c_act import (
    ACT_CREATE_ENVELOPE,
    POLICY_COOL_OFF,
    POLICY_DUAL_CONTROL,
    companion_confirm_act,
    confirm_act,
    clear_mode_c_memory,
    disable_mode_c_persist,
    enable_mode_c_persist,
    get_companion,
    inject_clock_advance,
    list_envelopes,
    list_pending_dual,
    propose_act,
    reload_mode_c_from_sqlite,
    reset_mode_c_store,
    set_companion,
    set_persona,
    undo_act,
)
from welora import mode_c_persist as mcp
from welora.safety_gate import TARGET_MONTHS


class TestP2OsModeCPersist(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        cls.pair = load_pair()

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "mode_c_test.db")
        # Isolate from any ambient WELORA_STORE=sqlite
        self._prev_store = os.environ.get("WELORA_STORE")
        self._prev_mc = os.environ.get("WELORA_MODE_C_DB")
        self._prev_flag = os.environ.get("WELORA_MODE_C_PERSIST")
        os.environ["WELORA_STORE"] = "memory"
        os.environ.pop("WELORA_MODE_C_DB", None)
        os.environ.pop("WELORA_MODE_C_PERSIST", None)
        disable_mode_c_persist()
        reset_mode_c_store()
        enable_mode_c_persist(self.db_path)

    def tearDown(self) -> None:
        reset_mode_c_store()
        disable_mode_c_persist()
        if self._prev_store is None:
            os.environ.pop("WELORA_STORE", None)
        else:
            os.environ["WELORA_STORE"] = self._prev_store
        if self._prev_mc is None:
            os.environ.pop("WELORA_MODE_C_DB", None)
        else:
            os.environ["WELORA_MODE_C_DB"] = self._prev_mc
        if self._prev_flag is None:
            os.environ.pop("WELORA_MODE_C_PERSIST", None)
        else:
            os.environ["WELORA_MODE_C_PERSIST"] = self._prev_flag
        self._tmpdir.cleanup()

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.80)
        self.assertEqual(HARD, {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"})
        self.assertEqual(
            PRIORITY,
            ["R01", "R03", "R02", "R08", "R09", "R06", "R07", "R04", "R05"],
        )
        passed_n, failed = run_hard_deny_suite()
        self.assertEqual(failed, [])
        self.assertEqual(passed_n, 8)
        # No Postgres migration for Mode C
        pg_mig = Path(__file__).resolve().parents[1] / "welora" / "db" / "migrations" / "postgres"
        self.assertFalse(any(pg_mig.glob("*mode_c*")))

    def test_schema_version_and_migration(self):
        self.assertTrue(Path(self.db_path).exists())
        self.assertEqual(mcp.schema_version(), mcp.SCHEMA_VERSION)
        # idempotent migrate
        self.assertEqual(mcp.migrate(), mcp.SCHEMA_VERSION)
        self.assertEqual(mcp.schema_version(), 1)

    def test_companion_survives_restart(self):
        code, body = set_companion(user_id="u1", companion_user_id="c1")
        self.assertEqual(code, 200)
        self.assertEqual(body["link"]["companion_user_id"], "c1")

        clear_mode_c_memory()
        self.assertIsNone(get_companion("u1"))

        stats = reload_mode_c_from_sqlite()
        self.assertEqual(stats["companions"], 1)
        link = get_companion("u1")
        self.assertIsNotNone(link)
        self.assertEqual(link["companion_user_id"], "c1")
        self.assertEqual(link["policy_version"], POLICY_DUAL_CONTROL)

    def test_open_proposal_survives_restart_then_confirm(self):
        code, body = propose_act(
            user_id="u-prop",
            message="Tạo phong bì Du lịch",
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        prop = body["act_proposal"]
        pid = prop["proposal_id"]
        self.assertEqual(prop["status"], "proposed")

        clear_mode_c_memory()
        reload_mode_c_from_sqlite()

        code2, conf = confirm_act(
            user_id="u-prop",
            proposal_id=pid,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(code2, 200)
        self.assertTrue(conf["ok"])
        self.assertEqual(conf["act_kind"], ACT_CREATE_ENVELOPE)
        self.assertIn("undo", conf)

        # envelopes also reloaded path: confirmed write persisted
        clear_mode_c_memory()
        reload_mode_c_from_sqlite()
        _c, env = list_envelopes("u-prop")
        self.assertEqual(len(env["items"]), 1)
        self.assertIn("Du lịch", env["items"][0]["title"])

    def test_pending_cool_off_countdown_survives_restart(self):
        set_persona(user_id="u-cool", persona="P1")
        code, body = propose_act(
            user_id="u-cool",
            message="Rút quỹ khẩn cấp 5000000",
            gate_status="passed",
            answer_confidence=0.95,
            params={
                "amount": 5_000_000,
                "current_amount": 10_000_000,
                "essential_expense_monthly": 5_000_000,
            },
            reason="Cần tiền chữa bệnh",
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["status"], "pending_cool_off")
        prop = body["act_proposal"]
        pid = prop["proposal_id"]
        until = prop["cool_off_until"]
        self.assertTrue(until)

        # early confirm still pending after restart
        clear_mode_c_memory()
        reload_mode_c_from_sqlite()
        code_e, early = confirm_act(
            user_id="u-cool",
            proposal_id=pid,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(code_e, 200)
        self.assertEqual(early["status"], "pending_cool_off")
        self.assertTrue(early.get("still_pending") or early.get("needs_cool_off_wait"))

        # advance clock + confirm after reload
        inject_clock_advance(hours=25)
        code_ok, done = confirm_act(
            user_id="u-cool",
            proposal_id=pid,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(code_ok, 200)
        self.assertTrue(done["ok"])
        self.assertTrue(done.get("cool_off_completed"))
        self.assertEqual(done.get("rule"), POLICY_COOL_OFF)

    def test_pending_dual_survives_restart_then_companion_confirm(self):
        primary = self.pair["passed"]["user_id"]
        companion = "user_companion_persist_01"
        set_companion(user_id=primary, companion_user_id=companion)
        # create envelope first (non-dual) so lock has target
        _c, p0 = propose_act(
            user_id=primary,
            message="Tạo phong bì Nhà",
            gate_status="passed",
            answer_confidence=0.95,
        )
        confirm_act(
            user_id=primary,
            proposal_id=p0["act_proposal"]["proposal_id"],
            confirm=True,
            gate_status="passed",
            answer_confidence=0.95,
        )

        code, body = propose_act(
            user_id=primary,
            message="Khóa phong bì cấm lấy chéo",
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["status"], "pending_dual")
        pid = body["act_proposal"]["proposal_id"]

        clear_mode_c_memory()
        reload_mode_c_from_sqlite()

        _c, pending = list_pending_dual(primary)
        self.assertEqual(len(pending["items"]), 1)
        self.assertEqual(pending["items"][0]["proposal_id"], pid)

        # companion confirm after restart (server gate from fixture user)
        code2, conf = companion_confirm_act(
            companion_user_id=companion,
            proposal_id=pid,
            confirm=True,
        )
        self.assertEqual(code2, 200)
        self.assertTrue(conf["ok"])
        self.assertEqual(conf["rule"], POLICY_DUAL_CONTROL)

    def test_undo_after_restart(self):
        code, body = propose_act(
            user_id="u-undo",
            message="Tạo phong bì UndoMe",
            gate_status="passed",
            answer_confidence=0.95,
        )
        pid = body["act_proposal"]["proposal_id"]
        _c, conf = confirm_act(
            user_id="u-undo",
            proposal_id=pid,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.95,
        )
        act_id = conf["act_id"]
        token = conf["undo"]["token"]

        clear_mode_c_memory()
        reload_mode_c_from_sqlite()

        code_u, undone = undo_act(
            user_id="u-undo",
            act_id=act_id,
            undo_token=token,
        )
        self.assertEqual(code_u, 200)
        self.assertTrue(undone["undone"])

        _c, env = list_envelopes("u-undo")
        self.assertEqual(env["items"], [])

        # proposal status undone persists
        clear_mode_c_memory()
        reload_mode_c_from_sqlite()
        from welora.mode_c_act import _PROPOSALS

        self.assertEqual(_PROPOSALS[pid]["status"], "undone")

    def test_write_drop_memory_reload_roundtrip_statuses(self):
        """Canonical suite: write → drop memory → reload → assert states."""
        set_companion(user_id="u-rt", companion_user_id="c-rt")
        set_persona(user_id="u-rt", persona="P2")

        # proposed
        _c, b1 = propose_act(
            user_id="u-rt",
            message="Tạo phong bì A",
            gate_status="passed",
            answer_confidence=0.9,
        )
        p_proposed = b1["act_proposal"]["proposal_id"]

        # pending_cool_off
        _c, b2 = propose_act(
            user_id="u-rt",
            message="Rút quỹ khẩn cấp 2000000",
            gate_status="passed",
            answer_confidence=0.9,
            params={
                "amount": 2_000_000,
                "current_amount": 5_000_000,
                "essential_expense_monthly": 1_000_000,
            },
            reason="Cần tiền gấp",
        )
        self.assertEqual(b2["status"], "pending_cool_off")
        p_cool = b2["act_proposal"]["proposal_id"]

        # pending_dual
        _c, b3 = propose_act(
            user_id="u-rt",
            message="Đổi trần phong bì 9000000",
            gate_status="passed",
            answer_confidence=0.9,
        )
        self.assertEqual(b3["status"], "pending_dual")
        p_dual = b3["act_proposal"]["proposal_id"]

        # confirmed
        _c, conf = confirm_act(
            user_id="u-rt",
            proposal_id=p_proposed,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.9,
        )
        self.assertTrue(conf["ok"])

        clear_mode_c_memory()
        stats = reload_mode_c_from_sqlite()
        self.assertGreaterEqual(stats["proposals"], 3)
        self.assertEqual(stats["companions"], 1)
        self.assertEqual(stats["schema_version"], 1)

        from welora.mode_c_act import _PROPOSALS, _COMPANIONS, _PERSONAS

        self.assertEqual(_PROPOSALS[p_proposed]["status"], "confirmed")
        self.assertEqual(_PROPOSALS[p_cool]["status"], "pending_cool_off")
        self.assertEqual(_PROPOSALS[p_dual]["status"], "pending_dual")
        self.assertEqual(_COMPANIONS["u-rt"]["companion_user_id"], "c-rt")
        self.assertEqual(_PERSONAS["u-rt"], "P2")
        self.assertTrue(_PROPOSALS[p_cool].get("cool_off_until"))


if __name__ == "__main__":
    unittest.main()
