import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import db
from auth_ui import (
    DASHBOARD_PATHS,
    DASHBOARD_TITLES,
    can_access_page,
    clear_auth_state,
    dashboard_path,
)
from streamlit.testing.v1 import AppTest

PROJECT = Path(__file__).resolve().parents[1]


class SessionNavigationTests(unittest.TestCase):
    def test_logout_clears_identity_and_login_fields(self):
        state = {
            "user": {"id": 4, "username": "admin", "role": "admin"},
            "role": "admin",
            "authenticated": True,
            "auth_user_id": 4,
            "auth_username": "admin",
            "auth_role": "admin",
            "login_username": "student1",
            "login_password": "secret",
            "_route_after_login": True,
            "_route_to_dashboard": True,
            "unrelated_preference": "compact",
        }
        clear_auth_state(state)
        for key in ("user", "role", "authenticated", "auth_user_id", "auth_username", "auth_role", "login_username", "login_password", "_route_after_login", "_route_to_dashboard"):
            self.assertNotIn(key, state)
        self.assertEqual(state["unrelated_preference"], "compact")

    def test_role_routes_open_the_matching_dashboard(self):
        self.assertEqual(dashboard_path("admin"), "pages/2_Admin.py")
        self.assertEqual(dashboard_path("registrar"), "pages/1_Registrar.py")
        self.assertEqual(dashboard_path("lecturer"), "pages/4_Lecturer.py")
        self.assertEqual(dashboard_path("student"), "pages/3_Student.py")
        with self.assertRaises(ValueError):
            dashboard_path("unknown")

    def test_sidebar_dashboard_navigation_includes_all_roles(self):
        self.assertEqual(set(DASHBOARD_PATHS), {"admin", "registrar", "lecturer", "student"})
        self.assertEqual(
            set(DASHBOARD_TITLES.values()),
            {"Admin Dashboard", "Registrar Dashboard", "Lecturer Dashboard", "Student Dashboard"},
        )
        self.assertEqual(
            {role: dashboard_path(role) for role in DASHBOARD_PATHS},
            DASHBOARD_PATHS,
        )

    def test_account_switch_does_not_reuse_previous_identity(self):
        session = {"user": {"id": 1, "username": "admin", "role": "admin"}, "role": "admin"}
        clear_auth_state(session)
        self.assertIsNone(session.get("user"))
        lecturer = {"id": 2, "username": "lecturer1", "role": "lecturer", "can_edit_marks": False}
        session["user"] = lecturer
        session["role"] = lecturer["role"]
        self.assertEqual(session["user"]["username"], "lecturer1")
        self.assertEqual(dashboard_path(session["user"]["role"]), "pages/4_Lecturer.py")
        self.assertNotEqual(session["user"]["id"], 1)

    def test_protected_pages_reject_logged_out_and_wrong_roles(self):
        self.assertFalse(can_access_page(None, "analytics"))
        self.assertFalse(can_access_page(None, "student"))
        self.assertFalse(can_access_page({"role": "student"}, "analytics"))
        self.assertFalse(can_access_page({"role": "lecturer"}, "student"))
        self.assertFalse(can_access_page({"role": "registrar"}, "analytics"))
        self.assertTrue(can_access_page({"role": "lecturer"}, "analytics"))
        self.assertTrue(can_access_page({"role": "student"}, "student"))

    def test_mark_management_requires_explicit_lecturer_grant(self):
        self.assertFalse(can_access_page({"role": "lecturer", "can_edit_marks": False}, "marks"))
        self.assertTrue(can_access_page({"role": "lecturer", "can_edit_marks": True}, "marks"))
        self.assertTrue(can_access_page({"role": "registrar"}, "marks"))


class StreamlitAccountSwitchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temp.name) / "accounts.db")
        self.db_patch.start()
        db.initialize_db()
        self.admin = db.authenticate_user("admin", "admin123")
        db.create_user("lecturer_test", "lecturer-password-1", "lecturer", actor=self.admin)
        db.create_user("student_test", "student-password-1", "student", student_identifier="ROLL-101", actor=self.admin)

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def _app(self):
        app = AppTest.from_file(str(PROJECT / "app.py"), default_timeout=10).run()
        self.assertFalse(app.exception)
        return app

    def _login(self, app, username, password):
        app.text_input(key="login_username").set_value(username)
        app.text_input(key="login_password").set_value(password)
        app.button[0].click().run()
        self.assertFalse(app.exception)

    def _logout(self, app):
        app.button(key="global_logout").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Academic Audit Analytics")
        self.assertNotIn("user", app.session_state)
        self.assertNotIn("role", app.session_state)

    def test_lecturer_logout_then_student_login_switches_identity_and_page(self):
        app = self._app()
        self._login(app, "lecturer_test", "lecturer-password-1")
        self.assertEqual(app.title[0].value, "Lecturer dashboard")
        self.assertTrue(any(button.key == "global_logout" for button in app.button))
        self._logout(app)
        self.assertEqual(app.text_input(key="login_username").value, "")
        self.assertEqual(app.text_input(key="login_password").value, "")

        self._login(app, "student_test", "student-password-1")
        self.assertEqual(app.title[0].value, "My Academic Progress")
        self.assertTrue(any(button.key == "global_logout" for button in app.button))

    def test_student_dashboard_link_does_not_grant_admin_access(self):
        app = self._app()
        self._login(app, "student_test", "student-password-1")
        app.switch_page(DASHBOARD_PATHS["admin"]).run(timeout=10)
        self.assertFalse(app.exception)
        self.assertTrue(any("not available" in warning.value for warning in app.warning))
        self.assertFalse(any(title.value == "Academic Performance Analytics" for title in app.title))
        self.assertEqual(app.session_state["user"]["role"], "student")
        app.switch_page(DASHBOARD_PATHS["student"]).run(timeout=10)
        self.assertFalse(app.exception)
        self.assertTrue(any(button.key == "global_logout" for button in app.button))

    def test_admin_and_registrar_route_to_their_own_dashboards(self):
        for username, password, expected_title in (
            ("admin", "admin123", "Academic Performance Analytics"),
            ("registrar", "registrar123", "Marks & Dataset Management"),
        ):
            with self.subTest(username=username):
                app = self._app()
                self._login(app, username, password)
                self.assertEqual(app.title[0].value, expected_title)
                self.assertTrue(any(button.key == "global_logout" for button in app.button))

    def test_logged_out_direct_access_stops_before_rendering_admin_data(self):
        app = self._app()
        app.switch_page("pages/2_Admin.py").run(timeout=10)
        self.assertFalse(app.exception)
        self.assertTrue(app.warning)
        self.assertFalse(any(title.value == "Academic Performance Analytics" for title in app.title))



if __name__ == "__main__":
    unittest.main()
