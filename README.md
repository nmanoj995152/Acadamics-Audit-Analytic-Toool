# Academic Audit Analytics Tool

A Streamlit application for academic record entry, class analytics, support reporting, and student performance views, backed by SQLite.

## Roles

- **Student:** sees only records linked to their verified roll or enrollment number, with performance summaries and improvement suggestions.
- **Lecturer:** sees class and subject analytics, at-risk reports, and downloadable filtered CSV reports. An administrator can separately authorize mark entry and editing.
- **Registrar:** retains the existing spreadsheet import, manual entry, record editing, deletion, options, and activity workflows.
- **Admin:** sees analytics and manages user accounts and role permissions.

Student accounts are provisioned by an administrator, not through public registration. A student account requires a verified unique identifier. Legacy records without identifiers remain unlinked and invisible to students. The parser recognizes common roll, registration, and enrollment number headers and imports the selected identifier with new records. Attendance is not currently collected.

## Setup and run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

On macOS/Linux, activate with `source .venv/bin/activate` before installing and running.

Fresh databases retain the original convenience accounts: `admin` / `admin123` and `registrar` / `registrar123`. Sign in as admin and reset these passwords in **User & permissions management** before exposing the app beyond a trusted local environment. Accounts created through admin management must use passwords of at least 10 characters. Existing SHA-256 password hashes are verified on successful login and upgraded to Argon2id.

## Database migration

Startup applies additive, idempotent SQLite changes. It adds nullable student identifiers to records and users plus a lecturer mark-edit permission flag. Existing rows, including legacy rows, are retained as-is with no identifier assigned. Student access queries require an exact matching stored identifier.

## Tests

```powershell
python -m unittest discover -s tests -v
```
