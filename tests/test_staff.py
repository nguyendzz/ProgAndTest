import re
from app.models.administrative_class import AdministrativeClass
from app.models.course_section import CourseSection
from app.models.faculty import Faculty
from app.models.registration_period import RegistrationPeriod
from app.models.student_profile import StudentProfileManager
from app.models.subject import Subject
from app.models.user import User


def extract_csrf(html_bytes: bytes) -> str:
    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"', html_bytes.decode("utf-8")
    )
    assert match is not None
    return match.group(1)


def login_as(client, username: str, password: str):
    client.get("/logout")
    get_resp = client.get("/login")
    token = extract_csrf(get_resp.data)
    return client.post(
        "/login",
        data={"csrf_token": token, "username": username, "password": password},
        follow_redirects=False,
    )


def seed_staff_and_lecturer(db):
    User.create(db, "staff01", "Staff123", "Staff", "staff01@school.edu")
    lec_user, _ = User.create(db, "lec01", "Lect1234", "Lecturer", "lec01@school.edu")
    Faculty.create(db, "IT", "Information Technology")
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO LECTURERS (LecturerID, UserID, FacultyID, FullName, Email) VALUES (?, ?, ?, ?, ?)",
            ("GV001", lec_user.user_id, "IT", "Dr. Tran Thi My Tien", "lec01@school.edu"),
        )


def test_manage_classes_and_faculties(client, db):
    seed_staff_and_lecturer(db)
    login_as(client, "staff01", "Staff123")
    page = client.get("/staff/classes-faculties")
    assert page.status_code == 200
    csrf = extract_csrf(page.data)

    dup_fac = client.post(
        "/staff/faculties/create",
        data={"csrf_token": csrf, "faculty_id": "IT", "faculty_name": "Duplicate IT"},
        follow_redirects=True,
    )
    assert b"Faculty ID already exists." in dup_fac.data

    ok_cls = client.post(
        "/staff/classes/create",
        data={
            "csrf_token": extract_csrf(dup_fac.data),
            "class_id": "IT_01",
            "faculty_id": "IT",
            "class_name": "IT Cohort 01",
            "academic_year": "2026-2030",
        },
        follow_redirects=True,
    )
    assert b"Class created successfully." in ok_cls.data

    no_fac = client.post(
        "/staff/classes/create",
        data={
            "csrf_token": extract_csrf(ok_cls.data),
            "class_id": "IT_02",
            "faculty_id": "",
            "class_name": "IT Cohort 02",
            "academic_year": "2026-2030",
        },
        follow_redirects=True,
    )
    assert b"Please select a faculty." in no_fac.data


def test_subjects_and_circular_prerequisite(db):
    sub_a, _ = Subject.create(db, "IT001", "Intro Programming", 3, None)
    assert sub_a is not None
    sub_b, _ = Subject.create(db, "IT002", "Data Structures", 4, "IT001")
    assert sub_b is not None

    dup, dup_msg = Subject.create(db, "IT001", "Duplicate", 3, None)
    assert dup is None
    assert "already exists" in dup_msg

    self_ok, self_msg = Subject.update(db, "IT001", "Intro Programming", 3, "IT001")
    assert self_ok is False
    assert "circular" in self_msg.lower()

    cycle_ok, cycle_msg = Subject.update(db, "IT001", "Intro Programming", 3, "IT002")
    assert cycle_ok is False
    assert "circular" in cycle_msg.lower()


def test_student_profiles_and_deactivate(client, db):
    seed_staff_and_lecturer(db)
    AdministrativeClass.create(db, "IT_01", "IT", "IT Cohort 01", "2026-2030")
    Subject.create(db, "SE104", "Software Engineering", 4, None)
    CourseSection.open_section(
        db, "SE104.01", "SE104", "GV001", "HK1 2026-2027", 60, "Mon", "07:30", "10:30", "B201"
    )

    bad_email, msg = StudentProfileManager.create_student(
        db, "S2026001", "Nguyen Van A", "2007-04-29", "invalid-email", "0901", "IT_01"
    )
    assert bad_email is None
    assert "Invalid email format." in msg

    st1, _ = StudentProfileManager.create_student(
        db, "S2026001", "Nguyen Van A", "2007-04-29", "nva@school.edu", "0901", "IT_01"
    )
    assert st1 is not None
    linked_user = User.find_by_username(db, "S2026001")
    assert linked_user is not None and linked_user.role == "Student"

    st2, _ = StudentProfileManager.create_student(
        db, "S2026002", "Tran Thi B", "2007-05-10", "ttb@school.edu", "0902", "IT_01"
    )
    assert st2 is not None

    with db.connection() as conn:
        conn.execute(
            "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES ('S2026001', 'SE104.01', 'Enrolled', 'REG-001')"
        )

    del_blocked, del_msg = StudentProfileManager.delete_profile_if_no_history(db, "S2026001")
    assert del_blocked is False
    assert "deactivated" in del_msg.lower()

    deact_ok, _ = StudentProfileManager.deactivate_profile(db, "S2026001")
    assert deact_ok is True
    assert User.find_by_username(db, "S2026001").status == "Locked"
    with db.connection() as conn:
        enr_status = conn.execute(
            "SELECT Status FROM ENROLLMENTS WHERE StudentID = 'S2026001'"
        ).fetchone()[0]
    assert enr_status == "Dropped"

    del_ok, _ = StudentProfileManager.delete_profile_if_no_history(db, "S2026002")
    assert del_ok is True
    assert StudentProfileManager.find_by_id(db, "S2026002") is None


def test_open_course_sections_conflicts(db):
    seed_staff_and_lecturer(db)
    Subject.create(db, "SE104", "Software Engineering", 4, None)
    Subject.create(db, "OLD01", "Legacy Course", 3, None)
    Subject.set_status(db, "OLD01", "Archived")

    archived_sec, msg_arch = CourseSection.open_section(
        db, "OLD01.01", "OLD01", "GV001", "HK1 2026-2027", 50, "Tue", "07:30", "10:30", "A101"
    )
    assert archived_sec is None
    assert "Archived" in msg_arch

    bad_cap, msg_cap = CourseSection.open_section(
        db, "SE104.99", "SE104", "GV001", "HK1 2026-2027", 5, "Mon", "07:30", "10:30", "B201"
    )
    assert bad_cap is None
    assert "10 and 200" in msg_cap

    ok_sec, _ = CourseSection.open_section(
        db, "SE104.01", "SE104", "GV001", "HK1 2026-2027", 60, "Mon", "07:30", "10:30", "B201"
    )
    assert ok_sec is not None

    lec_conflict, msg_lec = CourseSection.open_section(
        db, "SE104.02", "SE104", "GV001", "HK1 2026-2027", 60, "Mon", "09:00", "11:30", "B202"
    )
    assert lec_conflict is None
    assert "Lecturer is already assigned" in msg_lec

    lec2, _ = User.create(db, "lec02", "Lect1234", "Lecturer", "lec02@school.edu")
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO LECTURERS (LecturerID, UserID, FacultyID, FullName, Email) VALUES (?, ?, ?, ?, ?)",
            ("GV002", lec2.user_id, "IT", "Dr. Nguyen", "lec02@school.edu"),
        )
    room_conflict, msg_room = CourseSection.open_section(
        db, "SE104.03", "SE104", "GV002", "HK1 2026-2027", 60, "Mon", "08:00", "10:00", "B201"
    )
    assert room_conflict is None
    assert "Room is occupied" in msg_room


def test_manage_registration_periods(db):
    bad_dates, msg_bad = RegistrationPeriod.create(
        db,
        "HK1 2026-2027",
        "2026-08-20 08:00",
        "2026-08-10 17:00",
        "2026-08-25 17:00",
        "2026-09-05",
        "2026-09-20",
    )
    assert bad_dates is None
    assert "RegOpenDate" in msg_bad

    bad_drop, msg_drop = RegistrationPeriod.create(
        db,
        "HK1 2026-2027",
        "2026-08-01 08:00",
        "2026-08-15 17:00",
        "2026-08-20 17:00",
        "2026-09-25",
        "2026-09-10",
    )
    assert bad_drop is None
    assert "DropDeadline" in msg_drop

    ok_p, _ = RegistrationPeriod.create(
        db,
        "HK1 2026-2027",
        "2026-08-01 08:00",
        "2026-08-15 17:00",
        "2026-08-20 17:00",
        "2026-09-05",
        "2026-09-20",
        14,
        25,
        "Open",
    )
    assert ok_p is not None

    dup_p, msg_dup = RegistrationPeriod.create(
        db,
        "HK1 2026-2027",
        "2026-08-01 08:00",
        "2026-08-15 17:00",
        None,
        "2026-09-05",
        "2026-09-20",
    )
    assert dup_p is None
    assert "Period already exists." in msg_dup


def test_staff_routes_rbac_blocks_student(client, db):
    User.create(db, "stu88", "StudPass1", "Student", "stu88@school.edu")
    login_as(client, "stu88", "StudPass1")
    resp = client.get("/staff/subjects")
    assert resp.status_code == 403
