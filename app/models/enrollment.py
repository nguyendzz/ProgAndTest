from datetime import date, datetime
from typing import Optional
from app.models.semester_registration import SemesterRegistration
from app.models.waitlist import Waitlist


class Enrollment:
    VALID_STATUSES = ("Enrolled", "Dropped", "Withdrawn")
    DEFAULT_MIN_CREDITS = 14
    DEFAULT_MAX_CREDITS = 25
    HONOR_MAX_CREDITS = 30
    HONOR_GPA_THRESHOLD = 8.0

    def __init__(
        self,
        enrollment_id: Optional[int],
        student_id: str,
        section_id: str,
        enroll_date: Optional[str] = None,
        status: str = "Enrolled",
        confirmation_number: str = "",
    ):
        self._enrollmentId = enrollment_id
        self._studentId = student_id
        self._sectionId = section_id
        self._enrollDate = enroll_date
        self._status = status
        self._confirmationNumber = confirmation_number

    @property
    def enrollment_id(self) -> Optional[int]:
        return self._enrollmentId

    @property
    def student_id(self) -> str:
        return self._studentId

    @property
    def section_id(self) -> str:
        return self._sectionId

    @property
    def enroll_date(self) -> Optional[str]:
        return self._enrollDate

    @property
    def status(self) -> str:
        return self._status

    @property
    def confirmation_number(self) -> str:
        return self._confirmationNumber

    @classmethod
    def from_row(cls, row) -> Optional["Enrollment"]:
        if row is None:
            return None
        return cls(
            enrollment_id=row["EnrollmentID"],
            student_id=row["StudentID"],
            section_id=row["SectionID"],
            enroll_date=row["EnrollDate"],
            status=row["Status"],
            confirmation_number=row["ConfirmationNumber"],
        )

    @staticmethod
    def _parse_date(value: str) -> date:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()

    @classmethod
    def get_previous_semester_gpa_conn(
        cls, conn, student_id: str, current_semester: str
    ) -> float:
        rows = conn.execute(
            """
            SELECT c.Semester, g.FinalScore, s.Credits
            FROM ENROLLMENTS e
            JOIN COURSES c ON e.SectionID = c.SectionID
            JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
            JOIN GRADES g ON e.EnrollmentID = g.EnrollmentID
            WHERE e.StudentID = ?
              AND c.Semester != ?
              AND g.FinalScore IS NOT NULL
              AND g.GradeStatus = 'Final'
            ORDER BY c.Semester DESC
            """,
            (student_id, current_semester),
        ).fetchall()
        if not rows:
            return 0.0
        latest_semester = rows[0]["Semester"]
        weighted_sum = 0.0
        total_credits = 0
        for r in rows:
            if r["Semester"] != latest_semester:
                break
            credits = int(r["Credits"])
            weighted_sum += float(r["FinalScore"]) * credits
            total_credits += credits
        return round(weighted_sum / total_credits, 2) if total_credits > 0 else 0.0

    @classmethod
    def get_allowed_credit_bounds_conn(
        cls, conn, student_id: str, semester: str
    ) -> tuple[int, int]:
        period = conn.execute(
            "SELECT MinCredits, MaxCredits FROM REGISTRATION_PERIODS WHERE Semester = ?",
            (semester,),
        ).fetchone()
        min_credits = int(period["MinCredits"]) if period else cls.DEFAULT_MIN_CREDITS
        max_credits = int(period["MaxCredits"]) if period else cls.DEFAULT_MAX_CREDITS
        prev_gpa = cls.get_previous_semester_gpa_conn(conn, student_id, semester)
        if prev_gpa >= cls.HONOR_GPA_THRESHOLD:
            max_credits = max(max_credits, cls.HONOR_MAX_CREDITS)
        return min_credits, max_credits

    @classmethod
    def check_prerequisites_conn(
        cls, conn, student_id: str, subject_id: str
    ) -> tuple[bool, str]:
        sub = conn.execute(
            "SELECT PrerequisiteID FROM SUBJECTS WHERE SubjectID = ?",
            (subject_id,),
        ).fetchone()
        if not sub or not sub["PrerequisiteID"]:
            return True, ""
        prereq_id = sub["PrerequisiteID"]
        prereq_row = conn.execute(
            "SELECT SubjectName FROM SUBJECTS WHERE SubjectID = ?",
            (prereq_id,),
        ).fetchone()
        prereq_name = prereq_row["SubjectName"] if prereq_row else prereq_id
        passed = conn.execute(
            """
            SELECT 1
            FROM ENROLLMENTS e
            JOIN COURSES c ON e.SectionID = c.SectionID
            JOIN GRADES g ON e.EnrollmentID = g.EnrollmentID
            WHERE e.StudentID = ?
              AND c.SubjectID = ?
              AND g.FinalScore >= 4.0
              AND g.GradeStatus != 'W'
            LIMIT 1
            """,
            (student_id, prereq_id),
        ).fetchone()
        if not passed:
            return False, f"Prerequisite subject not completed: {prereq_id} - {prereq_name}."
        return True, ""

    @classmethod
    def check_schedule_conflict_conn(
        cls,
        conn,
        student_id: str,
        target_section,
        include_cart: bool = True,
        exclude_section_id: str = "",
    ) -> tuple[bool, Optional[str]]:
        semester = target_section["Semester"]
        day = target_section["DayOfWeek"]
        start_t = target_section["StartTime"]
        end_t = target_section["EndTime"]
        target_id = target_section["SectionID"]

        enrolled_rows = conn.execute(
            """
            SELECT c.SectionID, c.DayOfWeek, c.StartTime, c.EndTime
            FROM ENROLLMENTS e
            JOIN COURSES c ON e.SectionID = c.SectionID
            WHERE e.StudentID = ?
              AND c.Semester = ?
              AND e.Status = 'Enrolled'
            """,
            (student_id, semester),
        ).fetchall()

        existing = list(enrolled_rows)
        if include_cart:
            cart_rows = conn.execute(
                """
                SELECT c.SectionID, c.DayOfWeek, c.StartTime, c.EndTime
                FROM REGISTRATION_CART rc
                JOIN COURSES c ON rc.SectionID = c.SectionID
                WHERE rc.StudentID = ?
                  AND c.Semester = ?
                  AND rc.Status = 'InCart'
                """,
                (student_id, semester),
            ).fetchall()
            existing.extend(cart_rows)

        for other in existing:
            oid = other["SectionID"]
            if oid == target_id or oid == exclude_section_id:
                continue
            if (
                other["DayOfWeek"] == day
                and start_t < other["EndTime"]
                and end_t > other["StartTime"]
            ):
                return False, oid
        return True, None

    @classmethod
    def check_credit_limit_conn(
        cls,
        conn,
        student_id: str,
        semester: str,
        extra_credits: int = 0,
        include_cart: bool = True,
    ) -> tuple[bool, str]:
        _, max_credits = cls.get_allowed_credit_bounds_conn(conn, student_id, semester)
        enrolled_credits = SemesterRegistration.compute_enrolled_credits_conn(
            conn, student_id, semester
        )
        cart_credits = 0
        if include_cart:
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
                (student_id, semester),
            ).fetchone()
            cart_credits = int(cart_row["total"]) if cart_row else 0
        if enrolled_credits + cart_credits + extra_credits > max_credits:
            return (
                False,
                f"Total credits would exceed maximum {max_credits}.",
            )
        return True, ""

    def validateEnrollment(self, db) -> tuple[bool, str]:
        with db.connection() as conn:
            section = conn.execute(
                """
                SELECT c.*, s.Credits
                FROM COURSES c
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                WHERE c.SectionID = ?
                """,
                (self._sectionId,),
            ).fetchone()
            if not section or section["Status"] != "Open":
                return False, "Course section is not open."
            ok_pre, msg_pre = self.check_prerequisites_conn(
                conn, self._studentId, section["SubjectID"]
            )
            if not ok_pre:
                return False, msg_pre
            ok_conf, conf_sec = self.check_schedule_conflict_conn(
                conn, self._studentId, section
            )
            if not ok_conf:
                return False, f"Time conflict with existing section {conf_sec}."
            ok_cr, msg_cr = self.check_credit_limit_conn(
                conn, self._studentId, section["Semester"], int(section["Credits"])
            )
            if not ok_cr:
                return False, msg_cr
        return True, "Enrollment validation passed."

    @classmethod
    def add_section_to_cart(
        cls, db, student_id: str, section_id: str
    ) -> tuple[bool, str]:
        sec_id = section_id.strip().upper()
        with db.connection() as conn:
            section = conn.execute(
                """
                SELECT c.*, s.SubjectName, s.Credits, s.Status AS SubjectStatus
                FROM COURSES c
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                WHERE c.SectionID = ?
                """,
                (sec_id,),
            ).fetchone()
            if not section or section["Status"] != "Open":
                return False, "Course section is not available."

            period = conn.execute(
                "SELECT * FROM REGISTRATION_PERIODS WHERE Semester = ?",
                (section["Semester"],),
            ).fetchone()
            if not period or period["Status"] not in ("Open", "LateReg"):
                return False, "Registration period is not open."

            in_cart = conn.execute(
                "SELECT 1 FROM REGISTRATION_CART WHERE StudentID = ? AND SectionID = ? AND Status = 'InCart'",
                (student_id, sec_id),
            ).fetchone()
            if in_cart:
                return False, "Section is already in your registration cart."

            dup_enrolled_subject = conn.execute(
                """
                SELECT 1
                FROM ENROLLMENTS e
                JOIN COURSES c ON e.SectionID = c.SectionID
                WHERE e.StudentID = ?
                  AND c.Semester = ?
                  AND c.SubjectID = ?
                  AND e.Status = 'Enrolled'
                LIMIT 1
                """,
                (student_id, section["Semester"], section["SubjectID"]),
            ).fetchone()
            if dup_enrolled_subject:
                return False, "Already enrolled/carted another section of this subject."

            dup_cart_subject = conn.execute(
                """
                SELECT 1
                FROM REGISTRATION_CART rc
                JOIN COURSES c ON rc.SectionID = c.SectionID
                WHERE rc.StudentID = ?
                  AND c.Semester = ?
                  AND c.SubjectID = ?
                  AND rc.Status = 'InCart'
                LIMIT 1
                """,
                (student_id, section["Semester"], section["SubjectID"]),
            ).fetchone()
            if dup_cart_subject:
                return False, "Already enrolled/carted another section of this subject."

            ok_pre, msg_pre = cls.check_prerequisites_conn(
                conn, student_id, section["SubjectID"]
            )
            if not ok_pre:
                return False, msg_pre

            ok_conf, conf_sec = cls.check_schedule_conflict_conn(
                conn, student_id, section, include_cart=True
            )
            if not ok_conf:
                return False, f"Time conflict with existing section {conf_sec}."

            ok_cr, msg_cr = cls.check_credit_limit_conn(
                conn, student_id, section["Semester"], int(section["Credits"]), include_cart=True
            )
            if not ok_cr:
                return False, msg_cr

            old_row = conn.execute(
                "SELECT CartID FROM REGISTRATION_CART WHERE StudentID = ? AND SectionID = ?",
                (student_id, sec_id),
            ).fetchone()
            if old_row:
                conn.execute(
                    "UPDATE REGISTRATION_CART SET Status = 'InCart', AddedAt = CURRENT_TIMESTAMP WHERE CartID = ?",
                    (old_row["CartID"],),
                )
            else:
                conn.execute(
                    "INSERT INTO REGISTRATION_CART (StudentID, SectionID, Status) VALUES (?, ?, 'InCart')",
                    (student_id, sec_id),
                )
        return True, f"Added {sec_id} to registration cart."

    @classmethod
    def confirm_cart_checkout(cls, db, student_id: str, semester: str) -> dict:
        with db.atomic_transaction() as conn:
            period = conn.execute(
                "SELECT * FROM REGISTRATION_PERIODS WHERE Semester = ?",
                (semester,),
            ).fetchone()
            if not period or period["Status"] not in ("Open", "LateReg"):
                return {
                    "ok": False,
                    "message": "Registration period is closed.",
                    "enrolled": [],
                    "full_sections": [],
                    "failed": [],
                    "confirmation_number": "",
                }

            cart_rows = conn.execute(
                """
                SELECT rc.CartID, c.*, s.SubjectName, s.Credits
                FROM REGISTRATION_CART rc
                JOIN COURSES c ON rc.SectionID = c.SectionID
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                WHERE rc.StudentID = ?
                  AND c.Semester = ?
                  AND rc.Status = 'InCart'
                ORDER BY rc.AddedAt ASC
                """,
                (student_id, semester),
            ).fetchall()

            if not cart_rows:
                return {
                    "ok": False,
                    "message": "Registration cart is empty.",
                    "enrolled": [],
                    "full_sections": [],
                    "failed": [],
                    "confirmation_number": "",
                }

            conf_num = SemesterRegistration.generateConfirmationNumber(semester)
            enrolled_sections = []
            full_sections = []
            failed_sections = []

            for sec in cart_rows:
                sec_id = sec["SectionID"]
                if sec["Status"] != "Open":
                    failed_sections.append((sec_id, "Section is no longer open."))
                    continue

                ok_pre, msg_pre = cls.check_prerequisites_conn(
                    conn, student_id, sec["SubjectID"]
                )
                if not ok_pre:
                    failed_sections.append((sec_id, msg_pre))
                    continue

                ok_conf, conf_sec = cls.check_schedule_conflict_conn(
                    conn, student_id, sec, include_cart=False
                )
                if not ok_conf:
                    failed_sections.append((sec_id, f"Time conflict with {conf_sec}."))
                    continue

                ok_cr, msg_cr = cls.check_credit_limit_conn(
                    conn, student_id, semester, int(sec["Credits"]), include_cart=False
                )
                if not ok_cr:
                    failed_sections.append((sec_id, msg_cr))
                    continue

                dup_sub = conn.execute(
                    """
                    SELECT 1
                    FROM ENROLLMENTS e
                    JOIN COURSES c ON e.SectionID = c.SectionID
                    WHERE e.StudentID = ?
                      AND c.Semester = ?
                      AND c.SubjectID = ?
                      AND e.Status = 'Enrolled'
                    LIMIT 1
                    """,
                    (student_id, semester, sec["SubjectID"]),
                ).fetchone()
                if dup_sub:
                    failed_sections.append(
                        (sec_id, "Already enrolled in another section of this subject.")
                    )
                    continue

                enrolled_cnt = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM ENROLLMENTS WHERE SectionID = ? AND Status = 'Enrolled'",
                    (sec_id,),
                ).fetchone()["cnt"]
                if enrolled_cnt >= sec["Capacity"]:
                    full_sections.append(sec_id)
                    continue

                existing_enr = conn.execute(
                    "SELECT EnrollmentID FROM ENROLLMENTS WHERE StudentID = ? AND SectionID = ?",
                    (student_id, sec_id),
                ).fetchone()
                if existing_enr:
                    conn.execute(
                        """
                        UPDATE ENROLLMENTS
                        SET Status = 'Enrolled', EnrollDate = CURRENT_TIMESTAMP, ConfirmationNumber = ?
                        WHERE EnrollmentID = ?
                        """,
                        (conf_num, existing_enr["EnrollmentID"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO ENROLLMENTS (StudentID, SectionID, Status, ConfirmationNumber)
                        VALUES (?, ?, 'Enrolled', ?)
                        """,
                        (student_id, sec_id, conf_num),
                    )
                conn.execute(
                    "DELETE FROM REGISTRATION_CART WHERE CartID = ?",
                    (sec["CartID"],),
                )
                enrolled_sections.append(sec_id)

            final_conf = ""
            total_credits = 0
            if enrolled_sections:
                final_conf = SemesterRegistration.sync_summary_conn(
                    conn, student_id, semester, conf_num
                )
                total_credits = SemesterRegistration.compute_enrolled_credits_conn(
                    conn, student_id, semester
                )

        if not enrolled_sections:
            if full_sections:
                msg = f"Section(s) full at checkout: {', '.join(full_sections)}. You may join the waitlist."
            elif failed_sections:
                msg = "; ".join(f"{s}: {reason}" for s, reason in failed_sections)
            else:
                msg = "No sections could be enrolled."
            return {
                "ok": False,
                "message": msg,
                "enrolled": [],
                "full_sections": full_sections,
                "failed": failed_sections,
                "confirmation_number": "",
                "total_credits": 0,
            }

        extra_notes = []
        if full_sections:
            extra_notes.append(
                f"Full sections available for waitlist: {', '.join(full_sections)}"
            )
        if failed_sections:
            extra_notes.append(
                "; ".join(f"{s} ({reason})" for s, reason in failed_sections)
            )
        suffix = f" Note: {' | '.join(extra_notes)}" if extra_notes else ""
        return {
            "ok": True,
            "message": f"Registration confirmed! Receipt ID: {final_conf} ({total_credits} credits).{suffix}",
            "enrolled": enrolled_sections,
            "full_sections": full_sections,
            "failed": failed_sections,
            "confirmation_number": final_conf,
            "total_credits": total_credits,
        }

    def drop(self, db, action_date: Optional[date] = None) -> tuple[bool, str]:
        return self.drop_or_withdraw(db, self._studentId, self._sectionId, action_date)

    def withdraw(self, db, action_date: Optional[date] = None) -> tuple[bool, str]:
        return self.drop_or_withdraw(db, self._studentId, self._sectionId, action_date)

    @classmethod
    def drop_or_withdraw(
        cls,
        db,
        student_id: str,
        section_id: str,
        action_date: Optional[date] = None,
    ) -> tuple[bool, str]:
        today = action_date or date.today()
        sec_id = section_id.strip().upper()
        with db.atomic_transaction() as conn:
            row = conn.execute(
                """
                SELECT e.EnrollmentID, e.Status, c.Semester
                FROM ENROLLMENTS e
                JOIN COURSES c ON e.SectionID = c.SectionID
                WHERE e.StudentID = ? AND e.SectionID = ?
                """,
                (student_id, sec_id),
            ).fetchone()
            if not row or row["Status"] != "Enrolled":
                return False, "No active enrollment found for this section."

            period = conn.execute(
                "SELECT * FROM REGISTRATION_PERIODS WHERE Semester = ?",
                (row["Semester"],),
            ).fetchone()
            if not period:
                return False, "Registration period configuration not found."

            drop_deadline = cls._parse_date(period["DropDeadline"])
            withdraw_deadline = cls._parse_date(period["WithdrawDeadline"])
            min_credits = int(period["MinCredits"])

            if today <= drop_deadline:
                conn.execute(
                    "UPDATE ENROLLMENTS SET Status = 'Dropped' WHERE EnrollmentID = ?",
                    (row["EnrollmentID"],),
                )
                action_msg = f"Dropped {sec_id} successfully (no transcript record)."
            elif today <= withdraw_deadline:
                conn.execute(
                    "UPDATE ENROLLMENTS SET Status = 'Withdrawn' WHERE EnrollmentID = ?",
                    (row["EnrollmentID"],),
                )
                existing_grade = conn.execute(
                    "SELECT GradeID FROM GRADES WHERE EnrollmentID = ?",
                    (row["EnrollmentID"],),
                ).fetchone()
                if existing_grade:
                    conn.execute(
                        "UPDATE GRADES SET FinalScore = NULL, GradeStatus = 'W' WHERE GradeID = ?",
                        (existing_grade["GradeID"],),
                    )
                else:
                    conn.execute(
                        "INSERT INTO GRADES (EnrollmentID, GradeStatus) VALUES (?, 'W')",
                        (row["EnrollmentID"],),
                    )
                action_msg = f"Withdrawn from {sec_id} successfully (grade 'W' recorded on transcript)."
            else:
                return False, "Withdrawal deadline has passed. Course cannot be dropped."

            SemesterRegistration.sync_summary_conn(conn, student_id, row["Semester"])
            remaining_credits = SemesterRegistration.compute_enrolled_credits_conn(
                conn, student_id, row["Semester"]
            )
            Waitlist.process_next_in_queue_conn(conn, sec_id)

        if 0 < remaining_credits < min_credits:
            action_msg += f" Warning: Remaining credits ({remaining_credits}) are below minimum {min_credits}."
        return True, action_msg

    @classmethod
    def get_registration_history(
        cls, db, student_id: str, semester: str = ""
    ) -> list[dict]:
        params = [student_id]
        sem_sql = ""
        if semester.strip():
            sem_sql = "AND c.Semester = ?"
            params.append(semester.strip())
        with db.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT e.EnrollmentID,
                       e.SectionID,
                       c.SubjectID,
                       s.SubjectName,
                       s.Credits,
                       c.Semester,
                       c.DayOfWeek,
                       c.StartTime,
                       c.EndTime,
                       c.Room,
                       l.FullName AS LecturerName,
                       e.EnrollDate,
                       e.Status,
                       e.ConfirmationNumber
                FROM ENROLLMENTS e
                JOIN COURSES c ON e.SectionID = c.SectionID
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                WHERE e.StudentID = ?
                  {sem_sql}
                ORDER BY e.EnrollDate DESC, e.EnrollmentID DESC
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]
