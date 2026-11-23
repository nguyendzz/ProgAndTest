from typing import Optional


class CourseSection:
    VALID_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
    VALID_STATUSES = ("Open", "Closed", "Cancelled")

    def __init__(
        self,
        section_id: str,
        subject_id: str,
        lecturer_id: str,
        semester: str,
        capacity: int,
        day_of_week: str,
        start_time: str,
        end_time: str,
        room: str,
        status: str = "Open",
        subject_name: str = "",
        lecturer_name: str = "",
    ):
        self._sectionId = section_id
        self._subjectId = subject_id
        self._lecturerId = lecturer_id
        self._semester = semester
        self._capacity = capacity
        self._dayOfWeek = day_of_week
        self._startTime = start_time
        self._endTime = end_time
        self._room = room
        self._status = status
        self._schedule = f"{day_of_week} {start_time}-{end_time}"
        self._subjectName = subject_name
        self._lecturerName = lecturer_name

    @property
    def section_id(self) -> str:
        return self._sectionId

    @property
    def subject_id(self) -> str:
        return self._subjectId

    @property
    def lecturer_id(self) -> str:
        return self._lecturerId

    @property
    def semester(self) -> str:
        return self._semester

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def day_of_week(self) -> str:
        return self._dayOfWeek

    @property
    def start_time(self) -> str:
        return self._startTime

    @property
    def end_time(self) -> str:
        return self._endTime

    @property
    def room(self) -> str:
        return self._room

    @property
    def status(self) -> str:
        return self._status

    @property
    def schedule(self) -> str:
        return self._schedule

    @property
    def subject_name(self) -> str:
        return self._subjectName

    @property
    def lecturer_name(self) -> str:
        return self._lecturerName

    @classmethod
    def from_row(cls, row) -> Optional["CourseSection"]:
        if row is None:
            return None
        keys = row.keys()
        return cls(
            section_id=row["SectionID"],
            subject_id=row["SubjectID"],
            lecturer_id=row["LecturerID"],
            semester=row["Semester"],
            capacity=row["Capacity"],
            day_of_week=row["DayOfWeek"],
            start_time=row["StartTime"],
            end_time=row["EndTime"],
            room=row["Room"],
            status=row["Status"],
            subject_name=row["SubjectName"] if "SubjectName" in keys else "",
            lecturer_name=row["LecturerName"] if "LecturerName" in keys else "",
        )

    @classmethod
    def get_all(cls, db, semester: str = "") -> list["CourseSection"]:
        params = []
        where_clause = ""
        if semester.strip():
            where_clause = "WHERE c.Semester = ?"
            params.append(semester.strip())
        with db.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT c.*, s.SubjectName, l.FullName AS LecturerName
                FROM COURSES c
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                {where_clause}
                ORDER BY c.Semester DESC, c.SectionID ASC
                """,
                params,
            ).fetchall()
        return [cls.from_row(r) for r in rows]

    @classmethod
    def find_by_id(cls, db, section_id: str) -> Optional["CourseSection"]:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT c.*, s.SubjectName, l.FullName AS LecturerName
                FROM COURSES c
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                WHERE c.SectionID = ?
                """,
                (section_id.strip().upper(),),
            ).fetchone()
        return cls.from_row(row)

    @staticmethod
    def _times_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
        return start_a < end_b and end_a > start_b

    def checkScheduleConflict(self, other: "CourseSection") -> bool:
        if self._semester != other._semester:
            return False
        if self._dayOfWeek != other._dayOfWeek:
            return False
        return self._times_overlap(
            self._startTime, self._endTime, other._startTime, other._endTime
        )

    def getEnrolledCount(self, db) -> int:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM ENROLLMENTS
                WHERE SectionID = ? AND Status = 'Enrolled'
                """,
                (self._sectionId,),
            ).fetchone()
        return row["cnt"]

    def checkRemainingSeats(self, db) -> int:
        return max(0, self._capacity - self.getEnrolledCount(db))

    @classmethod
    def open_section(
        cls,
        db,
        section_id: str,
        subject_id: str,
        lecturer_id: str,
        semester: str,
        capacity: int,
        day_of_week: str,
        start_time: str,
        end_time: str,
        room: str,
    ) -> tuple[Optional["CourseSection"], str]:
        sec_id = section_id.strip().upper()
        sub_id = subject_id.strip().upper()
        lec_id = lecturer_id.strip().upper()
        sem = semester.strip()
        rm = room.strip()
        day = day_of_week.strip()
        st = start_time.strip()
        et = end_time.strip()

        if not all([sec_id, sub_id, lec_id, sem, day, st, et, rm]):
            return None, "All section fields are required."
        if len(sec_id) > 10:
            return None, "Section ID must be at most 10 characters."
        if day not in cls.VALID_DAYS:
            return None, "Invalid day of week."
        if st >= et:
            return None, "Start time must be earlier than end time."
        try:
            cap_int = int(capacity)
        except (TypeError, ValueError):
            return None, "Capacity must be an integer between 10 and 200."
        if cap_int < 10 or cap_int > 200:
            return None, "Course section capacity must be between 10 and 200 seats."

        with db.connection() as conn:
            if conn.execute(
                "SELECT 1 FROM COURSES WHERE SectionID = ?", (sec_id,)
            ).fetchone():
                return None, "Section ID already exists."
            sub_row = conn.execute(
                "SELECT Status FROM SUBJECTS WHERE SubjectID = ?", (sub_id,)
            ).fetchone()
            if not sub_row:
                return None, "Selected subject does not exist."
            if sub_row["Status"] == "Archived":
                return (
                    None,
                    "Archived curriculum subjects cannot have new course sections opened.",
                )
            if not conn.execute(
                "SELECT 1 FROM LECTURERS WHERE LecturerID = ?", (lec_id,)
            ).fetchone():
                return None, "Selected lecturer does not exist."

            lecturer_conflict = conn.execute(
                """
                SELECT SectionID
                FROM COURSES
                WHERE LecturerID = ?
                  AND Semester = ?
                  AND DayOfWeek = ?
                  AND Status != 'Cancelled'
                  AND StartTime < ?
                  AND EndTime > ?
                """,
                (lec_id, sem, day, et, st),
            ).fetchone()
            if lecturer_conflict:
                return (
                    None,
                    "Lecturer is already assigned to another class at this time.",
                )

            room_conflict = conn.execute(
                """
                SELECT SectionID
                FROM COURSES
                WHERE LOWER(Room) = LOWER(?)
                  AND Semester = ?
                  AND DayOfWeek = ?
                  AND Status != 'Cancelled'
                  AND StartTime < ?
                  AND EndTime > ?
                """,
                (rm, sem, day, et, st),
            ).fetchone()
            if room_conflict:
                return None, "Room is occupied during this time."

            conn.execute(
                """
                INSERT INTO COURSES (
                    SectionID, SubjectID, LecturerID, Semester, Capacity,
                    DayOfWeek, StartTime, EndTime, Room, Status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Open')
                """,
                (sec_id, sub_id, lec_id, sem, cap_int, day, st, et, rm),
            )
        return cls.find_by_id(db, sec_id), "Course section opened successfully."

    @classmethod
    def update_status(cls, db, section_id: str, status: str) -> tuple[bool, str]:
        sec_id = section_id.strip().upper()
        if status not in cls.VALID_STATUSES:
            return False, "Invalid section status."
        with db.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM COURSES WHERE SectionID = ?", (sec_id,)
            ).fetchone():
                return False, "Course section not found."
            conn.execute(
                "UPDATE COURSES SET Status = ? WHERE SectionID = ?",
                (status, sec_id),
            )
        return True, f"Section status updated to {status}."
