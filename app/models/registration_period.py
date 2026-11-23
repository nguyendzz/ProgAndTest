from datetime import date, datetime
from typing import Optional


class RegistrationPeriod:
    VALID_STATUSES = ("Upcoming", "Open", "LateReg", "Closed")

    def __init__(
        self,
        period_id: Optional[int],
        semester: str,
        reg_open_date: str,
        reg_close_date: str,
        late_reg_deadline: Optional[str],
        drop_deadline: str,
        withdraw_deadline: str,
        min_credits: int = 14,
        max_credits: int = 25,
        status: str = "Upcoming",
    ):
        self._periodId = period_id
        self._semester = semester
        self._regOpenDate = reg_open_date
        self._regCloseDate = reg_close_date
        self._lateRegDeadline = late_reg_deadline
        self._dropDeadline = drop_deadline
        self._withdrawDeadline = withdraw_deadline
        self._minCredits = min_credits
        self._maxCredits = max_credits
        self._status = status

    @property
    def period_id(self) -> Optional[int]:
        return self._periodId

    @property
    def semester(self) -> str:
        return self._semester

    @property
    def reg_open_date(self) -> str:
        return self._regOpenDate

    @property
    def reg_close_date(self) -> str:
        return self._regCloseDate

    @property
    def late_reg_deadline(self) -> Optional[str]:
        return self._lateRegDeadline

    @property
    def drop_deadline(self) -> str:
        return self._dropDeadline

    @property
    def withdraw_deadline(self) -> str:
        return self._withdrawDeadline

    @property
    def min_credits(self) -> int:
        return self._minCredits

    @property
    def max_credits(self) -> int:
        return self._maxCredits

    @property
    def status(self) -> str:
        return self._status

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        cleaned = value.strip().replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        raise ValueError(f"Invalid datetime format: {value}")

    @staticmethod
    def _parse_date(value: str) -> date:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()

    def isOpen(self, now: Optional[datetime] = None) -> bool:
        if self._status in ("Closed", "Upcoming"):
            return False
        current = now or datetime.now()
        open_dt = self._parse_dt(self._regOpenDate)
        close_dt = self._parse_dt(self._regCloseDate)
        return open_dt <= current <= close_dt

    def isLateReg(self, now: Optional[datetime] = None) -> bool:
        if self._status == "Closed" or not self._lateRegDeadline:
            return False
        current = now or datetime.now()
        close_dt = self._parse_dt(self._regCloseDate)
        late_dt = self._parse_dt(self._lateRegDeadline)
        return close_dt < current <= late_dt

    def isDropAllowed(self, today: Optional[date] = None) -> bool:
        current = today or date.today()
        return current <= self._parse_date(self._dropDeadline)

    def isWithdrawAllowed(self, today: Optional[date] = None) -> bool:
        current = today or date.today()
        return self._parse_date(self._dropDeadline) < current <= self._parse_date(
            self._withdrawDeadline
        )

    @classmethod
    def from_row(cls, row) -> Optional["RegistrationPeriod"]:
        if row is None:
            return None
        return cls(
            period_id=row["PeriodID"],
            semester=row["Semester"],
            reg_open_date=row["RegOpenDate"],
            reg_close_date=row["RegCloseDate"],
            late_reg_deadline=row["LateRegDeadline"],
            drop_deadline=row["DropDeadline"],
            withdraw_deadline=row["WithdrawDeadline"],
            min_credits=row["MinCredits"],
            max_credits=row["MaxCredits"],
            status=row["Status"],
        )

    @classmethod
    def get_all(cls, db) -> list["RegistrationPeriod"]:
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM REGISTRATION_PERIODS ORDER BY PeriodID DESC"
            ).fetchall()
        return [cls.from_row(r) for r in rows]

    @classmethod
    def find_by_semester(cls, db, semester: str) -> Optional["RegistrationPeriod"]:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM REGISTRATION_PERIODS WHERE Semester = ?",
                (semester.strip(),),
            ).fetchone()
        return cls.from_row(row)

    @classmethod
    def create(
        cls,
        db,
        semester: str,
        reg_open_date: str,
        reg_close_date: str,
        late_reg_deadline: Optional[str],
        drop_deadline: str,
        withdraw_deadline: str,
        min_credits: int = 14,
        max_credits: int = 25,
        status: str = "Upcoming",
    ) -> tuple[Optional["RegistrationPeriod"], str]:
        sem = semester.strip()
        if not sem or not reg_open_date or not reg_close_date or not drop_deadline or not withdraw_deadline:
            return None, "All required registration period fields must be provided."
        if status not in cls.VALID_STATUSES:
            return None, "Invalid registration period status."
        try:
            open_dt = cls._parse_dt(reg_open_date)
            close_dt = cls._parse_dt(reg_close_date)
            late_dt = cls._parse_dt(late_reg_deadline) if late_reg_deadline and late_reg_deadline.strip() else None
            drop_d = cls._parse_date(drop_deadline)
            withdraw_d = cls._parse_date(withdraw_deadline)
        except ValueError:
            return None, "Invalid date or timestamp format."
        if not (open_dt < close_dt):
            return None, "RegOpenDate must be earlier than RegCloseDate."
        if late_dt and close_dt > late_dt:
            return None, "RegCloseDate must be earlier than or equal to LateRegDeadline."
        if drop_d > withdraw_d:
            return None, "DropDeadline must be earlier than or equal to WithdrawDeadline."
        try:
            min_c = int(min_credits)
            max_c = int(max_credits)
        except (TypeError, ValueError):
            return None, "Credit limits must be valid integers."
        if min_c < 0 or max_c < min_c:
            return None, "MaxCredits must be greater than or equal to MinCredits."

        with db.connection() as conn:
            if conn.execute(
                "SELECT 1 FROM REGISTRATION_PERIODS WHERE Semester = ?", (sem,)
            ).fetchone():
                return None, "Period already exists."
            late_str = late_dt.strftime("%Y-%m-%d %H:%M:%S") if late_dt else None
            conn.execute(
                """
                INSERT INTO REGISTRATION_PERIODS (
                    Semester, RegOpenDate, RegCloseDate, LateRegDeadline,
                    DropDeadline, WithdrawDeadline, MinCredits, MaxCredits, Status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sem,
                    open_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    close_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    late_str,
                    drop_d.strftime("%Y-%m-%d"),
                    withdraw_d.strftime("%Y-%m-%d"),
                    min_c,
                    max_c,
                    status,
                ),
            )
        return cls.find_by_semester(db, sem), "Registration period created successfully."

    @classmethod
    def update_status(cls, db, period_id: int, status: str) -> tuple[bool, str]:
        if status not in cls.VALID_STATUSES:
            return False, "Invalid registration period status."
        with db.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM REGISTRATION_PERIODS WHERE PeriodID = ?", (period_id,)
            ).fetchone():
                return False, "Registration period not found."
            conn.execute(
                "UPDATE REGISTRATION_PERIODS SET Status = ? WHERE PeriodID = ?",
                (status, period_id),
            )
        return True, f"Registration period status updated to {status}."
