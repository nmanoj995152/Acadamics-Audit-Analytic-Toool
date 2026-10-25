"""SQLite persistence and role/ownership helpers for the audit tool."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

DB_PATH = Path(__file__).resolve().parent / "academic_audit.db"
PASSWORD_HASHER = PasswordHasher()
ROLES = {"student", "lecturer", "registrar", "admin"}
ROLE_PERMISSIONS = {
    "student": {"view_own_records"},
    "lecturer": {"view_analytics", "view_at_risk", "download_reports"},
    "registrar": {"view_analytics", "view_at_risk", "download_reports", "manage_records", "manage_options", "view_activity"},
    "admin": {"view_analytics", "view_at_risk", "download_reports", "manage_records", "manage_options", "view_activity", "manage_users"},
}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class ClosingConnection(sqlite3.Connection):
    """Use normal SQLite commit semantics and always release file handles."""
    def __exit__(self, exc_type, exc, traceback):
        try:
            return super().__exit__(exc_type, exc, traceback)
        finally:
            self.close()


def initialize_db() -> None:
    """Create missing structures and make additive, data-preserving migrations."""
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sections (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS branches (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS years (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, student_name TEXT NOT NULL, section TEXT NOT NULL,
            branch TEXT NOT NULL, year TEXT NOT NULL, subject TEXT NOT NULL,
            marks_obtained REAL NOT NULL, max_marks REAL NOT NULL, entered_by TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
            action TEXT NOT NULL, timestamp TEXT NOT NULL, details TEXT NOT NULL
        );
        """)
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "student_identifier" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN student_identifier TEXT")
        if "can_edit_marks" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN can_edit_marks INTEGER NOT NULL DEFAULT 0")
        record_columns = {row[1] for row in conn.execute("PRAGMA table_info(records)")}
        if "student_identifier" not in record_columns:
            conn.execute("ALTER TABLE records ADD COLUMN student_identifier TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_student_identifier ON users(student_identifier) WHERE student_identifier IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_student_identifier ON records(student_identifier)")
        seed_defaults(conn)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_defaults(conn: sqlite3.Connection) -> None:
    # Preserve the historic convenience accounts for a fresh database only.
    conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,?)", ("registrar", hash_password("registrar123"), "registrar"))
    conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,?)", ("admin", hash_password("admin123"), "admin"))
    for table, values in (("sections", ["A", "B", "C"]), ("branches", ["CSE", "ECE", "ME"]),
                          ("years", ["1st", "2nd", "3rd", "4th"]),
                          ("subjects", ["Data Structures", "Mathematics", "Physics", "English"])):
        conn.executemany(f"INSERT OR IGNORE INTO {table}(name) VALUES (?)", [(v,) for v in values])


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$argon2"):
        try:
            return PASSWORD_HASHER.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
    # Existing installations used SHA-256; authenticate then upgrade on login.
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == password_hash


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT id,username,role,password_hash,student_identifier,can_edit_marks FROM users WHERE username=?", (username.strip(),)).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        if not row["password_hash"].startswith("$argon2"):
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), row["id"]))
        return {"id": row["id"], "username": row["username"], "role": row["role"],
                "student_identifier": row["student_identifier"], "can_edit_marks": bool(row["can_edit_marks"])}


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """Return current account permissions for a live Streamlit session."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id,username,role,student_identifier,can_edit_marks FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        return ({"id": row["id"], "username": row["username"], "role": row["role"],
                 "student_identifier": row["student_identifier"], "can_edit_marks": bool(row["can_edit_marks"]) }
                if row else None)


def has_permission(role: str, permission: str, *, can_edit_marks: bool = False) -> bool:
    if permission == "manage_records" and role == "lecturer":
        return can_edit_marks
    if permission == "manage_options" and role == "lecturer":
        return can_edit_marks
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_permission(user: dict[str, Any], permission: str) -> None:
    role = user.get("role", "")
    edit_grant = bool(user.get("can_edit_marks"))
    # Session role data may be stale after an administrator changes an account.
    if user.get("id") is not None:
        with get_connection() as conn:
            row = conn.execute("SELECT role,can_edit_marks FROM users WHERE id=?", (user["id"],)).fetchone()
        if row is None:
            raise PermissionError("Account is no longer available")
        role, edit_grant = row["role"], bool(row["can_edit_marks"])
    if not has_permission(role, permission, can_edit_marks=edit_grant):
        raise PermissionError(f"Role is not permitted to {permission.replace('_', ' ')}")


def username_exists(username: str) -> bool:
    with get_connection() as conn:
        return conn.execute("SELECT 1 FROM users WHERE username=?", (username.strip(),)).fetchone() is not None


def create_user(username: str, password: str, role: str, *, student_identifier: str | None = None, can_edit_marks: bool = False, actor: dict[str, Any] | None = None) -> int:
    if actor is None:
        raise PermissionError("An authenticated administrator is required")
    require_permission(actor, "manage_users")
    if role not in ROLES:
        raise ValueError("Unsupported role")
    if not username.strip() or len(password) < 10:
        raise ValueError("Username is required and password must be at least 10 characters")
    identifier = (student_identifier or "").strip() or None
    if role == "student" and not identifier:
        raise ValueError("Student accounts require a verified roll or enrollment number")
    if role != "student":
        identifier = None
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO users(username,password_hash,role,student_identifier,can_edit_marks) VALUES(?,?,?,?,?)",
                           (username.strip(), hash_password(password), role, identifier, int(can_edit_marks)))
        return int(cur.lastrowid)


def list_users(actor: dict[str, Any]) -> list[dict[str, Any]]:
    require_permission(actor, "manage_users")
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT id,username,role,student_identifier,can_edit_marks FROM users ORDER BY username")]


def reset_user_password(user_id: int, password: str, actor: dict[str, Any]) -> None:
    require_permission(actor, "manage_users")
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    with get_connection() as conn:
        cursor = conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user_id))
        if cursor.rowcount == 0:
            raise ValueError("User account was not found")


def set_user_permissions(user_id: int, role: str, can_edit_marks: bool, actor: dict[str, Any]) -> None:
    require_permission(actor, "manage_users")
    if role not in ROLES:
        raise ValueError("Unsupported role")
    with get_connection() as conn:
        current = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if current is None:
            raise ValueError("User account was not found")
        if current["role"] == "admin" and role != "admin":
            remaining = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND id<>?", (user_id,)).fetchone()[0]
            if remaining == 0:
                raise ValueError("The last administrator cannot be demoted")
        conn.execute("UPDATE users SET role=?,can_edit_marks=?,student_identifier=CASE WHEN ?='student' THEN student_identifier ELSE NULL END WHERE id=?",
                     (role, int(can_edit_marks and role == "lecturer"), role, user_id))


def get_student_records(user: dict[str, Any]) -> list[dict[str, Any]]:
    require_permission(user, "view_own_records")
    identifier = user.get("student_identifier")
    if not identifier:
        return []
    with get_connection() as conn:
        rows = conn.execute("SELECT id,student_name,student_identifier,section,branch,year,subject,marks_obtained,max_marks,created_at FROM records WHERE student_identifier=? ORDER BY created_at DESC", (identifier,)).fetchall()
        return [dict(r) for r in rows]


def get_options(table_name: str) -> list[str]:
    if table_name not in {"sections", "branches", "years", "subjects"}:
        raise ValueError("Unsupported option table")
    with get_connection() as conn:
        return [r["name"] for r in conn.execute(f"SELECT name FROM {table_name} ORDER BY name")]


def add_option(table_name: str, name: str, actor: dict[str, Any] | None = None) -> None:
    if table_name not in {"sections", "branches", "years", "subjects"}:
        raise ValueError("Unsupported option table")
    if actor is None:
        raise PermissionError("An authenticated user is required")
    require_permission(actor, "manage_options")
    if name and name.strip():
        with get_connection() as conn:
            conn.execute(f"INSERT OR IGNORE INTO {table_name}(name) VALUES (?)", (name.strip(),))


def insert_record(student_name: str, section: str, branch: str, year: str, subject: str, marks_obtained: float, max_marks: float, entered_by: str, student_identifier: str | None = None, actor: dict[str, Any] | None = None) -> int:
    if actor is None:
        raise PermissionError("An authenticated user is required")
    require_permission(actor, "manage_records")
    now = _now()
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO records(student_name,section,branch,year,subject,marks_obtained,max_marks,entered_by,created_at,updated_at,student_identifier) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (student_name,section,branch,year,subject,marks_obtained,max_marks,entered_by,now,now,(student_identifier or "").strip() or None))
        return int(cur.lastrowid)


def update_record(record_id: int, student_name: str, section: str, branch: str, year: str, subject: str, marks_obtained: float, max_marks: float, actor: dict[str, Any] | None = None) -> None:
    if actor is None:
        raise PermissionError("An authenticated user is required")
    require_permission(actor, "manage_records")
    with get_connection() as conn:
        conn.execute("UPDATE records SET student_name=?,section=?,branch=?,year=?,subject=?,marks_obtained=?,max_marks=?,updated_at=? WHERE id=?",
            (student_name,section,branch,year,subject,marks_obtained,max_marks,_now(),record_id))


def get_all_records(filters: dict[str, Any] | None = None, actor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if actor is None:
        raise PermissionError("An authenticated user is required")
    require_permission(actor, "view_analytics")
    query = "SELECT id,student_name,student_identifier,section,branch,year,subject,marks_obtained,max_marks,entered_by,created_at,updated_at FROM records"
    clauses, params = [], []
    if filters:
        for field in ("student_name", "student_identifier", "section", "branch", "year", "subject"):
            value = filters.get(field)
            if value not in (None, "", "All"):
                clauses.append(f"{field}=?")
                params.append(value)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(query, params)]


def delete_record(record_id: int, actor: dict[str, Any] | None = None) -> None:
    if actor is None:
        raise PermissionError("An authenticated user is required")
    require_permission(actor, "manage_records")
    with get_connection() as conn:
        conn.execute("DELETE FROM records WHERE id=?", (record_id,))


def add_audit_log(user_id: int, action: str, details: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute("INSERT INTO audit_log(user_id,action,timestamp,details) VALUES(?,?,?,?)", (user_id,action,_now(),str(details)))


def get_recent_activity(limit: int = 10, actor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if actor is None:
        raise PermissionError("An authenticated user is required")
    require_permission(actor, "view_activity")
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT a.id,a.action,a.timestamp,a.details,u.username FROM audit_log a JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT ?", (limit,))]
