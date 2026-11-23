import re
from datetime import date
from app.models.enrollment import Enrollment
from app.models.registration_cart import RegistrationCart
from app.models.semester_registration import SemesterRegistration
from app.models.student import Student
from app.models.user import User
from app.models.waitlist import Waitlist


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


def seed_registration_dataset(db):
    lec_u, _ = User.create(db, "gv_reg", "Lect1234", "Lecturer", "gv_reg@school.edu")
    s1_u, _ = User.create(db, "sv_reg1", "Stud1234", "Student", "sv_reg1@school.edu")
    s2_u, _ = User.create(db, "sv_reg2", "Stud1234", "Student", "sv_reg2@school.edu")
    s3_u, _ = User.create(db, "sv_reg3", "Stud1234", "Student", "sv_reg3@school.edu")

    with db.connection() as conn:
        conn.execute("INSERT INTO FACULTIES VALUES ('IT', 'Information Technology')")
        conn.execute("INSERT INTO CLASSES VALUES ('IT_01', 'IT', 'IT Cohort 01', '2026-2030')")
        conn.execute(
            "INSERT INTO LECTURERS VALUES ('GV01', ?, 'IT', 'Dr. Tran', 'gv_reg@school.edu')",
            (lec_u.user_id,),
        )
        conn.execute(
            "INSERT INTO STUDENTS VALUES ('SV01', ?, 'IT_01', 'Nguyen Van A', '2007-04-29', 'sv_reg1@school.edu', '0901', 'Active')",
            (s1_u.user_id,),
        )
        conn.execute(
            "INSERT INTO STUDENTS VALUES ('SV02', ?, 'IT_01', 'Tran Thi B', '2007-05-10', 'sv_reg2@school.edu', '0902', 'Active')",
            (s2_u.user_id,),
        )
        conn.execute(
            "INSERT INTO STUDENTS VALUES ('SV03', ?, 'IT_01', 'Le Van C', '2007-06-12', 'sv_reg3@school.edu', '0903', 'Active')",
            (s3_u.user_id,),
        )
        conn.execute("INSERT INTO SUBJECTS VALUES ('IT001', 'Intro Programming', 4, NULL, 'Active')")
        conn.execute("INSERT INTO SUBJECTS VALUES ('SE104', 'Software Engineering', 4, 'IT001', 'Active')")
        conn.execute("INSERT INTO SUBJECTS VALUES ('NT106', 'Computer Networks', 4, NULL, 'Active')")
        conn.execute("INSERT INTO SUBJECTS VALUES ('DB201', 'Database Systems', 3, NULL, 'Active')")
        conn.execute("INSERT INTO SUBJECTS VALUES ('AI301', 'Machine Learning', 10, NULL, 'Active')")
        conn.execute("INSERT INTO SUBJECTS VALUES ('AI302', 'Deep Learning', 10, NULL, 'Active')")
        conn.execute("INSERT INTO SUBJECTS VALUES ('AI303', 'Robotics', 8, NULL, 'Active')")

        conn.execute(
            """
            INSERT INTO REGISTRATION_PERIODS (
                Semester, RegOpenDate, RegCloseDate, LateRegDeadline,
                DropDeadline, WithdrawDeadline, MinCredits, MaxCredits, Status
            )
            VALUES (
                'HK1 2026-2027', '2026-08-01 08:00:00', '2026-12-30 23:59:59',
                '2027-01-05 23:59:59', '2027-01-15', '2027-01-30', 14, 25, 'Open'
            )
            """
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('IT001.OLD', 'IT001', 'GV01', 'HK2 2025-2026', 60, 'Mon', '07:30', '10:30', 'A101', 'Closed')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('SE104.01', 'SE104', 'GV01', 'HK1 2026-2027', 60, 'Mon', '07:30', '10:30', 'B201', 'Open')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('SE104.02', 'SE104', 'GV01', 'HK1 2026-2027', 60, 'Tue', '07:30', '10:30', 'B202', 'Open')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('NT106.01', 'NT106', 'GV01', 'HK1 2026-2027', 60, 'Mon', '08:30', '11:00', 'B102', 'Open')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('DB201.01', 'DB201', 'GV01', 'HK1 2026-2027', 10, 'Wed', '13:00', '15:30', 'A105', 'Open')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('DB201.02', 'DB201', 'GV01', 'HK1 2026-2027', 10, 'Thu', '13:00', '15:30', 'A106', 'Open')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('AI301.01', 'AI301', 'GV01', 'HK1 2026-2027', 40, 'Tue', '13:00', '16:00', 'C101', 'Open')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('AI302.01', 'AI302', 'GV01', 'HK1 2026-2027', 40, 'Thu', '07:30', '10:30', 'C102', 'Open')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('AI303.01', 'AI303', 'GV01', 'HK1 2026-2027', 40, 'Fri', '07:30', '10:30', 'C103', 'Open')"
        )

        conn.execute(
            "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES ('SV01', 'IT001.OLD', 'Enrolled', 'REG-OLD-01')"
        )
        conn.execute(
            "INSERT INTO GRADES (EnrollmentID, AttendanceScore, MidtermScore, FinalExamScore, GradeStatus) VALUES (1, 9.0, 8.5, 8.5, 'Final')"
        )
        conn.execute(
            "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES ('SV02', 'IT001.OLD', 'Enrolled', 'REG-OLD-02')"
        )
        conn.execute(
            "INSERT INTO GRADES (EnrollmentID, AttendanceScore, MidtermScore, FinalExamScore, GradeStatus) VALUES (2, 3.0, 3.5, 3.0, 'Final')"
        )


def test_student_inherits_user_and_browse_catalog(client, db):
    seed_registration_dataset(db)
    stu = Student.find_by_id(db, "SV01")
    assert stu is not None
    assert isinstance(stu, User)

    catalog = stu.browseCourseCatalog(db, semester="HK1 2026-2027", search="SE104")
    assert len(catalog) == 2
    assert catalog[0]["PrerequisiteMet"] is True

    stu2 = Student.find_by_id(db, "SV02")
    catalog2 = stu2.browseCourseCatalog(db, semester="HK1 2026-2027", search="SE104")
    assert catalog2[0]["PrerequisiteMet"] is False

    login_as(client, "sv_reg1", "Stud1234")
    resp = client.get("/student/dashboard")
    assert resp.status_code == 200
    assert b"SE104.01" in resp.data


def test_cart_prerequisite_conflict_duplicate_and_credit_limits(db):
    seed_registration_dataset(db)
    stu1 = Student.find_by_id(db, "SV01")
    stu2 = Student.find_by_id(db, "SV02")

    ok_pre, msg_pre = stu2.addToCart(db, "SE104.01")
    assert ok_pre is False
    assert "Prerequisite" in msg_pre

    ok_add, _ = stu1.addToCart(db, "SE104.01")
    assert ok_add is True

    ok_dup_sub, msg_dup = stu1.addToCart(db, "SE104.02")
    assert ok_dup_sub is False
    assert "another section of this subject" in msg_dup

    ok_conf, msg_conf = stu1.addToCart(db, "NT106.01")
    assert ok_conf is False
    assert "Time conflict" in msg_conf

    assert stu1.addToCart(db, "AI301.01")[0] is True
    assert stu1.addToCart(db, "AI302.01")[0] is True
    assert stu1.addToCart(db, "AI303.01")[0] is False

    assert stu2.addToCart(db, "AI301.01")[0] is True
    assert stu2.addToCart(db, "AI302.01")[0] is True
    ok_limit_25, msg_limit = stu2.addToCart(db, "AI303.01")
    assert ok_limit_25 is False
    assert "25" in msg_limit


def test_atomic_checkout_and_full_section_partial_success(db):
    seed_registration_dataset(db)
    stu1 = Student.find_by_id(db, "SV01")
    assert stu1.addToCart(db, "SE104.01")[0] is True
    assert stu1.addToCart(db, "DB201.01")[0] is True

    fill_users = [
        User.create(db, f"fill{i}", "Pass1234", "Student", f"fill{i}@school.edu")[0]
        for i in range(10)
    ]
    with db.connection() as conn:
        for i, u in enumerate(fill_users):
            conn.execute(
                "INSERT INTO STUDENTS VALUES (?, ?, 'IT_01', ?, '2007-01-01', ?, '09', 'Active')",
                (f"FILL{i:02d}", u.user_id, f"Fill {i}", f"fill{i}@school.edu"),
            )
            conn.execute(
                "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES (?, 'DB201.01', 'Enrolled', ?)",
                (f"FILL{i:02d}", f"REG-F-{i}"),
            )

    res = stu1.confirmRegistration(db, "HK1 2026-2027")
    assert res["ok"] is True
    assert "SE104.01" in res["enrolled"]
    assert "DB201.01" in res["full_sections"]
    assert res["confirmation_number"].startswith("REG-")
    sem_reg = SemesterRegistration.find_by_student_semester(db, "SV01", "HK1 2026-2027")
    assert sem_reg is not None
    assert sem_reg.total_credits_enrolled == 4
    remaining_cart = RegistrationCart.get_items(db, "SV01", "HK1 2026-2027")
    assert len(remaining_cart) == 1
    assert remaining_cart[0]["SectionID"] == "DB201.01"


def test_fifo_waitlist_capacity_and_auto_promotion(db):
    seed_registration_dataset(db)
    cap_users = [
        User.create(db, f"cap{i}", "Pass1234", "Student", f"cap{i}@school.edu")[0]
        for i in range(10)
    ]
    with db.connection() as conn:
        for i, u in enumerate(cap_users):
            conn.execute(
                "INSERT INTO STUDENTS VALUES (?, ?, 'IT_01', ?, '2007-01-01', ?, '09', 'Active')",
                (f"CAP{i:02d}", u.user_id, f"Cap {i}", f"cap{i}@school.edu"),
            )
            conn.execute(
                "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES (?, 'DB201.01', 'Enrolled', ?)",
                (f"CAP{i:02d}", f"REG-C1-{i}"),
            )
            conn.execute(
                "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES (?, 'DB201.02', 'Enrolled', ?)",
                (f"CAP{i:02d}", f"REG-C2-{i}"),
            )

    stu1 = Student.find_by_id(db, "SV01")
    stu2 = Student.find_by_id(db, "SV02")

    wl1, _ = stu1.joinWaitlist(db, "DB201.01")
    assert wl1 is not None and wl1.queue_position == 1
    wl1_alt, _ = stu1.joinWaitlist(db, "DB201.02")
    assert wl1_alt is not None and wl1_alt.queue_position == 1
    wl2, _ = stu2.joinWaitlist(db, "DB201.01")
    assert wl2 is not None and wl2.queue_position == 2

    cap0 = Student.find_by_id(db, "CAP00")
    ok_drop, _ = cap0.dropCourse(db, "DB201.01", action_date=date(2027, 1, 10))
    assert ok_drop is True

    history_s1 = Enrollment.get_registration_history(db, "SV01", "HK1 2026-2027")
    assert any(h["SectionID"] == "DB201.01" and h["Status"] == "Enrolled" for h in history_s1)

    wls_s1 = Waitlist.get_student_waitlists(db, "SV01", "HK1 2026-2027")
    status_by_sec = {w["SectionID"]: w["Status"] for w in wls_s1}
    assert status_by_sec["DB201.01"] == "Enrolled"
    assert status_by_sec["DB201.02"] == "Cancelled"


def test_drop_withdraw_and_after_deadline(client, db):
    seed_registration_dataset(db)
    stu1 = Student.find_by_id(db, "SV01")
    stu1.addToCart(db, "SE104.01")
    stu1.addToCart(db, "DB201.01")
    stu1.addToCart(db, "AI301.01")
    res = stu1.confirmRegistration(db, "HK1 2026-2027")
    assert res["ok"] is True

    ok_drop, msg_drop = stu1.dropCourse(db, "DB201.01", action_date=date(2027, 1, 10))
    assert ok_drop is True
    assert "no transcript" in msg_drop.lower()

    ok_withdraw, msg_w = stu1.dropCourse(db, "SE104.01", action_date=date(2027, 1, 20))
    assert ok_withdraw is True
    assert "'W'" in msg_w
    with db.connection() as conn:
        g_status = conn.execute(
            """
            SELECT g.GradeStatus
            FROM GRADES g
            JOIN ENROLLMENTS e ON g.EnrollmentID = e.EnrollmentID
            WHERE e.StudentID = 'SV01' AND e.SectionID = 'SE104.01'
            """
        ).fetchone()[0]
    assert g_status == "W"

    ok_late, msg_late = stu1.dropCourse(db, "AI301.01", action_date=date(2027, 2, 5))
    assert ok_late is False
    assert "deadline has passed" in msg_late.lower()

    login_as(client, "sv_reg1", "Stud1234")
    hist_page = client.get("/student/history")
    assert hist_page.status_code == 200
    assert b"SE104.01" in hist_page.data


def test_rbac_blocks_non_student_from_registration_portal(client, db):
    seed_registration_dataset(db)
    login_as(client, "gv_reg", "Lect1234")
    assert client.get("/student/dashboard").status_code == 403
    assert client.get("/student/history").status_code == 403
