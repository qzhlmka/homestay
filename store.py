"""SQLite persistence for bookings.

Deliberately not in-memory: a Railway redeploy or a crash must not lose the
bookings you have already confirmed and taken deposits for.
"""

import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import config

# Blocks the calendar
BLOCKING_STATUSES = ("pending", "confirmed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id             TEXT PRIMARY KEY,
    reference      TEXT UNIQUE NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',

    check_in       TEXT NOT NULL,
    check_out      TEXT NOT NULL,
    nights         INTEGER NOT NULL,
    guests         INTEGER NOT NULL,

    total          INTEGER NOT NULL,
    deposit        INTEGER NOT NULL,
    breakdown      TEXT NOT NULL,

    guest_name     TEXT NOT NULL,
    guest_phone    TEXT NOT NULL,
    guest_email    TEXT NOT NULL DEFAULT '',
    guest_ic       TEXT NOT NULL DEFAULT '',
    guest_city     TEXT NOT NULL DEFAULT '',
    purpose        TEXT NOT NULL DEFAULT '',
    notes          TEXT NOT NULL DEFAULT '',

    created_at     TEXT NOT NULL,
    decided_at     TEXT,
    decided_by     TEXT,
    source_ip      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_bookings_dates
    ON bookings (status, check_in, check_out);

-- Dates you block by hand (maintenance, family staying over).
CREATE TABLE IF NOT EXISTS blackouts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)


def _now():
    return datetime.now(timezone.utc).isoformat()


def new_reference() -> str:
    """Short human-quotable reference, e.g. SP-7K2M."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I/O/0/1
    return "SP-" + "".join(secrets.choice(alphabet) for _ in range(4))


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------

def _pending_cutoff() -> str:
    """Pending bookings older than this have expired and no longer block."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.PENDING_HOLD_HOURS)
    return cutoff.isoformat()


def active_bookings(start: date, end: date):
    """Bookings that overlap [start, end) and currently block the calendar."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM bookings
             WHERE status IN ('pending', 'confirmed')
               AND check_in < ?
               AND check_out > ?
               AND (status = 'confirmed' OR created_at > ?)
             ORDER BY check_in
            """,
            (end.isoformat(), start.isoformat(), _pending_cutoff()),
        ).fetchall()
    return [dict(r) for r in rows]


def blackouts(start: date, end: date):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM blackouts WHERE start_date < ? AND end_date > ?",
            (end.isoformat(), start.isoformat()),
        ).fetchall()
    return [dict(r) for r in rows]


def blocked_dates(start: date, end: date) -> dict:
    """
    date -> reason, for every night that cannot be booked in [start, end).

    Only *nights* are blocked. A stay ending on the 5th leaves the 5th open,
    so a same-day changeover still works.
    """
    blocked = {}

    def mark(from_iso, to_iso, reason):
        day = date.fromisoformat(from_iso)
        last = date.fromisoformat(to_iso)
        while day < last:
            if start <= day <= end:
                blocked[day.isoformat()] = reason
            day += timedelta(days=1)

    for b in active_bookings(start, end):
        mark(b["check_in"], b["check_out"],
             "booked" if b["status"] == "confirmed" else "held")

    for b in blackouts(start, end):
        mark(b["start_date"], b["end_date"], "unavailable")

    return blocked


def is_available(check_in: date, check_out: date) -> bool:
    blocked = blocked_dates(check_in, check_out)
    day = check_in
    while day < check_out:
        if day.isoformat() in blocked:
            return False
        day += timedelta(days=1)
    return True


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------

class DatesTaken(Exception):
    """Someone else's request landed on these dates first."""


def create_booking(booking: dict) -> dict:
    """
    Insert a pending booking, re-checking availability inside the same
    transaction. Two guests submitting the same dates a millisecond apart would
    otherwise both get a pending hold on them.
    """
    booking = dict(booking)
    booking["id"] = secrets.token_urlsafe(12)
    booking["reference"] = new_reference()
    booking["status"] = "pending"
    booking["created_at"] = _now()

    columns = ", ".join(booking)
    placeholders = ", ".join("?" for _ in booking)

    conn = sqlite3.connect(config.DATABASE_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")

        clash = conn.execute(
            """
            SELECT 1 FROM bookings
             WHERE status IN ('pending', 'confirmed')
               AND check_in < ? AND check_out > ?
               AND (status = 'confirmed' OR created_at > ?)
             LIMIT 1
            """,
            (booking["check_out"], booking["check_in"], _pending_cutoff()),
        ).fetchone()
        if clash:
            conn.execute("ROLLBACK")
            raise DatesTaken()

        clash = conn.execute(
            "SELECT 1 FROM blackouts WHERE start_date < ? AND end_date > ? LIMIT 1",
            (booking["check_out"], booking["check_in"]),
        ).fetchone()
        if clash:
            conn.execute("ROLLBACK")
            raise DatesTaken()

        conn.execute(
            f"INSERT INTO bookings ({columns}) VALUES ({placeholders})",
            tuple(booking.values()),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()

    return booking


def get_booking(booking_id: str):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM bookings WHERE id = ? OR reference = ?",
            (booking_id, booking_id),
        ).fetchone()
    return dict(row) if row else None


def set_status(booking_id: str, status: str, decided_by: str = "") -> bool:
    """Returns False if the booking was already decided (double-tap guard)."""
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE bookings
               SET status = ?, decided_at = ?, decided_by = ?
             WHERE id = ? AND status = 'pending'
            """,
            (status, _now(), decided_by, booking_id),
        )
    return cur.rowcount > 0


def cancel_booking(booking_id: str, cancelled_by: str = "") -> bool:
    """
    Cancel a pending or confirmed booking, releasing its dates.

    A soft cancel, not a delete: the row stays in the CSV export so you keep
    the record of who booked and who cancelled it. Because 'cancelled' is not
    in BLOCKING_STATUSES, the dates free up and it drops off the calendar feed
    automatically.
    """
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE bookings
               SET status = 'cancelled', decided_at = ?, decided_by = ?
             WHERE id = ? AND status IN ('pending', 'confirmed')
            """,
            (_now(), cancelled_by, booking_id),
        )
    return cur.rowcount > 0


def purge_booking(booking_id: str) -> bool:
    """Delete a row outright. For clearing test data - real cancellations
    should use cancel_booking so the history survives."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM bookings WHERE id = ? OR reference = ?",
            (booking_id, booking_id),
        )
    return cur.rowcount > 0


def confirmed_bookings():
    """Everything the calendar feed should show, newest stays last."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM bookings
             WHERE status IN ('confirmed', 'pending')
               AND (status = 'confirmed' OR created_at > ?)
             ORDER BY check_in
            """,
            (_pending_cutoff(),),
        ).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    """Counts by status, for the health check."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM bookings GROUP BY status"
        ).fetchall()
    by_status = {r["status"]: r["n"] for r in rows}
    return {"total": sum(by_status.values()), **by_status}


def all_bookings():
    """Every booking ever, newest first. Used by the CSV export."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM bookings ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def add_blackout(start: date, end: date, reason: str = ""):
    with connect() as conn:
        conn.execute(
            "INSERT INTO blackouts (start_date, end_date, reason, created_at)"
            " VALUES (?, ?, ?, ?)",
            (start.isoformat(), end.isoformat(), reason, _now()),
        )
