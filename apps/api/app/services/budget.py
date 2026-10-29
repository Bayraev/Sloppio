"""Centralized budget manager — the ONLY gate for paid generation.

Invariants (tested in tests/test_budget.py):
- Rolling windows: 24h and 7d limits enforced over confirmed charges.
- Active reservations always count against BOTH windows (conservative).
- reserve() is atomic (BEGIN IMMEDIATE + process lock) — concurrent requests cannot exceed limits.
- Unknown cost must fail closed (callers must compute an estimate first; estimate() refuses
  unpriced models).
- settle() records the actual charge; release() only on confirmed no-charge outcomes.
- Reservations persist across restarts (SQLite) — restart never releases exposure.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.db import write_tx

WINDOW_24H = timedelta(hours=24)
WINDOW_7D = timedelta(days=7)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass
class BudgetSnapshot:
    limit_24h_usd: float
    limit_7d_usd: float
    spend_24h_usd: float
    spend_7d_usd: float
    reserved_usd: float
    remaining_24h_usd: float
    remaining_7d_usd: float

    def as_dict(self) -> dict:
        return {
            "limits": {"usd_24h": self.limit_24h_usd, "usd_7d": self.limit_7d_usd},
            "spend_24h_usd": round(self.spend_24h_usd, 4),
            "spend_7d_usd": round(self.spend_7d_usd, 4),
            "reserved_usd": round(self.reserved_usd, 4),
            "remaining_24h_usd": round(self.remaining_24h_usd, 4),
            "remaining_7d_usd": round(self.remaining_7d_usd, 4),
        }


class BudgetExceededError(Exception):
    def __init__(self, window: str, limit: float, would_spend: float) -> None:
        super().__init__(
            f"Budget limit for {window} would be exceeded: ${would_spend:.2f} needed vs ${limit:.2f} limit."
        )
        self.window = window
        self.limit = limit
        self.would_spend = would_spend


class BudgetService:
    def __init__(self, conn: sqlite3.Connection, limit_24h: float, limit_7d: float) -> None:
        self.conn = conn
        self.limit_24h = round(limit_24h, 4)
        self.limit_7d = round(limit_7d, 4)

    # --- queries -----------------------------------------------------------
    def _charges_since(self, since: datetime) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_usd), 0) AS total FROM budget_charges WHERE created_at >= ?",
            (iso(since),),
        ).fetchone()
        return float(row["total"])

    def _reserved_active(self) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_usd), 0) AS total FROM budget_reservations WHERE status = 'active'"
        ).fetchone()
        return float(row["total"])

    def snapshot(self) -> BudgetSnapshot:
        now = now_utc()
        spend24 = self._charges_since(now - WINDOW_24H)
        spend7 = self._charges_since(now - WINDOW_7D)
        reserved = self._reserved_active()
        return BudgetSnapshot(
            limit_24h_usd=self.limit_24h,
            limit_7d_usd=self.limit_7d,
            spend_24h_usd=spend24,
            spend_7d_usd=spend7,
            reserved_usd=reserved,
            remaining_24h_usd=round(max(0.0, self.limit_24h - spend24 - reserved), 4),
            remaining_7d_usd=round(max(0.0, self.limit_7d - spend7 - reserved), 4),
        )

    # --- mutations ---------------------------------------------------------
    def reserve(self, generation_id: str, amount_usd: float, note: str = "") -> str:
        """Atomically check both rolling windows (charges + ALL active reservations) and reserve."""
        amount_usd = round(amount_usd, 4)
        if amount_usd <= 0:
            # Zero-cost must never silently pass: a reservation of 0 is recorded for traceability,
            # but paid flows always have a positive estimate (unknown cost fails earlier).
            amount_usd = 0.0
        now = now_utc()
        with write_tx(self.conn):
            spend24 = self._charges_since(now - WINDOW_24H)
            spend7 = self._charges_since(now - WINDOW_7D)
            reserved = self._reserved_active()
            would24 = spend24 + reserved + amount_usd
            would7 = spend7 + reserved + amount_usd
            if would24 > self.limit_24h + 1e-9:
                raise BudgetExceededError("24h", self.limit_24h, would24)
            if would7 > self.limit_7d + 1e-9:
                raise BudgetExceededError("7d", self.limit_7d, would7)
            reservation_id = f"res_{uuid.uuid4().hex[:16]}"
            self.conn.execute(
                "INSERT INTO budget_reservations (id, generation_id, amount_usd, status, note, created_at)"
                " VALUES (?, ?, ?, 'active', ?, ?)",
                (reservation_id, generation_id, amount_usd, note, iso(now)),
            )
            return reservation_id

    def settle(self, reservation_id: str, actual_usd: float) -> None:
        """Confirmed charge (success). Records the actual amount; never reduces history."""
        actual_usd = round(actual_usd, 4)
        now = iso(now_utc())
        with write_tx(self.conn):
            row = self.conn.execute(
                "SELECT status, generation_id FROM budget_reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown reservation {reservation_id}")
            if row["status"] != "active":
                raise ValueError(f"Reservation {reservation_id} already {row['status']}")
            self.conn.execute(
                "INSERT INTO budget_charges (id, generation_id, amount_usd, created_at)"
                " VALUES (?, ?, ?, ?)",
                (f"chg_{uuid.uuid4().hex[:16]}", row["generation_id"], actual_usd, now),
            )
            self.conn.execute(
                "UPDATE budget_reservations SET status = 'settled', settled_at = ? WHERE id = ?",
                (now, reservation_id),
            )

    def release(self, reservation_id: str, note: str = "") -> None:
        """Confirmed no-charge outcome (failed/expired/cancelled/pre-submission)."""
        now = iso(now_utc())
        with write_tx(self.conn):
            row = self.conn.execute(
                "SELECT status FROM budget_reservations WHERE id = ?", (reservation_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown reservation {reservation_id}")
            if row["status"] != "active":
                raise ValueError(f"Reservation {reservation_id} already {row['status']}")
            self.conn.execute(
                "UPDATE budget_reservations SET status = 'released', settled_at = ?, note = ? WHERE id = ?",
                (now, note, reservation_id),
            )

    def active_reservations(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, generation_id, amount_usd, created_at, note FROM budget_reservations"
            " WHERE status = 'active' ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_charges(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, generation_id, amount_usd, created_at FROM budget_charges"
            " ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
