from typing import Optional


class Faculty:
    def __init__(self, faculty_id: str, faculty_name: str):
        self._facultyId = faculty_id
        self._facultyName = faculty_name

    @property
    def faculty_id(self) -> str:
        return self._facultyId

    @property
    def faculty_name(self) -> str:
        return self._facultyName

    @classmethod
    def from_row(cls, row) -> Optional["Faculty"]:
        if row is None:
            return None
        return cls(faculty_id=row["FacultyID"], faculty_name=row["FacultyName"])

    @classmethod
    def get_all(cls, db) -> list["Faculty"]:
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT FacultyID, FacultyName FROM FACULTIES ORDER BY FacultyID ASC"
            ).fetchall()
        return [cls.from_row(r) for r in rows]

    @classmethod
    def find_by_id(cls, db, faculty_id: str) -> Optional["Faculty"]:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT FacultyID, FacultyName FROM FACULTIES WHERE FacultyID = ?",
                (faculty_id.strip().upper(),),
            ).fetchone()
        return cls.from_row(row)

    @classmethod
    def create(
        cls, db, faculty_id: str, faculty_name: str
    ) -> tuple[Optional["Faculty"], str]:
        fid = faculty_id.strip().upper()
        fname = faculty_name.strip()
        if not fid or not fname:
            return None, "Faculty ID and Faculty Name are required."
        if len(fid) > 10:
            return None, "Faculty ID must be at most 10 characters."
        with db.connection() as conn:
            if conn.execute(
                "SELECT 1 FROM FACULTIES WHERE FacultyID = ?", (fid,)
            ).fetchone():
                return None, "Faculty ID already exists."
            conn.execute(
                "INSERT INTO FACULTIES (FacultyID, FacultyName) VALUES (?, ?)",
                (fid, fname),
            )
        return cls(fid, fname), "Faculty created successfully."

    @classmethod
    def update(cls, db, faculty_id: str, faculty_name: str) -> tuple[bool, str]:
        fid = faculty_id.strip().upper()
        fname = faculty_name.strip()
        if not fname:
            return False, "Faculty Name is required."
        with db.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM FACULTIES WHERE FacultyID = ?", (fid,)
            ).fetchone()
            if not row:
                return False, "Faculty not found."
            conn.execute(
                "UPDATE FACULTIES SET FacultyName = ? WHERE FacultyID = ?",
                (fname, fid),
            )
        return True, "Faculty updated successfully."

    def addClass(
        self, db, class_id: str, class_name: str, academic_year: str
    ) -> tuple[Optional[object], str]:
        from app.models.administrative_class import AdministrativeClass

        return AdministrativeClass.create(
            db, class_id, self._facultyId, class_name, academic_year
        )

    def assignLecturer(self, db, lecturer_id: str) -> tuple[bool, str]:
        lid = lecturer_id.strip().upper()
        with db.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM LECTURERS WHERE LecturerID = ?", (lid,)
            ).fetchone()
            if not row:
                return False, "Lecturer not found."
            conn.execute(
                "UPDATE LECTURERS SET FacultyID = ? WHERE LecturerID = ?",
                (self._facultyId, lid),
            )
        return True, "Lecturer assigned to faculty successfully."
