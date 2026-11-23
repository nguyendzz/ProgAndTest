from datetime import date
from typing import Optional
from app.models.enrollment import Enrollment
from app.models.registration_cart import RegistrationCart
from app.models.semester_registration import SemesterRegistration
from app.models.user import User
from app.models.waitlist import Waitlist


class Student(User):
    def __init__(
        self,
        user_id: Optional[int],
        username: str,
        password_hash: str,
        role: str,
        status: str,
        email: str,
        student_id: str,
        class_id: str,
        full_name: str,
        dob: str,
        phone: str = "",
        student_status: str = "Active",
        failed_attempts: int = 0,
        locked_until: Optional[str] = None,
        reset_token: Optional[str] = None,
        reset_token_expiry: Optional[str] = None,
        session_version: int = 1,
    ):
        super().__init__(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            role=role,
            status=status,
            email=email,
            failed_attempts=failed_attempts,
            locked_until=locked_until,
            reset_token=reset_token,
            reset_token_expiry=reset_token_expiry,
            session_version=session_version,
        )
        self._studentId = student_id
        self._classId = class_id
        self._fullName = full_name
        self._dob = dob
        self._phone = phone
        self._studentStatus = student_status

    @property
    def student_id(self) -> str:
        return self._studentId

    @property
    def class_id(self) -> str:
        return self._classId

    @property
    def full_name(self) -> str:
        return self._fullName

    @property
    def dob(self) -> str:
        return self._dob

    @property
    def phone(self) -> str:
        return self._phone

    @property
    def student_status(self) -> str:
        return self._studentStatus

    def get_dashboard_endpoint(self) -> str:
        return "student.dashboard"

    @classmethod
    def _from_joined_row(cls, row) -> Optional["Student"]:
        if row is None:
            return None
        return cls(
            user_id=row["UserID"],
            username=row["Username"],
            password_hash=row["PasswordHash"],
            role=row["Role"],
            status=row["Status"],
            email=row["StudentEmail"],
            student_id=row["StudentID"],
            class_id=row["ClassID"],
            full_name=row["FullName"],
            dob=row["DOB"],
            phone=row["Phone"] or "",
            student_status=row["StudentStatus"],
            failed_attempts=row["FailedAttempts"],
            locked_until=row["LockedUntil"],
            reset_token=row["ResetToken"],
            reset_token_expiry=row["ResetTokenExpiry"],
            session_version=row["SessionVersion"],
        )

    @classmethod
    def find_by_user_id(cls, db, user_id: int) -> Optional["Student"]:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT u.*,
                       s.StudentID,
                       s.ClassID,
                       s.FullName,
                       s.DOB,
                       s.Email AS StudentEmail,
                       s.Phone,
                       s.Status AS StudentStatus
                FROM STUDENTS s
                JOIN USERS u ON s.UserID = u.UserID
                WHERE s.UserID = ?
                """,
                (user_id,),
            ).fetchone()
        return cls._from_joined_row(row)

    @classmethod
    def find_by_id(cls, db, student_id: str) -> Optional["Student"]:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT u.*,
                       s.StudentID,
                       s.ClassID,
                       s.FullName,
                       s.DOB,
                       s.Email AS StudentEmail,
                       s.Phone,
                       s.Status AS StudentStatus
                FROM STUDENTS s
                JOIN USERS u ON s.UserID = u.UserID
                WHERE s.StudentID = ?
                """,
                (student_id.strip().upper(),),
            ).fetchone()
        return cls._from_joined_row(row)

    def browseCourseCatalog(
        self,
        db,
        semester: str = "",
        search: str = "",
        faculty_id: str = "",
        day: str = "",
        available_only: bool = False,
    ) -> list[dict]:
        conditions = ["c.Status = 'Open'"]
        params = []
        if semester.strip():
            conditions.append("c.Semester = ?")
            params.append(semester.strip())
        if search.strip():
            like_val = f"%{search.strip()}%"
            conditions.append(
                "(c.SectionID LIKE ? OR c.SubjectID LIKE ? OR s.SubjectName LIKE ?)"
            )
            params.extend([like_val, like_val, like_val])
        if faculty_id.strip():
            conditions.append("l.FacultyID = ?")
            params.append(faculty_id.strip().upper())
        if day.strip():
            conditions.append("c.DayOfWeek = ?")
            params.append(day.strip())

        where_sql = f"WHERE {' AND '.join(conditions)}"
        with db.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT c.*,
                       s.SubjectName,
                       s.Credits,
                       s.PrerequisiteID,
                       l.FullName AS LecturerName,
                       l.FacultyID,
                       (SELECT COUNT(*) FROM ENROLLMENTS e
                        WHERE e.SectionID = c.SectionID AND e.Status = 'Enrolled') AS EnrolledCount
                FROM COURSES c
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                {where_sql}
                ORDER BY c.SectionID ASC
                """,
                params,
            ).fetchall()

            enrolled_ids = {
                r["SectionID"]
                for r in conn.execute(
                    "SELECT SectionID FROM ENROLLMENTS WHERE StudentID = ? AND Status = 'Enrolled'",
                    (self._studentId,),
                ).fetchall()
            }
            cart_ids = {
                r["SectionID"]
                for r in conn.execute(
                    "SELECT SectionID FROM REGISTRATION_CART WHERE StudentID = ? AND Status = 'InCart'",
                    (self._studentId,),
                ).fetchall()
            }
            waitlist_map = {
                r["SectionID"]: r["QueuePosition"]
                for r in conn.execute(
                    "SELECT SectionID, QueuePosition FROM WAITLIST WHERE StudentID = ? AND Status = 'Waiting'",
                    (self._studentId,),
                ).fetchall()
            }

            catalog = []
            for r in rows:
                remaining = max(0, int(r["Capacity"]) - int(r["EnrolledCount"]))
                if available_only and remaining <= 0:
                    continue
                prereq_ok, _ = Enrollment.check_prerequisites_conn(
                    conn, self._studentId, r["SubjectID"]
                )
                conflict_ok, conflict_sec = Enrollment.check_schedule_conflict_conn(
                    conn, self._studentId, r, include_cart=True
                )
                item = dict(r)
                item["RemainingSeats"] = remaining
                item["PrerequisiteMet"] = prereq_ok
                item["HasConflict"] = not conflict_ok
                item["ConflictSection"] = conflict_sec
                item["IsEnrolled"] = r["SectionID"] in enrolled_ids
                item["InCart"] = r["SectionID"] in cart_ids
                item["WaitlistPosition"] = waitlist_map.get(r["SectionID"])
                catalog.append(item)
        return catalog

    def addToCart(self, db, section_id: str) -> tuple[bool, str]:
        return Enrollment.add_section_to_cart(db, self._studentId, section_id)

    def removeFromCart(self, db, section_id: str) -> tuple[bool, str]:
        return RegistrationCart.remove_item(db, self._studentId, section_id)

    def confirmRegistration(self, db, semester: str) -> dict:
        return Enrollment.confirm_cart_checkout(db, self._studentId, semester)

    def joinWaitlist(self, db, section_id: str) -> tuple[Optional[Waitlist], str]:
        return Waitlist.join_waitlist(db, self._studentId, section_id)

    def dropCourse(
        self, db, section_id: str, action_date: Optional[date] = None
    ) -> tuple[bool, str]:
        return Enrollment.drop_or_withdraw(db, self._studentId, section_id, action_date)

    def getCreditSummary(self, db, semester: str) -> dict:
        with db.connection() as conn:
            min_c, max_c = Enrollment.get_allowed_credit_bounds_conn(
                conn, self._studentId, semester
            )
            enrolled_c = SemesterRegistration.compute_enrolled_credits_conn(
                conn, self._studentId, semester
            )
            cart_row = conn.execute(
                """
                SELECT COALESCE(SUM(s.Credits), 0) AS total
                FROM REGISTRATION_CART rc
                JOIN COURSES c ON rc.SectionID = c.SectionID
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                WHERE rc.StudentID = ?
                  AND c.Semester = ?
                  AND rc.Status = 'InCart'
                """,
                (self._studentId, semester),
            ).fetchone()
            cart_c = int(cart_row["total"]) if cart_row else 0
            prev_gpa = Enrollment.get_previous_semester_gpa_conn(
                conn, self._studentId, semester
            )
        return {
            "min_credits": min_c,
            "max_credits": max_c,
            "enrolled_credits": enrolled_c,
            "cart_credits": cart_c,
            "projected_credits": enrolled_c + cart_c,
            "previous_gpa": prev_gpa,
        }
