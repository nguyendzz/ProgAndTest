import re
from datetime import datetime
from typing import Optional
import secrets


class SemesterRegistration:
    def __init__(
        self,
        reg_id: Optional[int],
        student_id: str,
        semester: str,
        total_credits_enrolled: int = 0,
        confirmation_number: str = "",
    ):
        self._regId = reg_id
        self._studentId = student_id
        self._semester = semester
        self._totalCreditsEnrolled = total_credits_enrolled
        self._confirmationNumber = confirmation_number

    @property
    def reg_id(self) -> Optional[int]:
        return self._regId

    @property
    def student_id(self) -> str:
        return self._studentId

    @property
    def semester(self) -> str:
        return self._semester

    @property
    def total_credits_enrolled(self) -> int:
        return self._totalCreditsEnrolled

    @property
    def confirmation_number(self) -> str:
        return self._confirmationNumber

    @classmethod
    def from_row(cls, row) -> Optional["SemesterRegistration"]:
        if row is None:
            return None
        return cls(
            reg_id=row["RegID"],
            student_id=row["StudentID"],
            semester=row["Semester"],
            total_credits_enrolled=row["TotalCreditsEnrolled"],
            confirmation_number=row["ConfirmationNumber"],
        )

    @staticmethod
    def generateConfirmationNumber(semester: str) -> str:
        clean_sem = re.sub(r"[^A-Za-z0-9]", "", semester).upper()[:12]
        stamp = datetime.now().strftime("%H%M%S")
        suffix = secrets.token_hex(2).upper()
        return f"REG-{clean_sem}-{stamp}{suffix}"

    @classmethod
    def find_by_student_semester(
        cls, db, student_id: str, semester: str
    ) -> Optional["SemesterRegistration"]:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM SEMESTER_REGISTRATIONS WHERE StudentID = ? AND Semester = ?",
                (student_id, semester),
            ).fetchone()
        return cls.from_row(row)

    def getTotalCredits(self, db) -> int:
        with db.connection() as conn:
            total = self.compute_enrolled_credits_conn(
                conn, self._studentId, self._semester
            )
        self._totalCreditsEnrolled = total
        return total

    @staticmethod
    def compute_enrolled_credits_conn(conn, student_id: str, semester: str) -> int:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(s.Credits), 0) AS total_credits
            FROM ENROLLMENTS e
            JOIN COURSES c ON e.SectionID = c.SectionID
            JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
            WHERE e.StudentID = ?
              AND c.Semester = ?
              AND e.Status = 'Enrolled'
            """,
            (student_id, semester),
        ).fetchone()
        return int(row["total_credits"]) if row else 0

    @classmethod
    def sync_summary_conn(
        cls, conn, student_id: str, semester: str, confirmation_number: Optional[str] = None
    ) -> str:
        total_credits = cls.compute_enrolled_credits_conn(conn, student_id, semester)
        existing = conn.execute(
            "SELECT RegID, ConfirmationNumber FROM SEMESTER_REGISTRATIONS WHERE StudentID = ? AND Semester = ?",
            (student_id, semester),
        ).fetchone()
        conf = confirmation_number or (
            existing["ConfirmationNumber"]
            if existing
            else cls.generateConfirmationNumber(semester)
        )
        if existing:
            conn.execute(
                """
                UPDATE SEMESTER_REGISTRATIONS
                SET TotalCreditsEnrolled = ?, ConfirmationNumber = ?
                WHERE RegID = ?
                """,
                (total_credits, conf, existing["RegID"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO SEMESTER_REGISTRATIONS (
                    StudentID, Semester, TotalCreditsEnrolled, ConfirmationNumber
                )
                VALUES (?, ?, ?, ?)
                """,
                (student_id, semester, total_credits, conf),
            )
        return conf
