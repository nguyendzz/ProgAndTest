from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
class Grade:
    VALID_STATUSES = ("Draft", "Final", "W")

    def __init__(
        self,
        grade_id: Optional[int],
        enrollment_id: int,
        attendance_score: Optional[float] = None,
        midterm_score: Optional[float] = None,
        final_exam_score: Optional[float] = None,
        final_score: Optional[float] = None,
        grade_status: str = "Draft",
    ):
        self._gradeId = grade_id
        self._enrollmentId = enrollment_id
        self._attendanceScore = attendance_score
        self._midtermScore = midterm_score
        self._finalExamScore = final_exam_score
        self._finalScore = final_score
        self._gradeStatus = grade_status

    @property
    def grade_id(self) -> Optional[int]:
        return self._gradeId

    @property
    def enrollment_id(self) -> int:
        return self._enrollmentId

    @property
    def attendance_score(self) -> Optional[float]:
        return self._attendanceScore

    @property
    def midterm_score(self) -> Optional[float]:
        return self._midtermScore

    @property
    def final_exam_score(self) -> Optional[float]:
        return self._finalExamScore

    @property
    def final_score(self) -> Optional[float]:
        return self._finalScore

    @property
    def grade_status(self) -> str:
        return self._gradeStatus

    @staticmethod
    def parse_score(raw_value) -> tuple[bool, Optional[float], str]:
        if raw_value is None or str(raw_value).strip() == "":
            return True, None, ""
        try:
            val = float(str(raw_value).strip())
        except ValueError:
            return False, None, "Score must be a valid number between 0.0 and 10.0."
        if val < 0.0 or val > 10.0:
            return False, None, "Score must be between 0.0 and 10.0."
        return True, round(val, 1), ""

    def calculateFinalScore(self) -> Optional[float]:
        if self._gradeStatus == "W":
            return None
        if (
            self._attendanceScore is None
            or self._midtermScore is None
            or self._finalExamScore is None
        ):
            self._finalScore = None
            return None
        raw = (
            Decimal("0.10") * Decimal(str(self._attendanceScore))
            + Decimal("0.30") * Decimal(str(self._midtermScore))
            + Decimal("0.60") * Decimal(str(self._finalExamScore))
        )
        computed = float(raw.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        self._finalScore = computed
        return computed

    @classmethod
    def from_row(cls, row) -> Optional["Grade"]:
        if row is None:
            return None
        return cls(
            grade_id=row["GradeID"],
            enrollment_id=row["EnrollmentID"],
            attendance_score=row["AttendanceScore"],
            midterm_score=row["MidtermScore"],
            final_exam_score=row["FinalExamScore"],
            final_score=row["FinalScore"],
            grade_status=row["GradeStatus"],
        )

    @classmethod
    def find_by_enrollment(cls, db, enrollment_id: int) -> Optional["Grade"]:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM GRADES WHERE EnrollmentID = ?", (enrollment_id,)
            ).fetchone()
        return cls.from_row(row)

    @classmethod
    def upsert_grade(
        cls,
        db,
        enrollment_id: int,
        attendance_raw,
        midterm_raw,
        final_exam_raw,
        save_as_draft: bool = False,
    ) -> tuple[Optional["Grade"], str]:
        ok_a, att, msg_a = cls.parse_score(attendance_raw)
        if not ok_a:
            return None, f"Attendance: {msg_a}"
        ok_m, mid, msg_m = cls.parse_score(midterm_raw)
        if not ok_m:
            return None, f"Midterm: {msg_m}"
        ok_f, fin, msg_f = cls.parse_score(final_exam_raw)
        if not ok_f:
            return None, f"Final Exam: {msg_f}"

        with db.connection() as conn:
            enr = conn.execute(
                "SELECT EnrollmentID, Status FROM ENROLLMENTS WHERE EnrollmentID = ?",
                (enrollment_id,),
            ).fetchone()
            if not enr:
                return None, "Enrollment record not found."
            if enr["Status"] == "Withdrawn":
                return None, "Cannot modify grade of a withdrawn course ('W')."

            grade_obj = cls(
                grade_id=None,
                enrollment_id=enrollment_id,
                attendance_score=att,
                midterm_score=mid,
                final_exam_score=fin,
                grade_status="Draft",
            )
            final_score = grade_obj.calculateFinalScore()
            if save_as_draft or final_score is None:
                status = "Draft"
                stored_final = None if save_as_draft else final_score
            else:
                status = "Final"
                stored_final = final_score

            existing = conn.execute(
                "SELECT GradeID FROM GRADES WHERE EnrollmentID = ?", (enrollment_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE GRADES
                    SET AttendanceScore = ?,
                        MidtermScore = ?,
                        FinalExamScore = ?,
                        FinalScore = ?,
                        GradeStatus = ?
                    WHERE EnrollmentID = ?
                    """,
                    (att, mid, fin, stored_final, status, enrollment_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO GRADES (
                        EnrollmentID, AttendanceScore, MidtermScore,
                        FinalExamScore, FinalScore, GradeStatus
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (enrollment_id, att, mid, fin, stored_final, status),
                )
            row = conn.execute(
                "SELECT * FROM GRADES WHERE EnrollmentID = ?", (enrollment_id,)
            ).fetchone()
        return cls.from_row(row), "Grades saved successfully."

    @staticmethod
    def classify_academic_standing(gpa: float) -> str:
        if gpa >= 8.5:
            return "Excellent"
        if gpa >= 7.0:
            return "Good"
        if gpa >= 5.5:
            return "Average"
        if gpa >= 4.0:
            return "Below Average"
        return "Poor"

    @classmethod
    def get_student_academic_results(cls, db, student_id: str) -> dict:
        with db.connection() as conn:
            rows = conn.execute(
                """
                SELECT c.Semester,
                       c.SectionID,
                       s.SubjectID,
                       s.SubjectName,
                       s.Credits,
                       e.Status AS EnrollmentStatus,
                       g.AttendanceScore,
                       g.MidtermScore,
                       g.FinalExamScore,
                       g.FinalScore,
                       g.GradeStatus
                FROM ENROLLMENTS e
                JOIN COURSES c ON e.SectionID = c.SectionID
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                LEFT JOIN GRADES g ON e.EnrollmentID = g.EnrollmentID
                WHERE e.StudentID = ?
                  AND e.Status IN ('Enrolled', 'Withdrawn')
                ORDER BY c.Semester ASC, s.SubjectID ASC
                """,
                (student_id,),
            ).fetchall()

        semesters_map = {}
        cum_weighted_sum = 0.0
        cum_gpa_credits = 0
        cum_credits_passed = 0

        for r in rows:
            sem = r["Semester"]
            if sem not in semesters_map:
                semesters_map[sem] = {
                    "semester": sem,
                    "courses": [],
                    "credits_passed": 0,
                    "weighted_sum": 0.0,
                    "gpa_credits": 0,
                    "semester_gpa": 0.0,
                }
            grade_status = r["GradeStatus"]
            final_score = r["FinalScore"]
            if r["EnrollmentStatus"] == "Withdrawn" or grade_status == "W":
                result_label = "W"
            elif final_score is None or grade_status == "Draft":
                result_label = "Pending"
            elif float(final_score) >= 4.0:
                result_label = "Pass"
            else:
                result_label = "Fail"

            credits = int(r["Credits"])
            if result_label in ("Pass", "Fail") and final_score is not None:
                score_val = float(final_score)
                semesters_map[sem]["weighted_sum"] += score_val * credits
                semesters_map[sem]["gpa_credits"] += credits
                cum_weighted_sum += score_val * credits
                cum_gpa_credits += credits
                if result_label == "Pass":
                    semesters_map[sem]["credits_passed"] += credits
                    cum_credits_passed += credits

            semesters_map[sem]["courses"].append(
                {
                    "section_id": r["SectionID"],
                    "subject_id": r["SubjectID"],
                    "subject_name": r["SubjectName"],
                    "credits": credits,
                    "attendance": r["AttendanceScore"],
                    "midterm": r["MidtermScore"],
                    "final_exam": r["FinalExamScore"],
                    "final_score": final_score if result_label in ("Pass", "Fail") else None,
                    "status": result_label,
                }
            )

        semesters = []
        for sem_data in semesters_map.values():
            if sem_data["gpa_credits"] > 0:
                sem_data["semester_gpa"] = round(
                    sem_data["weighted_sum"] / sem_data["gpa_credits"], 2
                )
            semesters.append(sem_data)

        cumulative_gpa = (
            round(cum_weighted_sum / cum_gpa_credits, 2) if cum_gpa_credits > 0 else 0.0
        )
        standing = (
            cls.classify_academic_standing(cumulative_gpa)
            if cum_gpa_credits > 0
            else "No Grades Yet"
        )
        return {
            "semesters": semesters,
            "cumulative_credits_passed": cum_credits_passed,
            "cumulative_gpa": cumulative_gpa,
            "academic_standing": standing,
        }
