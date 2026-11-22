import re
import sqlite3
from datetime import datetime, timedelta, timezone
import pytest
from app.models.user import User


def extract_csrf(html_bytes: bytes) -> str:
    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"', html_bytes.decode("utf-8")
    )
    assert match is not None
    return match.group(1)


def login_as(client, username: str, password: str):
    get_resp = client.get("/login")
    token = extract_csrf(get_resp.data)
    return client.post(
        "/login",
        data={"csrf_token": token, "username": username, "password": password},
        follow_redirects=False,
    )


def test_database_has_13_tables(db):
    with db.connection() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
            ).fetchall()
        }
    expected = {
        "USERS",
        "FACULTIES",
        "CLASSES",
        "STUDENTS",
        "LECTURERS",
        "SUBJECTS",
        "REGISTRATION_PERIODS",
        "COURSES",
        "ENROLLMENTS",
        "GRADES",
        "REGISTRATION_CART",
        "WAITLIST",
        "SEMESTER_REGISTRATIONS",
    }
    assert tables == expected


def test_grade_trigger_br17_and_range_br18(db):
    user_s, _ = User.create(db, "sv001", "Pass1234", "Student", "sv001@school.edu")
    user_l, _ = User.create(db, "gv001", "Pass1234", "Lecturer", "gv001@school.edu")
    with db.connection() as conn:
        conn.execute("INSERT INTO FACULTIES VALUES ('IT', 'Information Technology')")
        conn.execute("INSERT INTO CLASSES VALUES ('IT01', 'IT', 'IT_01', '2026-2030')")
        conn.execute(
            "INSERT INTO STUDENTS VALUES ('SV001', ?, 'IT01', 'Nguyen Van A', '2007-04-29', 'sv001@school.edu', '0901234567', 'Active')",
            (user_s.user_id,),
        )
        conn.execute(
            "INSERT INTO LECTURERS VALUES ('GV001', ?, 'IT', 'Dr. Tran', 'gv001@school.edu')",
            (user_l.user_id,),
        )
        conn.execute(
            "INSERT INTO SUBJECTS VALUES ('SE104', 'Software Engineering', 4, NULL, 'Active')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('SE104.01', 'SE104', 'GV001', 'HK1 2026-2027', 60, 'Mon', '07:30', '10:30', 'B201', 'Open')"
        )
        conn.execute(
            "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES ('SV001', 'SE104.01', 'Enrolled', 'REG-2026HK1-00001')"
        )
        conn.execute(
            "INSERT INTO GRADES (EnrollmentID, AttendanceScore, MidtermScore, FinalExamScore, GradeStatus) VALUES (1, 9.0, 8.5, 8.0, 'Final')"
        )
        final_score = conn.execute(
            "SELECT FinalScore FROM GRADES WHERE EnrollmentID = 1"
        ).fetchone()[0]
    assert final_score == 8.3

    with pytest.raises(sqlite3.IntegrityError):
        with db.connection() as conn:
            conn.execute("UPDATE GRADES SET MidtermScore = 11.5 WHERE EnrollmentID = 1")


def test_uc01_login_success_and_redirect(client):
    resp = login_as(client, "admin", "Admin123")
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers["Location"]


def test_uc01_br15_lock_after_5_failed_attempts(client, db):
    User.create(db, "staff01", "Staff123", "Staff", "staff01@school.edu")
    for _ in range(4):
        resp = login_as(client, "staff01", "WrongPass1")
        assert resp.status_code == 401
        assert b"Invalid username or password" in resp.data
    fifth = login_as(client, "staff01", "WrongPass1")
    assert fifth.status_code == 403
    assert b"locked for 15 minutes" in fifth.data
    still_locked = login_as(client, "staff01", "Staff123")
    assert still_locked.status_code == 403


def test_uc02_reset_password_and_expired_token(client, db):
    user, _ = User.create(db, "stu01", "OldPass1", "Student", "stu01@school.edu")
    token = user.create_reset_token(db, expiry_minutes=15)
    future_time = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        minutes=20
    )
    ok_expired, _ = user.resetPassword(db, token, "NewPass1", now=future_time)
    assert ok_expired is False
    ok_weak, _ = user.resetPassword(db, token, "123")
    assert ok_weak is False
    ok_reset, _ = user.resetPassword(db, token, "NewPass123")
    assert ok_reset is True
    resp = login_as(client, "stu01", "NewPass123")
    assert resp.status_code == 302


def test_uc03_logout_invalidates_protected_route(client):
    login_as(client, "admin", "Admin123")
    dash = client.get("/admin/dashboard")
    assert dash.status_code == 200
    out = client.get("/logout", follow_redirects=False)
    assert out.status_code == 302
    after_out = client.get("/admin/dashboard", follow_redirects=False)
    assert after_out.status_code == 302
    assert "/login" in after_out.headers["Location"]


def test_uc04_admin_manage_accounts_and_self_lock_prevention(client, db):
    login_as(client, "admin", "Admin123")
    page = client.get("/admin/accounts")
    assert page.status_code == 200
    csrf = extract_csrf(page.data)

    create_resp = client.post(
        "/admin/accounts/create",
        data={
            "csrf_token": csrf,
            "username": "lecturer01",
            "email": "lec01@school.edu",
            "password": "TempPass1",
            "role": "Lecturer",
        },
        follow_redirects=True,
    )
    assert b"User account created successfully." in create_resp.data

    dup_resp = client.post(
        "/admin/accounts/create",
        data={
            "csrf_token": extract_csrf(create_resp.data),
            "username": "lecturer01",
            "email": "other@school.edu",
            "password": "TempPass1",
            "role": "Lecturer",
        },
        follow_redirects=True,
    )
    assert b"Username already taken." in dup_resp.data

    admin_user = User.find_by_username(db, "admin")
    self_lock = client.post(
        f"/admin/accounts/{admin_user.user_id}/toggle-status",
        data={"csrf_token": extract_csrf(dup_resp.data)},
        follow_redirects=True,
    )
    assert b"Administrator cannot lock their own active account." in self_lock.data

    target = User.find_by_username(db, "lecturer01")
    lock_other = client.post(
        f"/admin/accounts/{target.user_id}/toggle-status",
        data={"csrf_token": extract_csrf(self_lock.data)},
        follow_redirects=True,
    )
    assert b"Account status updated to Locked." in lock_other.data
    client.get("/logout")
    locked_login = login_as(client, "lecturer01", "TempPass1")
    
    assert locked_login.status_code == 403
    assert b"Account locked. Contact administrator." in locked_login.data


def test_rbac_blocks_non_admin_from_admin_routes(client, db):
    User.create(db, "student99", "StudPass1", "Student", "student99@school.edu")
    login_as(client, "student99", "StudPass1")
    resp = client.get("/admin/accounts")
    assert resp.status_code == 403
