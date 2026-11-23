from typing import Optional
from app.models.grade import Grade
from app.models.user import User


class Lecturer(User):
    def __init__(
        self,
        user_id: Optional[int],
        username: str,
        password_hash: str,
        role: str,
        status: str,
        email: str,
        lecturer_id: str,
        faculty_id: str,
        full_name: str,
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
        self._lecturerId = lecturer_id
        self._facultyId = faculty_id
        self._fullName = full_name
        self._email = email

    @property
    def lecturer_id(self) -> str:
        return self._lecturerId

    @property
    def faculty_id(self) -> str:
        return self._facultyId

    @property
    def full_name(self) -> str:
        return self._fullName

    def get_dashboard_endpoint(self) -> str:
        return "lecturer.dashboard"

    @classmethod
    def _from_joined_row(cls, row) -> Optional["Lecturer"]:
        if row is None:
            return None
        return cls(
            user_id=row["UserID"],
            username=row["Username"],
            password_hash=row["PasswordHash"],
            role=row["Role"],
            status=row["Status"],
            email=row["LecturerEmail"],
            lecturer_id=row["LecturerID"],
            faculty_id=row["FacultyID"],
            full_name=row["FullName"],
            failed_attempts=row["FailedAttempts"],
            locked_until=row["LockedUntil"],
            reset_token=row["ResetToken"],
            reset_token_expiry=row["ResetTokenExpiry"],
            session_version=row["SessionVersion"],
        )

    @classmethod
    def find_by_user_id(cls, db, user_id: int) -> Optional["Lecturer"]:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT u.*, l.LecturerID, l.FacultyID, l.FullName, l.Email AS LecturerEmail
                FROM LECTURERS l
                JOIN USERS u ON l.UserID = u.UserID
                WHERE l.UserID = ?
                """,
                (user_id,),
            ).fetchone()
        return cls._from_joined_row(row)

    @classmethod
    def find_by_id(cls, db, lecturer_id: str) -> Optional["Lecturer"]:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT u.*, l.LecturerID, l.FacultyID, l.FullName, l.Email AS LecturerEmail
                FROM LECTURERS l
                JOIN USERS u ON l.UserID = u.UserID
                WHERE l.LecturerID = ?
                """,
                (lecturer_id.strip().upper(),),
            ).fetchone()
        return cls._from_joined_row(row)

    def viewAssignedSections(self, db, semester: str = "") -> list[dict]:
        params = [self._lecturerId]
        where_sem = ""
        if semester.strip():
            where_sem = "AND c.Semester = ?"
            params.append(semester.strip())
        with db.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT c.SectionID,
                       c.SubjectID,
                       s.SubjectName,
                       s.Credits,
                       c.Semester,
                       c.Capacity,
                       c.DayOfWeek,
                       c.StartTime,
                       c.EndTime,
                       c.Room,
                       c.Status,
                       (SELECT COUNT(*) FROM ENROLLMENTS e
                        WHERE e.SectionID = c.SectionID AND e.Status = 'Enrolled') AS EnrolledCount
                FROM COURSES c
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                WHERE c.LecturerID = ?
                  AND c.Status != 'Cancelled'
                  {where_sem}
                ORDER BY c.Semester DESC, c.SectionID ASC
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def getRoster(self, db, section_id: str) -> list[dict]:
        with db.connection() as conn:
            assigned = conn.execute(
                "SELECT 1 FROM COURSES WHERE SectionID = ? AND LecturerID = ?",
                (section_id, self._lecturerId),
            ).fetchone()
            if not assigned:
                return []
            rows = conn.execute(
                """
                SELECT e.EnrollmentID,
                       e.StudentID,
                       st.FullName,
                       st.ClassID,
                       e.Status AS EnrollmentStatus,
                       g.AttendanceScore,
                       g.MidtermScore,
                       g.FinalExamScore,
                       g.FinalScore,
                       g.GradeStatus
                FROM ENROLLMENTS e
                JOIN STUDENTS st ON e.StudentID = st.StudentID
                LEFT JOIN GRADES g ON e.EnrollmentID = g.EnrollmentID
                WHERE e.SectionID = ?
                  AND e.Status IN ('Enrolled', 'Withdrawn')
                ORDER BY e.StudentID ASC
                """,
                (section_id,),
            ).fetchall()
        roster = []
        for r in rows:
            item = dict(r)
            if item["EnrollmentStatus"] == "Withdrawn" or item["GradeStatus"] == "W":
                item["DisplayStatus"] = "W"
            elif item["FinalScore"] is None or item["GradeStatus"] == "Draft":
                item["DisplayStatus"] = "DRAFT"
            elif float(item["FinalScore"]) >= 4.0:
                item["DisplayStatus"] = "PASS"
            else:
                item["DisplayStatus"] = "FAIL"
            roster.append(item)
        return roster

    def enterGrades(
        self,
        db,
        section_id: str,
        enrollment_id: int,
        attendance_raw,
        midterm_raw,
        final_exam_raw,
        save_as_draft: bool = False,
    ) -> tuple[Optional[Grade], str]:
        with db.connection() as conn:
            valid_owner = conn.execute(
                """
                SELECT 1
                FROM ENROLLMENTS e
                JOIN COURSES c ON e.SectionID = c.SectionID
                WHERE e.EnrollmentID = ?
                  AND c.SectionID = ?
                  AND c.LecturerID = ?
                """,
                (enrollment_id, section_id, self._lecturerId),
            ).fetchone()
        if not valid_owner:
            return None, "Unauthorized: You are not assigned to this course section."
        return Grade.upsert_grade(
            db,
            enrollment_id,
            attendance_raw,
            midterm_raw,
            final_exam_raw,
            save_as_draft=save_as_draft,
        )
