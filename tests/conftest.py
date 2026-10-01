"""Shared pytest setup.

P0 follow-up: the app lifespan starts a background demo seed (WELORA_GUEST_DEMO on, non-prod).
Tests that enter the lifespan (``with TestClient(app)``) must not get a seeder thread writing into
their DB behind their back, so auto-seed is off unless a test opts in explicitly.
"""

import os

os.environ.setdefault("WELORA_DEMO_AUTOSEED", "0")
