from typing import Optional


class Subject:
    VALID_STATUSES = ("Active", "Archived")

    def __init__(
        self,
        subject_id: str,
        subject_name: str,
        credits: int,
        prerequisite_id: Optional[str] = None,
        status: str = "Active",
    ):
        self._subjectId = subject_id
        self._subjectName = subject_name
        self._credits = credits
        self._prerequisiteId = prerequisite_id
        self._status = status

    @property
    def subject_id(self) -> str:
        return self._subjectId

    @property
    def subject_name(self) -> str:
        return self._subjectName

    @property
    def credits(self) -> int:
        return self._credits

    @property
    def prerequisite_id(self) -> Optional[str]:
        return self._prerequisiteId

    @property
    def status(self) -> str:
        return self._status

    @classmethod
    def from_row(cls, row) -> Optional["Subject"]:
        if row is None:
            return None
        return cls(
            subject_id=row["SubjectID"],
            subject_name=row["SubjectName"],
            credits=row["Credits"],
            prerequisite_id=row["PrerequisiteID"],
            status=row["Status"],
        )

    @classmethod
    def get_all(cls, db, active_only: bool = False) -> list["Subject"]:
        where_clause = "WHERE Status = 'Active'" if active_only else ""
        with db.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM SUBJECTS {where_clause} ORDER BY SubjectID ASC"
            ).fetchall()
        return [cls.from_row(r) for r in rows]

    @classmethod
    def find_by_id(cls, db, subject_id: str) -> Optional["Subject"]:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM SUBJECTS WHERE SubjectID = ?",
                (subject_id.strip().upper(),),
            ).fetchone()
        return cls.from_row(row)

    @classmethod
    def has_circular_prerequisite(
        cls, db, subject_id: str, prerequisite_id: Optional[str]
    ) -> bool:
        if not prerequisite_id:
            return False
        target = subject_id.strip().upper()
        current = prerequisite_id.strip().upper()
        if current == target:
            return True
        visited = {target}
        with db.connection() as conn:
            while current:
                if current in visited:
                    return True
                visited.add(current)
                row = conn.execute(
                    "SELECT PrerequisiteID FROM SUBJECTS WHERE SubjectID = ?",
                    (current,),
                ).fetchone()
                if not row:
                    break
                current = row["PrerequisiteID"]
        return False

    @classmethod
    def create(
        cls,
        db,
        subject_id: str,
        subject_name: str,
        credits: int,
        prerequisite_id: Optional[str] = None,
    ) -> tuple[Optional["Subject"], str]:
        sid = subject_id.strip().upper()
        sname = subject_name.strip()
        prereq = prerequisite_id.strip().upper() if prerequisite_id else None
        if prereq == "":
            prereq = None
        if not sid or not sname:
            return None, "Subject ID and Subject Name are required."
        if len(sid) > 10:
            return None, "Subject ID must be at most 10 characters."
        try:
            credits_int = int(credits)
        except (TypeError, ValueError):
            return None, "Credits must be an integer between 1 and 4."
        if credits_int < 1 or credits_int > 4:
            return None, "Credits must be between 1 and 4."
        with db.connection() as conn:
            if conn.execute(
                "SELECT 1 FROM SUBJECTS WHERE SubjectID = ?", (sid,)
            ).fetchone():
                return None, "Subject code already exists."
            if prereq:
                if prereq == sid:
                    return None, "Cannot assign circular prerequisite chain."
                if not conn.execute(
                    "SELECT 1 FROM SUBJECTS WHERE SubjectID = ?", (prereq,)
                ).fetchone():
                    return None, "Prerequisite subject does not exist."
        if cls.has_circular_prerequisite(db, sid, prereq):
            return None, "Cannot assign circular prerequisite chain."
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO SUBJECTS (SubjectID, SubjectName, Credits, PrerequisiteID, Status)
                VALUES (?, ?, ?, ?, 'Active')
                """,
                (sid, sname, credits_int, prereq),
            )
        return cls.find_by_id(db, sid), "Subject created successfully."

    @classmethod
    def update(
        cls,
        db,
        subject_id: str,
        subject_name: str,
        credits: int,
        prerequisite_id: Optional[str] = None,
    ) -> tuple[bool, str]:
        sid = subject_id.strip().upper()
        sname = subject_name.strip()
        prereq = prerequisite_id.strip().upper() if prerequisite_id else None
        if prereq == "":
            prereq = None
        if not sname:
            return False, "Subject Name is required."
        try:
            credits_int = int(credits)
        except (TypeError, ValueError):
            return False, "Credits must be an integer between 1 and 4."
        if credits_int < 1 or credits_int > 4:
            return False, "Credits must be between 1 and 4."
        with db.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM SUBJECTS WHERE SubjectID = ?", (sid,)
            ).fetchone():
                return False, "Subject not found."
            if prereq and not conn.execute(
                "SELECT 1 FROM SUBJECTS WHERE SubjectID = ?", (prereq,)
            ).fetchone():
                return False, "Prerequisite subject does not exist."
        if cls.has_circular_prerequisite(db, sid, prereq):
            return False, "Cannot assign circular prerequisite chain."
        with db.connection() as conn:
            conn.execute(
                """
                UPDATE SUBJECTS
                SET SubjectName = ?, Credits = ?, PrerequisiteID = ?
                WHERE SubjectID = ?
                """,
                (sname, credits_int, prereq, sid),
            )
        return True, "Subject updated successfully."

    @classmethod
    def set_status(cls, db, subject_id: str, status: str) -> tuple[bool, str]:
        sid = subject_id.strip().upper()
        if status not in cls.VALID_STATUSES:
            return False, "Invalid subject status."
        with db.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM SUBJECTS WHERE SubjectID = ?", (sid,)
            ).fetchone():
                return False, "Subject not found."
            conn.execute(
                "UPDATE SUBJECTS SET Status = ? WHERE SubjectID = ?",
                (status, sid),
            )
        return True, f"Subject status updated to {status}."

    def checkPrerequisite(self, db, student_id: str) -> bool:
        if not self._prerequisiteId:
            return True
        with db.connection() as conn:
            row = conn.execute(
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
                (student_id, self._prerequisiteId),
            ).fetchone()
        return row is not None
