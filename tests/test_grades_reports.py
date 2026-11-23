import re
from app.models.grade import Grade
from app.models.lecturer import Lecturer
from app.models.report_service import ReportService
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


def seed_academic_dataset(db):
    lec_user, _ = User.create(db, "gv001", "Lect1234", "Lecturer", "gv001@school.edu")
    stu_user, _ = User.create(db, "sv001", "Stud1234", "Student", "sv001@school.edu")
    User.create(db, "staff01", "Staff123", "Staff", "staff01@school.edu")

    with db.connection() as conn:
        conn.execute("INSERT INTO FACULTIES VALUES ('IT', 'Information Technology')")
        conn.execute("INSERT INTO CLASSES VALUES ('IT_01', 'IT', 'IT Cohort 01', '2026-2030')")
        conn.execute(
            "INSERT INTO LECTURERS VALUES ('GV001', ?, 'IT', 'Dr. Tran Thi My Tien', 'gv001@school.edu')",
            (lec_user.user_id,),
        )
        conn.execute(
            "INSERT INTO STUDENTS VALUES ('SV001', ?, 'IT_01', 'Nguyen Van A', '2007-04-29', 'sv001@school.edu', '0901234567', 'Active')",
            (stu_user.user_id,),
        )
        conn.execute("INSERT INTO SUBJECTS VALUES ('SE104', 'Software Engineering', 3, NULL, 'Active')")
        conn.execute("INSERT INTO SUBJECTS VALUES ('DB201', 'Database Systems', 2, NULL, 'Active')")
        conn.execute("INSERT INTO SUBJECTS VALUES ('GDTC1', 'Physical Education 1', 1, NULL, 'Active')")
        conn.execute(
            "INSERT INTO COURSES VALUES ('SE104.01', 'SE104', 'GV001', 'HK1 2026-2027', 60, 'Mon', '07:30', '10:30', 'B201', 'Open')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('DB201.01', 'DB201', 'GV001', 'HK1 2026-2027', 50, 'Wed', '13:00', '15:30', 'A105', 'Open')"
        )
        conn.execute(
            "INSERT INTO COURSES VALUES ('GDTC1.01', 'GDTC1', 'GV001', 'HK1 2026-2027', 50, 'Fri', '07:30', '09:30', 'GYM1', 'Open')"
        )
        conn.execute(
            "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES ('SV001', 'SE104.01', 'Enrolled', 'REG-2026HK1-00001')"
        )
        conn.execute(
            "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES ('SV001', 'DB201.01', 'Enrolled', 'REG-2026HK1-00002')"
        )
        conn.execute(
            "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES ('SV001', 'GDTC1.01', 'Enrolled', 'REG-2026HK1-00003')"
        )
        conn.execute(
            "INSERT INTO WAITLIST (StudentID, SectionID, QueuePosition, Status) VALUES ('SV001', 'DB201.01', 1, 'Waiting')"
        )


def test_lecturer_inherits_user_and_grade_scale_conversion(db):
    seed_academic_dataset(db)
    lec = Lecturer.find_by_id(db, "GV001")
    assert lec is not None
    assert isinstance(lec, User)
    assert len(lec.viewAssignedSections(db)) == 3

    g = Grade(None, 1, 9.0, 8.5, 8.0)
    assert g.process_score == 8.6
    assert g.calculateFinalScore() == 8.3
    assert Grade.score10_to_letter_and_gpa4(9.5) == ("A+", 4.0)
    assert Grade.score10_to_letter_and_gpa4(8.7) == ("A", 4.0)
    assert Grade.score10_to_letter_and_gpa4(8.2) == ("B+", 3.5)
    assert Grade.score10_to_letter_and_gpa4(7.5) == ("B", 3.0)
    assert Grade.score10_to_letter_and_gpa4(6.5) == ("C+", 2.5)
    assert Grade.score10_to_letter_and_gpa4(5.7) == ("C", 2.0)
    assert Grade.score10_to_letter_and_gpa4(5.2) == ("D+", 1.5)
    assert Grade.score10_to_letter_and_gpa4(4.5) == ("D", 1.0)
    assert Grade.score10_to_letter_and_gpa4(3.9) == ("F", 0.0)


def test_enter_and_compute_grades(client, db):
    seed_academic_dataset(db)
    lec = Lecturer.find_by_id(db, "GV001")

    invalid_grade, msg_invalid = lec.enterGrades(db, "SE104.01", 1, "8.0", "11.5", "7.5")
    assert invalid_grade is None
    assert "0.0 and 10.0" in msg_invalid

    partial_grade, _ = lec.enterGrades(db, "SE104.01", 1, "10.0", "7.0", "")
    assert partial_grade is not None
    assert partial_grade.grade_status == "Draft"
    assert partial_grade.final_score is None

    final_grade, _ = lec.enterGrades(db, "SE104.01", 1, "8.0", "8.0", "8.3")
    assert final_grade is not None
    assert final_grade.final_score == 8.2
    assert final_grade.letter_grade == "B+"
    assert final_grade.gpa4_score == 3.5
    assert final_grade.grade_status == "Final"

    login_as(client, "gv001", "Lect1234")
    resp = client.get("/lecturer/grades?section_id=SE104.01")
    assert resp.status_code == 200
    assert b"8.2" in resp.data
    assert b"B+" in resp.data


def test_view_academic_results_and_gpa_scale_4(client, db):
    seed_academic_dataset(db)
    lec = Lecturer.find_by_id(db, "GV001")
    lec.enterGrades(db, "SE104.01", 1, "8.0", "8.0", "8.3")
    lec.enterGrades(db, "DB201.01", 2, "7.5", "7.5", "7.5")
    lec.enterGrades(db, "GDTC1.01", 3, "5.0", "5.0", "5.0")

    results = Grade.get_student_academic_results(db, "SV001")
    assert results["cumulative_credits_passed"] == 6
    assert results["cumulative_gpa"] == 3.3
    assert results["academic_standing"] == "Good"

    login_as(client, "sv001", "Stud1234")
    page = client.get("/academic/results")
    assert page.status_code == 200
    assert b"3.30" in page.data
    assert b"B+" in page.data
    assert b"Non-GPA" in page.data


def test_view_weekly_class_schedule(client, db):
    seed_academic_dataset(db)
    login_as(client, "gv001", "Lect1234")
    lec_sched = client.get("/lecturer/schedule")
    assert lec_sched.status_code == 200
    assert b"SE104.01" in lec_sched.data

    login_as(client, "sv001", "Stud1234")
    stu_sched = client.get("/academic/schedule")
    assert stu_sched.status_code == 200
    assert b"B201" in stu_sched.data


def test_generate_and_export_reports(client, db):
    seed_academic_dataset(db)
    lec = Lecturer.find_by_id(db, "GV001")
    lec.enterGrades(db, "SE104.01", 1, "9.0", "8.5", "8.0")

    for rtype in ("student_roster", "grade_distribution", "enrollment_fill", "waitlist_metrics"):
        data = ReportService.generate_report(db, rtype)
        assert len(data["rows"]) >= 1

    login_as(client, "staff01", "Staff123")
    rep_page = client.get("/reports/?report_type=grade_distribution")
    assert rep_page.status_code == 200
    assert b"Grade Distribution by Course" in rep_page.data

    excel_resp = client.get("/reports/export/excel?report_type=enrollment_fill")
    assert excel_resp.status_code == 200
    assert excel_resp.data[:2] == b"PK"

    pdf_resp = client.get("/reports/export/pdf?report_type=student_roster")
    assert pdf_resp.status_code == 200
    assert pdf_resp.data[:4] == b"%PDF"


def test_rbac_blocks_student_from_reports_and_grade_entry(client, db):
    seed_academic_dataset(db)
    login_as(client, "sv001", "Stud1234")
    assert client.get("/reports/").status_code == 403
    assert client.get("/lecturer/grades").status_code == 403
