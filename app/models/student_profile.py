import re
from typing import Optional
from app.utils.security import SecurityService


class StudentProfileManager:
    EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
    VALID_STATUSES = ("Active", "Inactive", "Graduated", "Suspended")

    @classmethod
    def list_paginated(
        cls,
        db,
        page: int = 1,
        per_page: int = 10,
        search: str = "",
        class_filter: str = "",
    ) -> dict:
        page = max(1, page)
        offset = (page - 1) * per_page
        conditions = []
        params = []
        if search.strip():
            like_val = f"%{search.strip()}%"
            conditions.append("(s.StudentID LIKE ? OR s.FullName LIKE ? OR s.ClassID LIKE ?)")
            params.extend([like_val, like_val, like_val])
        if class_filter.strip():
            conditions.append("s.ClassID = ?")
            params.append(class_filter.strip().upper())
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with db.connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM STUDENTS s {where_clause}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"""
                SELECT s.*, c.ClassName, u.Username, u.Status AS AccountStatus,
                       (SELECT COUNT(*) FROM ENROLLMENTS e WHERE e.StudentID = s.StudentID) AS EnrollmentCount
                FROM STUDENTS s
                JOIN CLASSES c ON s.ClassID = c.ClassID
                JOIN USERS u ON s.UserID = u.UserID
                {where_clause}
                ORDER BY s.StudentID ASC
                LIMIT ? OFFSET ?
                """,
                [*params, per_page, offset],
            ).fetchall()
        total_pages = max(1, (total + per_page - 1) // per_page)
        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }

    @classmethod
    def find_by_id(cls, db, student_id: str) -> Optional[dict]:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT s.*, c.ClassName, f.FacultyName, u.Username, u.Status AS AccountStatus,
                       (SELECT COUNT(*) FROM ENROLLMENTS e WHERE e.StudentID = s.StudentID) AS EnrollmentCount
                FROM STUDENTS s
                JOIN CLASSES c ON s.ClassID = c.ClassID
                JOIN FACULTIES f ON c.FacultyID = f.FacultyID
                JOIN USERS u ON s.UserID = u.UserID
                WHERE s.StudentID = ?
                """,
                (student_id.strip().upper(),),
            ).fetchone()
        return dict(row) if row else None

    @classmethod
    def create_student(
        cls,
        db,
        student_id: str,
        full_name: str,
        dob: str,
        email: str,
        phone: str,
        class_id: str,
        default_password: str = "Student123",
    ) -> tuple[Optional[dict], str]:
        sid = student_id.strip().upper()
        name = full_name.strip()
        dob_clean = dob.strip()
        email_clean = email.strip().lower()
        phone_clean = phone.strip()
        cid = class_id.strip().upper()

        if not all([sid, name, dob_clean, email_clean, cid]):
            return None, "Student ID, Full Name, DOB, Email, and Class are required."
        if len(sid) > 10:
            return None, "Student ID must be at most 10 characters."
        if not cls.EMAIL_PATTERN.match(email_clean):
            return None, "Invalid email format."

        with db.connection() as conn:
            if conn.execute(
                "SELECT 1 FROM STUDENTS WHERE StudentID = ?", (sid,)
            ).fetchone():
                return None, "Student code already exists."
            if not conn.execute(
                "SELECT 1 FROM CLASSES WHERE ClassID = ?", (cid,)
            ).fetchone():
                return None, "Selected class does not exist."
            if conn.execute(
                "SELECT 1 FROM USERS WHERE Username = ?", (sid,)
            ).fetchone():
                return None, "Linked username already exists."
            if conn.execute(
                "SELECT 1 FROM USERS WHERE LOWER(Email) = LOWER(?)", (email_clean,)
            ).fetchone():
                return None, "Email already registered."

            pw_hash = SecurityService.hash_password(default_password)
            cursor = conn.execute(
                """
                INSERT INTO USERS (Username, PasswordHash, Role, Status, Email)
                VALUES (?, ?, 'Student', 'Active', ?)
                """,
                (sid, pw_hash, email_clean),
            )
            user_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO STUDENTS (
                    StudentID, UserID, ClassID, FullName, DOB, Email, Phone, Status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Active')
                """,
                (sid, user_id, cid, name, dob_clean, email_clean, phone_clean),
            )
        return cls.find_by_id(db, sid), "Student profile and linked account created successfully."

    @classmethod
    def update_student(
        cls,
        db,
        student_id: str,
        full_name: str,
        dob: str,
        email: str,
        phone: str,
        class_id: str,
        status: str,
    ) -> tuple[bool, str]:
        sid = student_id.strip().upper()
        name = full_name.strip()
        dob_clean = dob.strip()
        email_clean = email.strip().lower()
        phone_clean = phone.strip()
        cid = class_id.strip().upper()

        if not all([name, dob_clean, email_clean, cid]):
            return False, "Full Name, DOB, Email, and Class are required."
        if not cls.EMAIL_PATTERN.match(email_clean):
            return False, "Invalid email format."
        if status not in cls.VALID_STATUSES:
            return False, "Invalid student status."

        with db.connection() as conn:
            existing = conn.execute(
                "SELECT UserID FROM STUDENTS WHERE StudentID = ?", (sid,)
            ).fetchone()
            if not existing:
                return False, "Student profile not found."
            if not conn.execute(
                "SELECT 1 FROM CLASSES WHERE ClassID = ?", (cid,)
            ).fetchone():
                return False, "Selected class does not exist."
            if conn.execute(
                "SELECT 1 FROM USERS WHERE LOWER(Email) = LOWER(?) AND UserID != ?",
                (email_clean, existing["UserID"]),
            ).fetchone():
                return False, "Email already registered by another user."
            conn.execute(
                """
                UPDATE STUDENTS
                SET ClassID = ?, FullName = ?, DOB = ?, Email = ?, Phone = ?, Status = ?
                WHERE StudentID = ?
                """,
                (cid, name, dob_clean, email_clean, phone_clean, status, sid),
            )
            conn.execute(
                "UPDATE USERS SET Email = ? WHERE UserID = ?",
                (email_clean, existing["UserID"]),
            )
        return True, "Student profile updated successfully."

    @classmethod
    def deactivate_profile(cls, db, student_id: str) -> tuple[bool, str]:
        sid = student_id.strip().upper()
        with db.connection() as conn:
            row = conn.execute(
                "SELECT UserID FROM STUDENTS WHERE StudentID = ?", (sid,)
            ).fetchone()
            if not row:
                return False, "Student profile not found."
            user_id = row["UserID"]
            conn.execute(
                "UPDATE USERS SET Status = 'Locked', SessionVersion = SessionVersion + 1 WHERE UserID = ?",
                (user_id,),
            )
            conn.execute(
                "UPDATE STUDENTS SET Status = 'Inactive' WHERE StudentID = ?",
                (sid,),
            )
            conn.execute(
                "UPDATE ENROLLMENTS SET Status = 'Dropped' WHERE StudentID = ? AND Status = 'Enrolled'",
                (sid,),
            )
        return (
            True,
            "Student profile deactivated. Account locked and historical records preserved.",
        )

    @classmethod
    def delete_profile_if_no_history(cls, db, student_id: str) -> tuple[bool, str]:
        sid = student_id.strip().upper()
        with db.connection() as conn:
            row = conn.execute(
                "SELECT UserID FROM STUDENTS WHERE StudentID = ?", (sid,)
            ).fetchone()
            if not row:
                return False, "Student profile not found."
            history = conn.execute(
                "SELECT 1 FROM ENROLLMENTS WHERE StudentID = ? LIMIT 1", (sid,)
            ).fetchone()
            if history:
                return (
                    False,
                    "Student has academic records. Profile must be deactivated rather than deleted.",
                )
            user_id = row["UserID"]
            conn.execute("DELETE FROM STUDENTS WHERE StudentID = ?", (sid,))
            conn.execute("DELETE FROM USERS WHERE UserID = ?", (user_id,))
        return True, "Student profile permanently deleted."
