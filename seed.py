from app import create_app
from app.models.administrative_class import AdministrativeClass
from app.models.course_section import CourseSection
from app.models.faculty import Faculty
from app.models.lecturer import Lecturer
from app.models.registration_period import RegistrationPeriod
from app.models.student import Student
from app.models.student_profile import StudentProfileManager
from app.models.subject import Subject
from app.models.user import User


def seed_demo_data():
    app = create_app(init_db=True)
    db = app.extensions["db"]

    User.create(db, "staff01", "Staff123", "Staff", "staff01@school.edu")

    Faculty.create(db, "IT", "Information Technology")
    Faculty.create(db, "SE", "Software Engineering")
    AdministrativeClass.create(db, "IT_01", "IT", "Information Technology 01", "2026-2030")
    AdministrativeClass.create(db, "SE_01", "SE", "Software Engineering 01", "2026-2030")

    Lecturer.create_lecturer(db, "GV001", "Dr. Tran Thi My Tien", "gv001@school.edu", "IT")
    Lecturer.create_lecturer(db, "GV002", "Dr. Nguyen Van Minh", "gv002@school.edu", "SE")

    Subject.create(db, "IT001", "Introduction to Programming", 4, None)
    Subject.create(db, "SE104", "Software Engineering", 4, "IT001")
    Subject.create(db, "DB201", "Database Systems", 3, None)
    Subject.create(db, "NT106", "Computer Networks", 3, None)
    Subject.create(db, "ENG01", "Academic English 1", 2, None)
    Subject.create(db, "GDTC1", "Physical Education 1", 1, None)

    StudentProfileManager.create_student(
        db, "SV001", "Phan Lam Nguyen", "2007-04-29", "sv001@school.edu", "0901000001", "IT_01"
    )
    StudentProfileManager.create_student(
        db, "SV002", "Nguyen Minh Khang", "2007-06-15", "sv002@school.edu", "0901000002", "SE_01"
    )

    RegistrationPeriod.create(
        db,
        "HK1 2026-2027",
        "2026-08-01 08:00:00",
        "2026-12-30 23:59:59",
        "2027-01-05 23:59:59",
        "2027-01-15",
        "2027-01-30",
        14,
        25,
        "Open",
    )

    CourseSection.open_section(
        db, "IT001.OLD", "IT001", "GV001", "HK2 2025-2026", 60, "Mon", "07:30", "10:30", "A101"
    )
    CourseSection.update_status(db, "IT001.OLD", "Closed")
    CourseSection.open_section(
        db, "SE104.01", "SE104", "GV001", "HK1 2026-2027", 60, "Mon", "07:30", "10:30", "B201"
    )
    CourseSection.open_section(
        db, "DB201.01", "DB201", "GV001", "HK1 2026-2027", 50, "Wed", "13:00", "15:30", "A105"
    )
    CourseSection.open_section(
        db, "NT106.01", "NT106", "GV002", "HK1 2026-2027", 50, "Fri", "07:30", "10:30", "B102"
    )

    with db.connection() as conn:
        exists = conn.execute(
            "SELECT EnrollmentID FROM ENROLLMENTS WHERE StudentID = 'SV001' AND SectionID = 'IT001.OLD'"
        ).fetchone()
        if not exists:
            cur = conn.execute(
                "INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber) VALUES ('SV001', 'IT001.OLD', 'Enrolled', 'REG-SEED-001')"
            )
            enr_id = cur.lastrowid
            lec = Lecturer.find_by_id(db, "GV001")
            lec.enterGrades(db, "IT001.OLD", enr_id, "9.0", "8.5", "8.5")

    stu1 = Student.find_by_id(db, "SV001")
    if stu1:
        stu1.addToCart(db, "SE104.01")
        stu1.addToCart(db, "DB201.01")
        stu1.confirmRegistration(db, "HK1 2026-2027")

    print("Demo seed data initialized successfully.")


if __name__ == "__main__":
    seed_demo_data()
