from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.utils.security import SecurityService


class User(ABC):
    VALID_ROLES = ("Admin", "Staff", "Lecturer", "Student")
    VALID_STATUSES = ("Active", "Locked")
    TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        user_id: Optional[int],
        username: str,
        password_hash: str,
        role: str,
        status: str,
        email: str,
        failed_attempts: int = 0,
        locked_until: Optional[str] = None,
        reset_token: Optional[str] = None,
        reset_token_expiry: Optional[str] = None,
        session_version: int = 1,
    ):
        self._userId = user_id
        self.username = username
        self.__passwordHash = password_hash
        self.role = role
        self.status = status
        self.email = email
        self.failed_attempts = failed_attempts
        self.locked_until = locked_until
        self.reset_token = reset_token
        self.reset_token_expiry = reset_token_expiry
        self.session_version = session_version

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @property
    def user_id(self) -> Optional[int]:
        return self._userId

    @property
    def password_hash(self) -> str:
        return self.__passwordHash

    @abstractmethod
    def get_dashboard_endpoint(self) -> str:
        raise NotImplementedError

    def is_temporarily_locked(self, now: Optional[datetime] = None) -> bool:
        if not self.locked_until:
            return False
        current_time = now or self._utc_now()
        lock_time = datetime.strptime(self.locked_until, self.TIME_FORMAT)
        return current_time < lock_time

    def login(
        self,
        db,
        plain_password: str,
        max_attempts: int = 5,
        lock_minutes: int = 15,
        now: Optional[datetime] = None,
    ) -> tuple[bool, str]:
        current_time = now or self._utc_now()
        if self.status != "Active":
            return False, "Account locked. Contact administrator."
        if self.is_temporarily_locked(current_time):
            return (
                False,
                "Account locked for 15 minutes due to multiple failed login attempts.",
            )
        if self.locked_until and not self.is_temporarily_locked(current_time):
            self.failed_attempts = 0
            self.locked_until = None
            with db.connection() as conn:
                conn.execute(
                    "UPDATE USERS SET FailedAttempts = 0, LockedUntil = NULL WHERE UserID = ?",
                    (self._userId,),
                )
        if not SecurityService.verify_password(plain_password, self.__passwordHash):
            new_attempts = self.failed_attempts + 1
            locked_until_str = None
            message = "Invalid username or password"
            if new_attempts >= max_attempts:
                locked_until_str = (
                    current_time + timedelta(minutes=lock_minutes)
                ).strftime(self.TIME_FORMAT)
                message = "Account locked for 15 minutes due to 5 consecutive failed login attempts."
            self.failed_attempts = new_attempts
            self.locked_until = locked_until_str
            with db.connection() as conn:
                conn.execute(
                    "UPDATE USERS SET FailedAttempts = ?, LockedUntil = ? WHERE UserID = ?",
                    (new_attempts, locked_until_str, self._userId),
                )
            return False, message
        self.failed_attempts = 0
        self.locked_until = None
        with db.connection() as conn:
            conn.execute(
                "UPDATE USERS SET FailedAttempts = 0, LockedUntil = NULL WHERE UserID = ?",
                (self._userId,),
            )
        return True, "Login successful."

    def logout(self, db) -> None:
        self.session_version += 1
        with db.connection() as conn:
            conn.execute(
                "UPDATE USERS SET SessionVersion = ? WHERE UserID = ?",
                (self.session_version, self._userId),
            )

    def changePassword(
        self, db, current_password: str, new_password: str
    ) -> tuple[bool, str]:
        if not SecurityService.verify_password(current_password, self.__passwordHash):
            return False, "Current password is incorrect."
        valid, msg = SecurityService.validate_password_complexity(new_password)
        if not valid:
            return False, msg
        new_hash = SecurityService.hash_password(new_password)
        self.__passwordHash = new_hash
        self.session_version += 1
        with db.connection() as conn:
            conn.execute(
                """
                UPDATE USERS
                SET PasswordHash = ?, SessionVersion = ?
                WHERE UserID = ?
                """,
                (new_hash, self.session_version, self._userId),
            )
        return True, "Password changed successfully."

    def resetPassword(
        self,
        db,
        token: str,
        new_password: str,
        now: Optional[datetime] = None,
    ) -> tuple[bool, str]:
        current_time = now or self._utc_now()
        if not self.reset_token or self.reset_token != token:
            return False, "Invalid password reset token."
        if not self.reset_token_expiry:
            return False, "Password reset token has expired."
        expiry_time = datetime.strptime(self.reset_token_expiry, self.TIME_FORMAT)
        if current_time > expiry_time:
            return False, "Password reset token has expired. Please request a new link."
        valid, msg = SecurityService.validate_password_complexity(new_password)
        if not valid:
            return False, msg
        new_hash = SecurityService.hash_password(new_password)
        self.__passwordHash = new_hash
        self.reset_token = None
        self.reset_token_expiry = None
        self.failed_attempts = 0
        self.locked_until = None
        self.session_version += 1
        with db.connection() as conn:
            conn.execute(
                """
                UPDATE USERS
                SET PasswordHash = ?,
                    ResetToken = NULL,
                    ResetTokenExpiry = NULL,
                    FailedAttempts = 0,
                    LockedUntil = NULL,
                    SessionVersion = ?
                WHERE UserID = ?
                """,
                (new_hash, self.session_version, self._userId),
            )
        return (
            True,
            "Password reset successfully. Please sign in with your new password.",
        )

    def create_reset_token(
        self, db, expiry_minutes: int = 15, now: Optional[datetime] = None
    ) -> str:
        current_time = now or self._utc_now()
        token = SecurityService.generate_reset_token()
        expiry_str = (current_time + timedelta(minutes=expiry_minutes)).strftime(
            self.TIME_FORMAT
        )
        self.reset_token = token
        self.reset_token_expiry = expiry_str
        with db.connection() as conn:
            conn.execute(
                "UPDATE USERS SET ResetToken = ?, ResetTokenExpiry = ? WHERE UserID = ?",
                (token, expiry_str, self._userId),
            )
        return token

    @classmethod
    def from_row(cls, row) -> Optional["User"]:
        if row is None:
            return None
        role = row["Role"]
        subclass_map = {
            "Admin": Administrator,
            "Staff": AcademicStaff,
            "Lecturer": LecturerAccount,
            "Student": StudentAccount,
        }
        target_cls = subclass_map.get(role, Administrator)
        return target_cls(
            user_id=row["UserID"],
            username=row["Username"],
            password_hash=row["PasswordHash"],
            role=role,
            status=row["Status"],
            email=row["Email"],
            failed_attempts=row["FailedAttempts"],
            locked_until=row["LockedUntil"],
            reset_token=row["ResetToken"],
            reset_token_expiry=row["ResetTokenExpiry"],
            session_version=row["SessionVersion"],
        )

    @classmethod
    def find_by_id(cls, db, user_id: int) -> Optional["User"]:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM USERS WHERE UserID = ?", (user_id,)
            ).fetchone()
        return cls.from_row(row)

    @classmethod
    def find_by_username(cls, db, username: str) -> Optional["User"]:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM USERS WHERE Username = ?", (username.strip(),)
            ).fetchone()
        return cls.from_row(row)

    @classmethod
    def find_by_username_or_email(cls, db, identifier: str) -> Optional["User"]:
        clean = identifier.strip()
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM USERS WHERE Username = ? OR LOWER(Email) = LOWER(?)",
                (clean, clean),
            ).fetchone()
        return cls.from_row(row)

    @classmethod
    def find_by_reset_token(cls, db, token: str) -> Optional["User"]:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM USERS WHERE ResetToken = ?", (token,)
            ).fetchone()
        return cls.from_row(row)

    @classmethod
    def create(
        cls, db, username: str, plain_password: str, role: str, email: str
    ) -> tuple[Optional["User"], str]:
        clean_user = username.strip()
        clean_email = email.strip().lower()
        if not clean_user or not clean_email:
            return None, "Username and email are required."
        if role not in cls.VALID_ROLES:
            return None, "Invalid role selected."
        valid, msg = SecurityService.validate_password_complexity(plain_password)
        if not valid:
            return None, msg
        with db.connection() as conn:
            if conn.execute(
                "SELECT 1 FROM USERS WHERE Username = ?", (clean_user,)
            ).fetchone():
                return None, "Username already taken."
            if conn.execute(
                "SELECT 1 FROM USERS WHERE LOWER(Email) = LOWER(?)", (clean_email,)
            ).fetchone():
                return None, "Email already registered."
            pw_hash = SecurityService.hash_password(plain_password)
            cursor = conn.execute(
                """
                INSERT INTO USERS (Username, PasswordHash, Role, Status, Email)
                VALUES (?, ?, ?, 'Active', ?)
                """,
                (clean_user, pw_hash, role, clean_email),
            )
            new_id = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM USERS WHERE UserID = ?", (new_id,)
            ).fetchone()
        return cls.from_row(row), "User account created successfully."

    @classmethod
    def list_paginated(
        cls,
        db,
        page: int = 1,
        per_page: int = 10,
        search: str = "",
        role_filter: str = "",
    ) -> dict:
        page = max(1, page)
        offset = (page - 1) * per_page
        conditions = []
        params = []
        if search.strip():
            like_val = f"%{search.strip()}%"
            conditions.append("(Username LIKE ? OR Email LIKE ?)")
            params.extend([like_val, like_val])
        if role_filter in cls.VALID_ROLES:
            conditions.append("Role = ?")
            params.append(role_filter)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with db.connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM USERS {where_clause}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"""
                SELECT * FROM USERS {where_clause}
                ORDER BY UserID ASC
                LIMIT ? OFFSET ?
                """,
                [*params, per_page, offset],
            ).fetchall()
        total_pages = max(1, (total + per_page - 1) // per_page)
        return {
            "items": [cls.from_row(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }

    @classmethod
    def update_role(
        cls,
        db,
        target_user_id: int,
        new_role: str,
        actor_user_id: Optional[int] = None,
    ) -> tuple[bool, str]:
        if actor_user_id is not None and target_user_id == actor_user_id:
            return False, "Administrator cannot change their own role."
        if new_role not in cls.VALID_ROLES:
            return False, "Invalid role."
        with db.connection() as conn:
            row = conn.execute(
                "SELECT UserID FROM USERS WHERE UserID = ?", (target_user_id,)
            ).fetchone()
            if not row:
                return False, "User account not found."
            conn.execute(
                "UPDATE USERS SET Role = ? WHERE UserID = ?",
                (new_role, target_user_id),
            )
        return True, "User role updated successfully."

    @classmethod
    def toggle_status(
        cls, db, target_user_id: int, actor_user_id: int
    ) -> tuple[bool, str]:
        if target_user_id == actor_user_id:
            return False, "Administrator cannot lock their own active account."
        with db.connection() as conn:
            row = conn.execute(
                "SELECT Status FROM USERS WHERE UserID = ?", (target_user_id,)
            ).fetchone()
            if not row:
                return False, "User account not found."
            new_status = "Locked" if row["Status"] == "Active" else "Active"
            conn.execute(
                """
                UPDATE USERS
                SET Status = ?, FailedAttempts = 0, LockedUntil = NULL
                WHERE UserID = ?
                """,
                (new_status, target_user_id),
            )
        return True, f"Account status updated to {new_status}."


class Administrator(User):
    def get_dashboard_endpoint(self) -> str:
        return "admin.dashboard"


class AcademicStaff(User):
    def get_dashboard_endpoint(self) -> str:
        return "staff.dashboard"


class LecturerAccount(User):
    def get_dashboard_endpoint(self) -> str:
        return "lecturer.dashboard"


class StudentAccount(User):
    def get_dashboard_endpoint(self) -> str:
        return "student.dashboard"
