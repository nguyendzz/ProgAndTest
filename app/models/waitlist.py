from typing import Optional
from app.models.semester_registration import SemesterRegistration


class Waitlist:
    VALID_STATUSES = ("Waiting", "Enrolled", "Skipped", "Cancelled")
    WAITLIST_CAPACITY_RATIO = 0.50

    def __init__(
        self,
        waitlist_id: Optional[int],
        student_id: str,
        section_id: str,
        queue_position: int,
        joined_at: Optional[str] = None,
        status: str = "Waiting",
    ):
        self._waitlistId = waitlist_id
        self._studentId = student_id
        self._sectionId = section_id
        self._queuePosition = queue_position
        self._joinedAt = joined_at
        self._status = status

    @property
    def waitlist_id(self) -> Optional[int]:
        return self._waitlistId

    @property
    def student_id(self) -> str:
        return self._studentId

    @property
    def section_id(self) -> str:
        return self._sectionId

    @property
    def queue_position(self) -> int:
        return self._queuePosition

    @property
    def joined_at(self) -> Optional[str]:
        return self._joinedAt

    @property
    def status(self) -> str:
        return self._status

    @classmethod
    def from_row(cls, row) -> Optional["Waitlist"]:
        if row is None:
            return None
        return cls(
            waitlist_id=row["WaitlistID"],
            student_id=row["StudentID"],
            section_id=row["SectionID"],
            queue_position=row["QueuePosition"],
            joined_at=row["JoinedAt"],
            status=row["Status"],
        )

    @classmethod
    def get_student_waitlists(cls, db, student_id: str, semester: str = "") -> list[dict]:
        params = [student_id]
        sem_sql = ""
        if semester.strip():
            sem_sql = "AND c.Semester = ?"
            params.append(semester.strip())
        with db.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT w.WaitlistID,
                       w.StudentID,
                       w.SectionID,
                       w.QueuePosition,
                       w.JoinedAt,
                       w.Status,
                       c.SubjectID,
                       s.SubjectName,
                       s.Credits,
                       c.Semester,
                       c.DayOfWeek,
                       c.StartTime,
                       c.EndTime,
                       c.Room
                FROM WAITLIST w
                JOIN COURSES c ON w.SectionID = c.SectionID
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                WHERE w.StudentID = ?
                  {sem_sql}
                ORDER BY w.JoinedAt DESC
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    @classmethod
    def join_waitlist(
        cls, db, student_id: str, section_id: str
    ) -> tuple[Optional["Waitlist"], str]:
        from app.models.enrollment import Enrollment

        sec_id = section_id.strip().upper()
        with db.atomic_transaction() as conn:
            section = conn.execute(
                """
                SELECT c.*, s.SubjectName, s.Credits, s.PrerequisiteID
                FROM COURSES c
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                WHERE c.SectionID = ?
                """,
                (sec_id,),
            ).fetchone()
            if not section or section["Status"] != "Open":
                return None, "Course section is not available."

            period = conn.execute(
                "SELECT * FROM REGISTRATION_PERIODS WHERE Semester = ?",
                (section["Semester"],),
            ).fetchone()
            if not period or period["Status"] not in ("Open", "LateReg"):
                return None, "Registration period is closed."

            enrolled_cnt = conn.execute(
                "SELECT COUNT(*) AS cnt FROM ENROLLMENTS WHERE SectionID = ? AND Status = 'Enrolled'",
                (sec_id,),
            ).fetchone()["cnt"]
            if enrolled_cnt < section["Capacity"]:
                return None, "Section still has available seats. Please add it to your cart."

            dup_subject = conn.execute(
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
            if dup_subject:
                return None, "Already enrolled in another section of this subject."

            existing_wait = conn.execute(
                "SELECT WaitlistID, Status FROM WAITLIST WHERE StudentID = ? AND SectionID = ?",
                (student_id, sec_id),
            ).fetchone()
            if existing_wait and existing_wait["Status"] == "Waiting":
                return None, "Already queued on the waitlist for this section."

            prereq_ok, prereq_msg = Enrollment.check_prerequisites_conn(
                conn, student_id, section["SubjectID"]
            )
            if not prereq_ok:
                return None, prereq_msg

            conflict_ok, conflict_sec = Enrollment.check_schedule_conflict_conn(
                conn, student_id, section
            )
            if not conflict_ok:
                return (
                    None,
                    f"Cannot waitlist a section that conflicts with enrolled schedule ({conflict_sec}).",
                )

            credit_ok, credit_msg = Enrollment.check_credit_limit_conn(
                conn, student_id, section["Semester"], int(section["Credits"])
            )
            if not credit_ok:
                return None, credit_msg

            waiting_cnt = conn.execute(
                "SELECT COUNT(*) AS cnt FROM WAITLIST WHERE SectionID = ? AND Status = 'Waiting'",
                (sec_id,),
            ).fetchone()["cnt"]
            max_waitlist = max(1, int(section["Capacity"] * cls.WAITLIST_CAPACITY_RATIO))
            if waiting_cnt >= max_waitlist:
                return None, "Waitlist capacity reached."

            max_pos_row = conn.execute(
                "SELECT COALESCE(MAX(QueuePosition), 0) AS max_pos FROM WAITLIST WHERE SectionID = ?",
                (sec_id,),
            ).fetchone()
            next_pos = int(max_pos_row["max_pos"]) + 1

            if existing_wait:
                conn.execute(
                    """
                    UPDATE WAITLIST
                    SET QueuePosition = ?, JoinedAt = CURRENT_TIMESTAMP, Status = 'Waiting'
                    WHERE WaitlistID = ?
                    """,
                    (next_pos, existing_wait["WaitlistID"]),
                )
                wid = existing_wait["WaitlistID"]
            else:
                cur = conn.execute(
                    """
                    INSERT INTO WAITLIST (StudentID, SectionID, QueuePosition, Status)
                    VALUES (?, ?, ?, 'Waiting')
                    """,
                    (student_id, sec_id, next_pos),
                )
                wid = cur.lastrowid

            row = conn.execute(
                "SELECT * FROM WAITLIST WHERE WaitlistID = ?", (wid,)
            ).fetchone()
        return cls.from_row(row), f"Joined waitlist at position #{next_pos}."

    def cancelWaitlist(self, db) -> tuple[bool, str]:
        return self.cancel_by_id(db, self._waitlistId, self._studentId)

    @classmethod
    def cancel_by_id(
        cls, db, waitlist_id: int, student_id: str
    ) -> tuple[bool, str]:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT Status FROM WAITLIST WHERE WaitlistID = ? AND StudentID = ?",
                (waitlist_id, student_id),
            ).fetchone()
            if not row or row["Status"] != "Waiting":
                return False, "Active waitlist entry not found."
            conn.execute(
                "UPDATE WAITLIST SET Status = 'Cancelled' WHERE WaitlistID = ?",
                (waitlist_id,),
            )
        return True, "Waitlist entry cancelled."

    def processNextInQueue(self, db) -> Optional[str]:
        with db.atomic_transaction() as conn:
            return self.process_next_in_queue_conn(conn, self._sectionId)

    @classmethod
    def process_next_in_queue_conn(cls, conn, section_id: str) -> Optional[str]:
        from app.models.enrollment import Enrollment

        section = conn.execute(
            """
            SELECT c.*, s.Credits
            FROM COURSES c
            JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
            WHERE c.SectionID = ?
            """,
            (section_id,),
        ).fetchone()
        if not section or section["Status"] != "Open":
            return None

        enrolled_cnt = conn.execute(
            "SELECT COUNT(*) AS cnt FROM ENROLLMENTS WHERE SectionID = ? AND Status = 'Enrolled'",
            (section_id,),
        ).fetchone()["cnt"]
        if enrolled_cnt >= section["Capacity"]:
            return None

        candidates = conn.execute(
            """
            SELECT * FROM WAITLIST
            WHERE SectionID = ? AND Status = 'Waiting'
            ORDER BY QueuePosition ASC, JoinedAt ASC
            """,
            (section_id,),
        ).fetchall()

        for cand in candidates:
            sid = cand["StudentID"]
            conflict_ok, _ = Enrollment.check_schedule_conflict_conn(conn, sid, section)
            credit_ok, _ = Enrollment.check_credit_limit_conn(
                conn, sid, section["Semester"], int(section["Credits"]), include_cart=False
            )
            already_subject = conn.execute(
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
                (sid, section["Semester"], section["SubjectID"]),
            ).fetchone()

            if not conflict_ok or not credit_ok or already_subject:
                conn.execute(
                    "UPDATE WAITLIST SET Status = 'Skipped' WHERE WaitlistID = ?",
                    (cand["WaitlistID"],),
                )
                continue

            conf_num = SemesterRegistration.generateConfirmationNumber(section["Semester"])
            existing_enr = conn.execute(
                "SELECT EnrollmentID FROM ENROLLMENTS WHERE StudentID = ? AND SectionID = ?",
                (sid, section_id),
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
                    (sid, section_id, conf_num),
                )

            conn.execute(
                "UPDATE WAITLIST SET Status = 'Enrolled' WHERE WaitlistID = ?",
                (cand["WaitlistID"],),
            )
            conn.execute(
                """
                UPDATE WAITLIST
                SET Status = 'Cancelled'
                WHERE StudentID = ?
                  AND Status = 'Waiting'
                  AND SectionID != ?
                  AND SectionID IN (
                      SELECT SectionID FROM COURSES
                      WHERE SubjectID = ? AND Semester = ?
                  )
                """,
                (sid, section_id, section["SubjectID"], section["Semester"]),
            )
            conn.execute(
                "DELETE FROM REGISTRATION_CART WHERE StudentID = ? AND SectionID = ?",
                (sid, section_id),
            )
            SemesterRegistration.sync_summary_conn(conn, sid, section["Semester"], conf_num)
            return sid

        return None
