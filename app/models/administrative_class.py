from typing import Optional


class AdministrativeClass:
    def __init__(
        self,
        class_id: str,
        faculty_id: str,
        class_name: str,
        academic_year: str,
        faculty_name: str = "",
    ):
        self._classId = class_id
        self._facultyId = faculty_id
        self._className = class_name
        self._academicYear = academic_year
        self._facultyName = faculty_name

    @property
    def class_id(self) -> str:
        return self._classId

    @property
    def faculty_id(self) -> str:
        return self._facultyId

    @property
    def class_name(self) -> str:
        return self._className

    @property
    def academic_year(self) -> str:
        return self._academicYear

    @property
    def faculty_name(self) -> str:
        return self._facultyName

    @classmethod
    def from_row(cls, row) -> Optional["AdministrativeClass"]:
        if row is None:
            return None
        keys = row.keys()
        return cls(
            class_id=row["ClassID"],
            faculty_id=row["FacultyID"],
            class_name=row["ClassName"],
            academic_year=row["AcademicYear"],
            faculty_name=row["FacultyName"] if "FacultyName" in keys else "",
        )

    @classmethod
    def get_all(cls, db, faculty_id: str = "") -> list["AdministrativeClass"]:
        params = []
        where_clause = ""
        if faculty_id.strip():
            where_clause = "WHERE c.FacultyID = ?"
            params.append(faculty_id.strip().upper())
        with db.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT c.ClassID, c.FacultyID, c.ClassName, c.AcademicYear, f.FacultyName
                FROM CLASSES c
                JOIN FACULTIES f ON c.FacultyID = f.FacultyID
                {where_clause}
                ORDER BY c.ClassID ASC
                """,
                params,
            ).fetchall()
        return [cls.from_row(r) for r in rows]

    @classmethod
    def find_by_id(cls, db, class_id: str) -> Optional["AdministrativeClass"]:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT c.ClassID, c.FacultyID, c.ClassName, c.AcademicYear, f.FacultyName
                FROM CLASSES c
                JOIN FACULTIES f ON c.FacultyID = f.FacultyID
                WHERE c.ClassID = ?
                """,
                (class_id.strip().upper(),),
            ).fetchone()
        return cls.from_row(row)

    @classmethod
    def create(
        cls,
        db,
        class_id: str,
        faculty_id: str,
        class_name: str,
        academic_year: str,
    ) -> tuple[Optional["AdministrativeClass"], str]:
        cid = class_id.strip().upper()
        fid = faculty_id.strip().upper()
        cname = class_name.strip()
        ayear = academic_year.strip()
        if not fid:
            return None, "Please select a faculty."
        if not cid or not cname or not ayear:
            return None, "Class ID, Class Name, and Academic Year are required."
        if len(cid) > 10:
            return None, "Class ID must be at most 10 characters."
        with db.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM FACULTIES WHERE FacultyID = ?", (fid,)
            ).fetchone():
                return None, "Selected faculty does not exist."
            if conn.execute(
                "SELECT 1 FROM CLASSES WHERE ClassID = ?", (cid,)
            ).fetchone():
                return None, "Class ID already exists."
            conn.execute(
                """
                INSERT INTO CLASSES (ClassID, FacultyID, ClassName, AcademicYear)
                VALUES (?, ?, ?, ?)
                """,
                (cid, fid, cname, ayear),
            )
        return cls.find_by_id(db, cid), "Class created successfully."

    @classmethod
    def update(
        cls,
        db,
        class_id: str,
        faculty_id: str,
        class_name: str,
        academic_year: str,
    ) -> tuple[bool, str]:
        cid = class_id.strip().upper()
        fid = faculty_id.strip().upper()
        cname = class_name.strip()
        ayear = academic_year.strip()
        if not fid:
            return False, "Please select a faculty."
        if not cname or not ayear:
            return False, "Class Name and Academic Year are required."
        with db.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM CLASSES WHERE ClassID = ?", (cid,)
            ).fetchone():
                return False, "Class not found."
            if not conn.execute(
                "SELECT 1 FROM FACULTIES WHERE FacultyID = ?", (fid,)
            ).fetchone():
                return False, "Selected faculty does not exist."
            conn.execute(
                """
                UPDATE CLASSES
                SET FacultyID = ?, ClassName = ?, AcademicYear = ?
                WHERE ClassID = ?
                """,
                (fid, cname, ayear, cid),
            )
        return True, "Class updated successfully."

    def getStudentList(self, db) -> list[dict]:
        with db.connection() as conn:
            rows = conn.execute(
                """
                SELECT StudentID, FullName, DOB, Email, Phone, Status
                FROM STUDENTS
                WHERE ClassID = ?
                ORDER BY StudentID ASC
                """,
                (self._classId,),
            ).fetchall()
        return [dict(r) for r in rows]
