"""
Regression test for a real bug caught during development: repository.py
originally did `from app.db import get_client`, which binds a local name
at first-import time. If ANY test module imports app.main (directly or
transitively) before conftest.py's fake_supabase fixture has run its
monkeypatch, that early import permanently captures the real (unpatched)
get_client function — silently breaking every other test's mocking,
depending on which order pytest happens to collect files in.

This was fixed by having repository.py do `from app import db` and call
`db.get_client()` at call-time instead, so the monkeypatch always takes
effect regardless of import order. This test guards against that fix
being reverted.
"""


def test_fake_supabase_patch_is_effective_regardless_of_import_order(fake_supabase):
    from app import repository as repo

    village = repo.upsert_village(
        "RegressionGuardVillage", {"min_lat": 0, "min_lon": 0, "max_lat": 1, "max_lon": 1}
    )
    assert village["name"] == "RegressionGuardVillage"
    # If this ran against the REAL Supabase client instead of the fake one,
    # this test would have raised RuntimeError before reaching this line.
    assert "villages" in fake_supabase.tables