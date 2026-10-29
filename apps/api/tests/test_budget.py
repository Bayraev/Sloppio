"""Budget invariants — the tests that must never regress."""
from __future__ import annotations

import sqlite3
import threading
from datetime import timedelta

import pytest

from app.services.budget import BudgetExceededError, BudgetService, WINDOW_24H, WINDOW_7D, iso, now_utc
from app.db import connect, apply_migrations
from tests.conftest import make_settings


def make_budget(tmp_path, limit24=7.0, limit7=50.0) -> tuple[BudgetService, sqlite3.Connection]:
    settings = make_settings(tmp_path)
    conn = connect(settings)
    apply_migrations(conn)
    return BudgetService(conn, limit24, limit7), conn


def test_daily_limit_enforced(tmp_path):
    budget, _ = make_budget(tmp_path, limit24=1.0, limit7=50.0)
    r1 = budget.reserve("g1", 0.60)
    budget.settle(r1, 0.60)
    with pytest.raises(BudgetExceededError) as exc:
        budget.reserve("g2", 0.50)
    assert exc.value.window == "24h"


def test_boundary_exact_limit_allowed_then_one_cent_rejected(tmp_path):
    budget, _ = make_budget(tmp_path, limit24=1.0, limit7=50.0)
    budget.reserve("g1", 1.0)  # exactly at the limit — allowed
    with pytest.raises(BudgetExceededError):
        budget.reserve("g2", 0.01)


def test_weekly_limit_enforced_with_rolling_charges(tmp_path):
    budget, conn = make_budget(tmp_path, limit24=100.0, limit7=10.0)
    # Charge 6 USD yesterday (inside 7d window, outside 24h).
    yesterday = iso(now_utc() - timedelta(days=1))
    conn.execute(
        "INSERT INTO budget_charges (id, generation_id, amount_usd, created_at) VALUES ('c0','g0',6.0,?)",
        (yesterday,),
    )
    conn.commit()
    # 24h window has room, but 7d does not.
    with pytest.raises(BudgetExceededError) as exc:
        budget.reserve("g1", 4.5)
    assert exc.value.window == "7d"
    # 3.5 fits (6+3.5 < 10).
    budget.reserve("g1", 3.5)


def test_old_charges_leave_rolling_window(tmp_path):
    budget, conn = make_budget(tmp_path, limit24=100.0, limit7=10.0)
    eight_days_ago = iso(now_utc() - timedelta(days=8, hours=1))
    conn.execute(
        "INSERT INTO budget_charges (id, generation_id, amount_usd, created_at) VALUES ('c0','g0',9.0,?)",
        (eight_days_ago,),
    )
    conn.commit()
    budget.reserve("g1", 9.0)  # old charge no longer blocks


def test_concurrent_reservations_cannot_exceed_limit(tmp_path):
    budget, _ = make_budget(tmp_path, limit24=10.0, limit7=50.0)
    results = []
    barrier = threading.Barrier(8)

    def worker(i):
        barrier.wait()
        try:
            rid = budget.reserve(f"g{i}", 1.5)
            results.append(("ok", rid))
        except BudgetExceededError:
            results.append(("denied", None))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = [r for r in results if r[0] == "ok"]
    denied = [r for r in results if r[0] == "denied"]
    assert len(ok) == 6, f"expected exactly 6 approvals (10/1.5), got {len(ok)}"
    assert len(denied) == 2
    snap = budget.snapshot()
    assert snap.reserved_usd == 9.0


def test_reservation_persists_across_restart(tmp_path):
    budget, conn = make_budget(tmp_path, limit24=10.0, limit7=50.0)
    budget.reserve("g1", 4.0)
    conn.close()
    # "Restart": fresh service over the same DB file.
    settings = make_settings(tmp_path)
    conn2 = connect(settings)
    budget2 = BudgetService(conn2, 10.0, 50.0)
    snap = budget2.snapshot()
    assert snap.reserved_usd == 4.0
    with pytest.raises(BudgetExceededError):
        budget2.reserve("g2", 7.0)


def test_active_reservation_blocks_both_windows(tmp_path):
    budget, conn = make_budget(tmp_path, limit24=5.0, limit7=50.0)
    # Old active reservation (created 3 days ago) still blocks the 24h window.
    three_days_ago = iso(now_utc() - timedelta(days=3))
    conn.execute(
        "INSERT INTO budget_reservations (id, generation_id, amount_usd, status, created_at)"
        " VALUES ('r_old', 'g_old', 4.5, 'active', ?)",
        (three_days_ago,),
    )
    conn.commit()
    with pytest.raises(BudgetExceededError) as exc:
        budget.reserve("g1", 1.0)
    assert exc.value.window == "24h"


def test_settle_records_actual_and_release_records_nothing(tmp_path):
    budget, conn = make_budget(tmp_path, limit24=2.0, limit7=50.0)
    r1 = budget.reserve("g1", 0.5)
    budget.settle(r1, 0.42)
    charges = conn.execute("SELECT * FROM budget_charges").fetchall()
    assert len(charges) == 1 and abs(charges[0]["amount_usd"] - 0.42) < 1e-9
    r2 = budget.reserve("g2", 0.5)
    budget.release(r2, note="terminal:failed")
    snap = budget.snapshot()
    assert snap.spend_24h_usd == 0.42
    assert snap.reserved_usd == 0.0
    with pytest.raises(ValueError):
        budget.release(r2)  # already released


def test_snapshot_remaining_accounts_for_reserved(tmp_path):
    budget, _ = make_budget(tmp_path, limit24=7.0, limit7=50.0)
    r = budget.reserve("g1", 2.0)
    snap = budget.snapshot()
    assert snap.remaining_24h_usd == 5.0
    budget.settle(r, 1.5)
    snap = budget.snapshot()
    assert snap.spend_24h_usd == 1.5
    assert snap.remaining_24h_usd == 5.5
