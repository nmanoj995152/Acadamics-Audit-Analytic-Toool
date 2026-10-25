import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db


class AuthenticationAndRoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "audit.db"
        self.path_patch = patch.object(db, "DB_PATH", self.database)
        self.path_patch.start()
        db.initialize_db()
        self.admin = db.authenticate_user("admin", "admin123")

    def tearDown(self):
        self.path_patch.stop()
        self.temp.cleanup()

    def test_argon2_password_hash_and_authentication(self):
        password_hash = db.hash_password("long-safe-password")
        self.assertTrue(password_hash.startswith("$argon2"))
        self.assertTrue(db.verify_password("long-safe-password", password_hash))
        self.assertFalse(db.verify_password("wrong", password_hash))

    def test_admin_can_reset_password_with_argon2(self):
        db.reset_user_password(self.admin["id"], "a-new-secure-password", actor=self.admin)
        self.assertIsNotNone(db.authenticate_user("admin", "a-new-secure-password"))
        with self.assertRaises(ValueError):
            db.reset_user_password(self.admin["id"], "short", actor=self.admin)

    def test_legacy_sha256_hash_upgrades_on_successful_login(self):
        old_hash = hashlib.sha256(b"legacy-password").hexdigest()
        with db.get_connection() as conn:
            conn.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)", ("legacy", old_hash, "registrar"))
        self.assertIsNotNone(db.authenticate_user("legacy", "legacy-password"))
        with db.get_connection() as conn:
            upgraded = conn.execute("SELECT password_hash FROM users WHERE username='legacy'").fetchone()[0]
        self.assertTrue(upgraded.startswith("$argon2"))

    def test_role_permissions_and_admin_only_user_management(self):
        self.assertTrue(db.has_permission("lecturer", "view_analytics"))
        self.assertFalse(db.has_permission("lecturer", "manage_records"))
        self.assertTrue(db.has_permission("lecturer", "manage_records", can_edit_marks=True))
        self.assertTrue(db.has_permission("registrar", "manage_records"))
        self.assertFalse(db.has_permission("student", "view_analytics"))
        with self.assertRaises(PermissionError):
            db.create_user("nope", "long-safe-password", "admin", actor={"role": "lecturer"})
        with self.assertRaises(PermissionError):
            db.create_user("no_actor", "long-safe-password", "admin")

    def test_students_require_identifier_and_users_are_created_by_admin(self):
        with self.assertRaises(ValueError):
            db.create_user("student_no_id", "long-safe-password", "student", actor=self.admin)
        student_id = db.create_user("student1", "long-safe-password", "student", student_identifier="R-001", actor=self.admin)
        self.assertGreater(student_id, 0)
        with self.assertRaises(sqlite3.IntegrityError):
            db.create_user("student2", "long-safe-password", "student", student_identifier="R-001", actor=self.admin)

    def test_permission_change_takes_effect_for_existing_session(self):
        lecturer_id = db.create_user("lecturer", "long-safe-password", "lecturer", can_edit_marks=True, actor=self.admin)
        session = db.authenticate_user("lecturer", "long-safe-password")
        db.set_user_permissions(lecturer_id, "lecturer", False, actor=self.admin)
        with self.assertRaises(PermissionError):
            db.insert_record("X", "", "", "", "Math", 1, 10, "lecturer", actor=session)

    def test_last_administrator_cannot_be_demoted(self):
        with self.assertRaises(ValueError):
            db.set_user_permissions(self.admin["id"], "lecturer", False, actor=self.admin)

    def test_student_ownership_only_returns_exactly_linked_records(self):
        # A migrated legacy row has NULL ownership and stays invisible.
        legacy_id = db.insert_record("Same Name", "A", "CSE", "1st", "Math", 70, 100, "registrar", actor={"role": "registrar"})
        db.insert_record("Same Name", "A", "CSE", "1st", "Science", 90, 100, "registrar", "R-001", actor={"role": "registrar"})
        student = {"role": "student", "student_identifier": "R-001"}
        rows = db.get_student_records(student)
        self.assertEqual([r["subject"] for r in rows], ["Science"])
        self.assertNotEqual(rows[0]["id"], legacy_id)
        self.assertEqual(db.get_student_records({"role": "student", "student_identifier": "R-002"}), [])
        with self.assertRaises(PermissionError):
            db.get_all_records(actor=student)

    def test_data_access_helpers_require_authorized_actor(self):
        with self.assertRaises(PermissionError):
            db.get_all_records()
        with self.assertRaises(PermissionError):
            db.insert_record("X", "", "", "", "Math", 1, 10, "nobody")


class AdditiveMigrationTests(unittest.TestCase):
    def test_old_schema_migrates_without_changing_legacy_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.db"
            conn = sqlite3.connect(path)
            conn.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL);
            CREATE TABLE sections(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
            CREATE TABLE branches(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
            CREATE TABLE years(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
            CREATE TABLE subjects(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
            CREATE TABLE records(id INTEGER PRIMARY KEY AUTOINCREMENT, student_name TEXT NOT NULL, section TEXT NOT NULL, branch TEXT NOT NULL, year TEXT NOT NULL, subject TEXT NOT NULL, marks_obtained REAL NOT NULL, max_marks REAL NOT NULL, entered_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, action TEXT NOT NULL, timestamp TEXT NOT NULL, details TEXT NOT NULL);
            INSERT INTO users(username,password_hash,role) VALUES('old_admin','oldhash','admin');
            INSERT INTO records(student_name,section,branch,year,subject,marks_obtained,max_marks,entered_by,created_at,updated_at) VALUES('Legacy Student','A','CSE','1st','Math',75,100,'old_admin','2025-01-01','2025-01-01');
            """)
            conn.commit()
            conn.close()
            with patch.object(db, "DB_PATH", path):
                db.initialize_db()
                db.initialize_db()  # migration is idempotent
                with db.get_connection() as migrated:
                    row = migrated.execute("SELECT id,student_name,subject,marks_obtained,student_identifier FROM records").fetchone()
                    count = migrated.execute("SELECT COUNT(*) FROM records").fetchone()[0]
                    columns = {r[1] for r in migrated.execute("PRAGMA table_info(users)")}
            self.assertEqual(count, 1)
            self.assertEqual(tuple(row)[:4], (1, "Legacy Student", "Math", 75.0))
            self.assertIsNone(row["student_identifier"])
            self.assertIn("student_identifier", columns)
            self.assertIn("can_edit_marks", columns)


if __name__ == "__main__":
    unittest.main()
