from typing import Optional


class RegistrationCart:
    VALID_STATUSES = ("InCart", "Confirmed", "Expired")

    def __init__(
        self,
        cart_id: Optional[int],
        student_id: str,
        section_id: str,
        added_at: Optional[str] = None,
        status: str = "InCart",
    ):
        self._cartId = cart_id
        self._studentId = student_id
        self._sectionId = section_id
        self._addedAt = added_at
        self._status = status

    @property
    def cart_id(self) -> Optional[int]:
        return self._cartId

    @property
    def student_id(self) -> str:
        return self._studentId

    @property
    def section_id(self) -> str:
        return self._sectionId

    @property
    def added_at(self) -> Optional[str]:
        return self._addedAt

    @property
    def status(self) -> str:
        return self._status

    @classmethod
    def from_row(cls, row) -> Optional["RegistrationCart"]:
        if row is None:
            return None
        return cls(
            cart_id=row["CartID"],
            student_id=row["StudentID"],
            section_id=row["SectionID"],
            added_at=row["AddedAt"],
            status=row["Status"],
        )

    @classmethod
    def get_items(cls, db, student_id: str, semester: str = "") -> list[dict]:
        params = [student_id]
        sem_sql = ""
        if semester.strip():
            sem_sql = "AND c.Semester = ?"
            params.append(semester.strip())
        with db.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT rc.CartID,
                       rc.StudentID,
                       rc.SectionID,
                       rc.AddedAt,
                       rc.Status,
                       c.SubjectID,
                       s.SubjectName,
                       s.Credits,
                       c.Semester,
                       c.Capacity,
                       c.DayOfWeek,
                       c.StartTime,
                       c.EndTime,
                       c.Room,
                       l.FullName AS LecturerName
                FROM REGISTRATION_CART rc
                JOIN COURSES c ON rc.SectionID = c.SectionID
                JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                WHERE rc.StudentID = ?
                  AND rc.Status = 'InCart'
                  {sem_sql}
                ORDER BY rc.AddedAt ASC
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    @classmethod
    def get_cart_credits(cls, db, student_id: str, semester: str) -> int:
        with db.connection() as conn:
            row = conn.execute(
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
        return int(row["total"]) if row else 0

    def removeFromCart(self, db) -> tuple[bool, str]:
        return self.remove_item(db, self._studentId, self._sectionId)

    @classmethod
    def remove_item(cls, db, student_id: str, section_id: str) -> tuple[bool, str]:
        with db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM REGISTRATION_CART WHERE StudentID = ? AND SectionID = ?",
                (student_id, section_id.strip().upper()),
            )
            if cur.rowcount == 0:
                return False, "Section not found in registration cart."
        return True, f"Removed {section_id.strip().upper()} from registration cart."

    def clearCart(self, db) -> int:
        return self.clear_student_cart(db, self._studentId)

    @classmethod
    def clear_student_cart(cls, db, student_id: str, semester: str = "") -> int:
        with db.connection() as conn:
            if semester.strip():
                cur = conn.execute(
                    """
                    DELETE FROM REGISTRATION_CART
                    WHERE StudentID = ?
                      AND SectionID IN (SELECT SectionID FROM COURSES WHERE Semester = ?)
                    """,
                    (student_id, semester.strip()),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM REGISTRATION_CART WHERE StudentID = ?",
                    (student_id,),
                )
            return cur.rowcount
