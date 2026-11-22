"""Shared data layer. Every path (A, B, C) calls these same functions."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "iam.db"


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    # mode=ro opens the database read-only, so no tool can modify data
    con = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in con.execute(sql, params)]
    finally:
        con.close()


def find_identity(name: str) -> list[dict]:
    return _rows(
        "SELECT user_id, display_name, department, status FROM identities "
        "WHERE display_name LIKE ? ORDER BY user_id LIMIT 10",
        (f"%{name}%",),
    )


def get_entitlements(user_id: str) -> list[dict]:
    return _rows(
        """SELECT ap.name AS application, e.name AS entitlement, a.native_id AS account
           FROM accounts a
           JOIN applications ap ON ap.app_id = a.app_id
           JOIN account_entitlements ae ON ae.account_id = a.account_id
           JOIN entitlements e ON e.ent_id = ae.ent_id
           WHERE a.user_id = ?
           ORDER BY ap.name, e.name""",
        (user_id,),
    )


def find_orphaned_accounts() -> list[dict]:
    return _rows(
        """SELECT a.account_id, ap.name AS application, a.native_id AS account
           FROM accounts a
           JOIN applications ap ON ap.app_id = a.app_id
           WHERE a.user_id IS NULL
           ORDER BY a.account_id"""
    )
