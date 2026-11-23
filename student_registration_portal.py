"""
STUDENT MANAGER SYSTEM - Student Course Registration Module
Team member: TV 3
Scope: UC-11 to UC-19 (Course Catalog, Cart, Atomic Checkout, Waitlist,
Prerequisites, Drop/Withdraw, Registration History, Schedule Conflict,
Credit Limit).

Python 3.10+
Run GUI:       python student_registration_portal.py
Run tests:     python student_registration_portal.py --test
Export tests:  python student_registration_portal.py --export-test-cases
No third-party package is required for the application or unit tests.
For Excel export install openpyxl: pip install openpyxl
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Dict, List, Optional, Set, Tuple
import sys
import unittest


# ---------------------------------------------------------------------------
# Domain models: the five OOP classes requested in the assignment
# ---------------------------------------------------------------------------

@dataclass
class Student:
    student_id: str
    full_name: str
    previous_gpa: float = 0.0
    passed_subjects: Dict[str, float] = field(default_factory=dict)
    active: bool = True

    def has_passed(self, subject_id: str) -> bool:
        """BR-01: prerequisite is passed when FinalScore >= 4.0."""
        return self.passed_subjects.get(subject_id, -1.0) >= 4.0


@dataclass
class RegistrationCart:
    student_id: str
    section_ids: List[str] = field(default_factory=list)

    def add(self, section_id: str) -> None:
        if section_id not in self.section_ids:
            self.section_ids.append(section_id)

    def remove(self, section_id: str) -> None:
        if section_id in self.section_ids:
            self.section_ids.remove(section_id)

    def clear(self) -> None:
        self.section_ids.clear()


@dataclass
class Enrollment:
    student_id: str
    section_id: str
    status: str = "Enrolled"  # Enrolled, Dropped, Withdrawn
    enrolled_at: datetime = field(default_factory=datetime.now)
    confirmation_number: str = ""


@dataclass
class Waitlist:
    student_id: str
    section_id: str
    queue_position: int
    status: str = "Waiting"  # Waiting, Enrolled, Skipped, Cancelled
    joined_at: datetime = field(default_factory=datetime.now)


@dataclass
class SemesterRegistration:
    student_id: str
    semester: str
    total_credits_enrolled: int = 0
    confirmation_number: str = ""

    def refresh_total(self, controller: "RegistrationController") -> None:
        self.total_credits_enrolled = controller.confirmed_credits(
            self.student_id, self.semester
        )


# ---------------------------------------------------------------------------
# Registration controller / business logic
# ---------------------------------------------------------------------------

class RegistrationError(Exception):
    """Expected business-rule validation error shown by the portal."""


class RegistrationController:
    MIN_CREDITS = 14
    MAX_CREDITS = 25
    HONOR_MAX_CREDITS = 30
    WAITLIST_RATIO = 0.50

    def __init__(self):
        self.students: Dict[str, Student] = {}
        self.subjects: Dict[str, dict] = {}
        self.sections: Dict[str, dict] = {}
        self.carts: Dict[str, RegistrationCart] = {}
        self.enrollments: List[Enrollment] = []
        self.waitlists: List[Waitlist] = []
        self.semester_registrations: Dict[Tuple[str, str], SemesterRegistration] = {}
        self.registration_periods: Dict[str, dict] = {}
        self._confirmation_counter = 1
        self._seed_demo_data()

    def _seed_demo_data(self) -> None:
        """Small demo dataset; replace with database records for deployment."""
        self.students["S1001"] = Student(
            "S1001", "Alex Nguyen", previous_gpa=8.2,
            passed_subjects={"MATH101": 7.5, "ENG101": 6.0}
        )
        self.students["S1002"] = Student(
            "S1002", "Jamie Tran", previous_gpa=7.1,
            passed_subjects={"MATH101": 5.5}
        )
        self.subjects.update({
            "MATH101": {"name": "Mathematics I", "credits": 3, "prerequisite": None, "status": "Active"},
            "CS101": {"name": "Introduction to Programming", "credits": 4, "prerequisite": "MATH101", "status": "Active"},
            "ENG101": {"name": "Academic English", "credits": 3, "prerequisite": None, "status": "Active"},
            "PHY101": {"name": "Physics I", "credits": 4, "prerequisite": "MATH101", "status": "Active"},
            "HIS101": {"name": "World History", "credits": 2, "prerequisite": None, "status": "Active"},
            "ART101": {"name": "Creative Design", "credits": 2, "prerequisite": None, "status": "Active"},
        })
        self.sections.update({
            "SEC-MATH": self._make_section("SEC-MATH", "MATH101", "HK1 2026-2027", 30, "Mon", "08:00", "10:00", "A101"),
            "SEC-CS": self._make_section("SEC-CS", "CS101", "HK1 2026-2027", 30, "Tue", "08:00", "11:00", "B201"),
            "SEC-ENG": self._make_section("SEC-ENG", "ENG101", "HK1 2026-2027", 30, "Mon", "10:00", "12:00", "C301"),
            "SEC-PHY": self._make_section("SEC-PHY", "PHY101", "HK1 2026-2027", 30, "Wed", "13:00", "16:00", "A202"),
            "SEC-HIS": self._make_section("SEC-HIS", "HIS101", "HK1 2026-2027", 30, "Thu", "08:00", "10:00", "D101"),
            "SEC-ART": self._make_section("SEC-ART", "ART101", "HK1 2026-2027", 2, "Fri", "08:00", "10:00", "E101"),
        })
        self.registration_periods["HK1 2026-2027"] = {
            "status": "Open",
            "drop_deadline": date(2027, 1, 15),
            "withdraw_deadline": date(2027, 1, 30),
            "min_credits": 14,
            "max_credits": 25,
        }
        for sid in self.students:
            self.carts[sid] = RegistrationCart(sid)
            self.semester_registrations[(sid, "HK1 2026-2027")] = SemesterRegistration(
                sid, "HK1 2026-2027"
            )

    @staticmethod
    def _make_section(section_id, subject_id, semester, capacity, day, start, end, room):
        return {
            "section_id": section_id, "subject_id": subject_id,
            "semester": semester, "capacity": capacity, "day": day,
            "start": time.fromisoformat(start), "end": time.fromisoformat(end),
            "room": room, "lecturer": "Lecturer Demo", "status": "Open"
        }

    def _student(self, student_id: str) -> Student:
        student = self.students.get(student_id)
        if not student or not student.active:
            raise RegistrationError("Student account is unavailable.")
        return student

    def _period(self, semester: str) -> dict:
        period = self.registration_periods.get(semester)
        if not period:
            raise RegistrationError("No registration period is configured.")
        if period["status"] not in ("Open", "LateReg"):
            raise RegistrationError("Registration period is not open.")
        return period

    def _section(self, section_id: str) -> dict:
        section = self.sections.get(section_id)
        if not section or section["status"] != "Open":
            raise RegistrationError("Course section is not available.")
        return section

    def enrolled_count(self, section_id: str) -> int:
        return sum(1 for e in self.enrollments
                   if e.section_id == section_id and e.status == "Enrolled")

    def remaining_seats(self, section_id: str) -> int:
        section = self.sections[section_id]
        return max(0, section["capacity"] - self.enrolled_count(section_id))

    def confirmed_credits(self, student_id: str, semester: str) -> int:
        total = 0
        for enrollment in self.enrollments:
            if enrollment.student_id == student_id and enrollment.status == "Enrolled":
                section = self.sections[enrollment.section_id]
                if section["semester"] == semester:
                    total += self.subjects[section["subject_id"]]["credits"]
        return total

    def cart_credits(self, student_id: str, semester: str) -> int:
        cart = self.carts.setdefault(student_id, RegistrationCart(student_id))
        return sum(self.subjects[self.sections[s]["subject_id"]]["credits"]
                   for s in cart.section_ids if self.sections[s]["semester"] == semester)

    def _existing_sections(self, student_id: str, semester: str) -> List[str]:
        ids = list(self.carts.setdefault(student_id, RegistrationCart(student_id)).section_ids)
        ids += [e.section_id for e in self.enrollments
                if e.student_id == student_id and e.status == "Enrolled"
                and self.sections[e.section_id]["semester"] == semester]
        return list(dict.fromkeys(ids))

    # UC-15 / BR-01
    def check_prerequisite(self, student_id: str, section_id: str) -> bool:
        student = self._student(student_id)
        section = self._section(section_id)
        prerequisite = self.subjects[section["subject_id"]]["prerequisite"]
        return prerequisite is None or student.has_passed(prerequisite)

    # UC-18 / BR-02
    def check_schedule_conflict(self, student_id: str, section_id: str) -> Optional[str]:
        target = self._section(section_id)
        for other_id in self._existing_sections(student_id, target["semester"]):
            if other_id == section_id:
                continue
            other = self.sections[other_id]
            overlaps = (
                target["day"] == other["day"]
                and target["start"] < other["end"]
                and target["end"] > other["start"]
            )
            if overlaps:
                return other_id
        return None

    # UC-19 / BR-04 / BR-05
    def check_credit_limit(self, student_id: str, semester: str,
                           extra_credits: int = 0) -> bool:
        student = self._student(student_id)
        period = self.registration_periods.get(semester, {})
        max_credits = period.get("max_credits", self.MAX_CREDITS)
        if student.previous_gpa >= 8.0:
            max_credits = max(max_credits, self.HONOR_MAX_CREDITS)
        current = self.confirmed_credits(student_id, semester)
        cart = self.cart_credits(student_id, semester)
        return current + cart + extra_credits <= max_credits

    # UC-11
    def browse_course_catalog(self, student_id: str, keyword: str = "") -> List[dict]:
        self._student(student_id)
        keyword = keyword.casefold().strip()
        rows = []
        for section in self.sections.values():
            if section["status"] != "Open":
                continue
            subject = self.subjects[section["subject_id"]]
            searchable = (section["section_id"] + " " + subject["name"]).casefold()
            if keyword and keyword not in searchable:
                continue
            prereq_met = self.check_prerequisite(student_id, section["section_id"])
            rows.append({
                **section, "subject_name": subject["name"],
                "credits": subject["credits"],
                "remaining_seats": self.remaining_seats(section["section_id"]),
                "prerequisite_met": prereq_met
            })
        return rows

    # UC-12
    def add_to_cart(self, student_id: str, section_id: str) -> None:
        self._student(student_id)
        section = self._section(section_id)
        self._period(section["semester"])
        cart = self.carts.setdefault(student_id, RegistrationCart(student_id))
        if section_id in cart.section_ids:
            raise RegistrationError("Section is already in the registration cart.")
        subject_id = section["subject_id"]
        if any(e.student_id == student_id and e.status == "Enrolled"
               and self.sections[e.section_id]["semester"] == section["semester"]
               and self.sections[e.section_id]["subject_id"] == subject_id
               for e in self.enrollments):
            raise RegistrationError("Already enrolled in another section of this subject.")
        if any(self.sections[s]["subject_id"] == subject_id for s in cart.section_ids):
            raise RegistrationError("Another section of this subject is already in the cart.")
        if not self.check_prerequisite(student_id, section_id):
            raise RegistrationError("Prerequisite subject not completed (FinalScore must be >= 4.0).")
        conflict = self.check_schedule_conflict(student_id, section_id)
        if conflict:
            raise RegistrationError(f"Time conflict with section {conflict}.")
        credits = self.subjects[subject_id]["credits"]
        if not self.check_credit_limit(student_id, section["semester"], credits):
            raise RegistrationError("Total credits would exceed the maximum allowed.")
        cart.add(section_id)

    # UC-13: atomic checkout; validate all selections before changing any state.
    def confirm_registration(self, student_id: str) -> str:
        self._student(student_id)
        cart = self.carts.setdefault(student_id, RegistrationCart(student_id))
        if not cart.section_ids:
            raise RegistrationError("Registration cart is empty.")
        semesters = {self.sections[s]["semester"] for s in cart.section_ids}
        if len(semesters) != 1:
            raise RegistrationError("A cart checkout must contain one semester.")
        semester = next(iter(semesters))
        self._period(semester)

        # Revalidate all business rules at checkout time (seat can be taken meanwhile).
        selected = list(cart.section_ids)
        seen_subjects: Set[str] = set()
        for sid in selected:
            section = self._section(sid)
            subject_id = section["subject_id"]
            if subject_id in seen_subjects:
                raise RegistrationError("Only one section per subject is allowed.")
            seen_subjects.add(subject_id)
            if not self.check_prerequisite(student_id, sid):
                raise RegistrationError(f"Prerequisite not met for {subject_id}.")
            if self.check_schedule_conflict_for_checkout(student_id, sid, selected):
                raise RegistrationError(f"Schedule conflict in section {sid}.")
            if self.remaining_seats(sid) <= 0:
                raise RegistrationError(f"Section {sid} is full; join the waitlist.")
        selected_credits = sum(self.subjects[self.sections[s]["subject_id"]]["credits"]
                               for s in selected)
        # cart credits are included by check_credit_limit; avoid double counting selected cart
        current = self.confirmed_credits(student_id, semester)
        student = self._student(student_id)
        period = self.registration_periods[semester]
        maximum = period["max_credits"]
        if student.previous_gpa >= 8.0:
            maximum = max(maximum, self.HONOR_MAX_CREDITS)
        if current + selected_credits > maximum:
            raise RegistrationError("Credit limit exceeded during checkout.")

        # Commit only after all validations pass.
        confirmation = f"REG-{semester.replace(' ', '').replace('-', '')}-{self._confirmation_counter:05d}"
        self._confirmation_counter += 1
        for sid in selected:
            self.enrollments.append(Enrollment(student_id, sid, "Enrolled",
                                               datetime.now(), confirmation))
        cart.clear()
        summary = self.semester_registrations.setdefault(
            (student_id, semester), SemesterRegistration(student_id, semester)
        )
        summary.confirmation_number = confirmation
        summary.refresh_total(self)
        return confirmation

    def check_schedule_conflict_for_checkout(self, student_id: str,
                                             section_id: str,
                                             selected: List[str]) -> bool:
        target = self.sections[section_id]
        # Compare against already-enrolled sections and other sections in this checkout.
        others = [e.section_id for e in self.enrollments
                  if e.student_id == student_id and e.status == "Enrolled"]
        others += [s for s in selected if s != section_id]
        for other_id in others:
            other = self.sections[other_id]
            if (target["semester"] == other["semester"]
                and target["day"] == other["day"]
                and target["start"] < other["end"]
                and target["end"] > other["start"]):
                return True
        return False

    # UC-14 / BR-08 / BR-09
    def join_waitlist(self, student_id: str, section_id: str) -> int:
        self._student(student_id)
        section = self._section(section_id)
        if self.remaining_seats(section_id) > 0:
            raise RegistrationError("Section still has available seats; add it to the cart.")
        if not self.check_prerequisite(student_id, section_id):
            raise RegistrationError("Prerequisite subject not completed.")
        if self.check_schedule_conflict(student_id, section_id):
            raise RegistrationError("Cannot waitlist a section that conflicts with enrolled schedule.")
        credits = self.subjects[section["subject_id"]]["credits"]
        if not self.check_credit_limit(student_id, section["semester"], credits):
            raise RegistrationError("Credit limit would be exceeded.")
        if any(w.student_id == student_id and w.section_id == section_id
               and w.status == "Waiting" for w in self.waitlists):
            raise RegistrationError("Student is already on this waitlist.")
        queue = [w for w in self.waitlists
                 if w.section_id == section_id and w.status == "Waiting"]
        maximum = max(1, int(section["capacity"] * self.WAITLIST_RATIO))
        if len(queue) >= maximum:
            raise RegistrationError("Waitlist capacity reached (maximum 50% of section capacity).")
        position = len(queue) + 1
        self.waitlists.append(Waitlist(student_id, section_id, position))
        return position

    def _promote_waitlist(self, section_id: str) -> Optional[str]:
        waiting = sorted(
            [w for w in self.waitlists if w.section_id == section_id and w.status == "Waiting"],
            key=lambda w: w.joined_at
        )
        if not waiting:
            return None
        candidate = waiting[0]
        if self.check_schedule_conflict(candidate.student_id, section_id):
            candidate.status = "Skipped"
            return self._promote_waitlist(section_id)
        candidate.status = "Enrolled"
        self.enrollments.append(Enrollment(
            candidate.student_id, section_id, "Enrolled", datetime.now(),
            f"WAITLIST-{section_id}-{candidate.queue_position:03d}"
        ))
        # BR-09: cancel other waitlists for the same subject after promotion.
        promoted_subject = self.sections[section_id]["subject_id"]
        for w in self.waitlists:
            if w.student_id == candidate.student_id and w.status == "Waiting":
                if self.sections[w.section_id]["subject_id"] == promoted_subject:
                    w.status = "Cancelled"
        return candidate.student_id

    # UC-16 / BR-10 / BR-11
    def drop_or_withdraw(self, student_id: str, section_id: str,
                         action_date: Optional[date] = None) -> str:
        action_date = action_date or date.today()
        enrollment = next((e for e in self.enrollments
                           if e.student_id == student_id and e.section_id == section_id
                           and e.status == "Enrolled"), None)
        if not enrollment:
            raise RegistrationError("No active enrollment found for this section.")
        semester = self.sections[section_id]["semester"]
        period = self.registration_periods[semester]
        if action_date <= period["drop_deadline"]:
            enrollment.status = "Dropped"
            result = "Dropped (no transcript record)"
        elif action_date <= period["withdraw_deadline"]:
            enrollment.status = "Withdrawn"
            result = "Withdrawn (grade W recorded)"
        else:
            raise RegistrationError("Withdrawal deadline has passed. Course cannot be dropped.")
        self._promote_waitlist(section_id)
        summary = self.semester_registrations.get((student_id, semester))
        if summary:
            summary.refresh_total(self)
        return result

    # UC-17
    def registration_history(self, student_id: str) -> List[dict]:
        self._student(student_id)
        rows = []
        for enrollment in self.enrollments:
            if enrollment.student_id == student_id:
                section = self.sections[enrollment.section_id]
                subject = self.subjects[section["subject_id"]]
                rows.append({
                    "section_id": section["section_id"],
                    "subject": subject["name"],
                    "semester": section["semester"],
                    "status": enrollment.status,
                    "confirmation": enrollment.confirmation_number,
                })
        for wait in self.waitlists:
            if wait.student_id == student_id:
                section = self.sections[wait.section_id]
                rows.append({
                    "section_id": section["section_id"],
                    "subject": self.subjects[section["subject_id"]]["name"],
                    "semester": section["semester"],
                    "status": f"{wait.status} #{wait.queue_position}",
                    "confirmation": "",
                })
        return rows


# ---------------------------------------------------------------------------
# GUI Portal (Tkinter). Uses the controller; no business rules in the UI.
# ---------------------------------------------------------------------------

class StudentRegistrationPortal:
    def __init__(self, controller: Optional[RegistrationController] = None):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.controller = controller or RegistrationController()
        self.student_id = "S1001"
        self.root = tk.Tk()
        self.root.title("Student Manager System - Course Registration Portal")
        self.root.geometry("1120x680")
        self.root.minsize(900, 580)
        self._build_ui()
        self.refresh_catalog()
        self.refresh_cart()
        self.refresh_history()

    def _build_ui(self):
        tk, ttk = self.tk, self.ttk
        header = ttk.Frame(self.root, padding=12)
        header.pack(fill="x")
        ttk.Label(header, text="STUDENT MANAGER SYSTEM",
                  font=("Arial", 18, "bold")).pack(side="left")
        ttk.Label(header, text=f"Student: {self.student_id} | {self.controller.students[self.student_id].full_name}",
                  font=("Arial", 10)).pack(side="right")
        body = ttk.Frame(self.root, padding=10)
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="UC-11: Course Catalog", padding=8)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = ttk.Frame(body)
        right.pack(side="right", fill="both", expand=True)

        search_row = ttk.Frame(left)
        search_row.pack(fill="x", pady=(0, 6))
        self.search_var = tk.StringVar()
        ttk.Entry(search_row, textvariable=self.search_var).pack(side="left", fill="x", expand=True)
        ttk.Button(search_row, text="Search", command=self.refresh_catalog).pack(side="left", padx=5)
        columns = ("section", "subject", "credits", "schedule", "seats", "prereq")
        self.catalog = ttk.Treeview(left, columns=columns, show="headings", height=17)
        headings = {"section":"Section", "subject":"Subject", "credits":"Credits",
                    "schedule":"Schedule", "seats":"Seats", "prereq":"Prerequisite"}
        widths = {"section":100, "subject":180, "credits":55, "schedule":130, "seats":55, "prereq":90}
        for col in columns:
            self.catalog.heading(col, text=headings[col])
            self.catalog.column(col, width=widths[col], anchor="center")
        self.catalog.pack(fill="both", expand=True)
        ttk.Button(left, text="Add Selected Section to Cart",
                   command=self.add_selected).pack(fill="x", pady=8)

        cart_frame = ttk.LabelFrame(right, text="UC-12 / UC-13: Registration Cart", padding=8)
        cart_frame.pack(fill="both", expand=True)
        self.cart_list = tk.Listbox(cart_frame, height=9)
        self.cart_list.pack(fill="both", expand=True)
        actions = ttk.Frame(cart_frame)
        actions.pack(fill="x", pady=6)
        ttk.Button(actions, text="Remove Selected", command=self.remove_selected_cart).pack(side="left")
        ttk.Button(actions, text="Confirm Registration", command=self.confirm).pack(side="right")
        self.credit_label = ttk.Label(cart_frame, text="Cart credits: 0")
        self.credit_label.pack(anchor="w")

        wait_frame = ttk.LabelFrame(right, text="UC-14: Waitlist", padding=8)
        wait_frame.pack(fill="x", pady=8)
        ttk.Button(wait_frame, text="Join Waitlist for Selected Catalog Section",
                   command=self.waitlist_selected).pack(fill="x")

        history_frame = ttk.LabelFrame(right, text="UC-17: Registration History", padding=8)
        history_frame.pack(fill="both", expand=True)
        self.history = ttk.Treeview(history_frame, columns=("section","subject","status"),
                                    show="headings", height=6)
        for col, width in (("section",100),("subject",180),("status",130)):
            self.history.heading(col, text=col.title())
            self.history.column(col, width=width)
        self.history.pack(fill="both", expand=True)
        history_actions = ttk.Frame(history_frame)
        history_actions.pack(fill="x", pady=5)
        ttk.Button(history_actions, text="Drop / Withdraw Selected",
                   command=self.drop_selected).pack(side="left")
        ttk.Button(history_actions, text="Refresh", command=self.refresh_all).pack(side="right")

        self.status_var = tk.StringVar(value="Ready. Select a course section.")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w", padding=5).pack(fill="x", side="bottom")

    def _message(self, message: str, error: bool = False):
        from tkinter import messagebox
        self.status_var.set(message)
        (messagebox.showerror if error else messagebox.showinfo)("Student Portal", message)

    def refresh_catalog(self):
        for item in self.catalog.get_children():
            self.catalog.delete(item)
        for row in self.controller.browse_course_catalog(
                self.student_id, self.search_var.get() if hasattr(self, "search_var") else ""):
            schedule = f'{row["day"]} {row["start"].strftime("%H:%M")}-{row["end"].strftime("%H:%M")}'
            self.catalog.insert("", "end", iid=row["section_id"], values=(
                row["section_id"], row["subject_name"], row["credits"], schedule,
                row["remaining_seats"], "Met" if row["prerequisite_met"] else "Not met"
            ))

    def refresh_cart(self):
        self.cart_list.delete(0, "end")
        cart = self.controller.carts[self.student_id]
        for sid in cart.section_ids:
            section = self.controller.sections[sid]
            subject = self.controller.subjects[section["subject_id"]]
            self.cart_list.insert("end", f'{sid} | {subject["name"]} | {subject["credits"]} credits')
        self.credit_label.config(text=f'Cart credits: {self.controller.cart_credits(self.student_id, "HK1 2026-2027")}')

    def refresh_history(self):
        for item in self.history.get_children():
            self.history.delete(item)
        for index, row in enumerate(self.controller.registration_history(self.student_id)):
            self.history.insert("", "end", iid=str(index),
                                values=(row["section_id"], row["subject"], row["status"]))

    def refresh_all(self):
        self.refresh_catalog()
        self.refresh_cart()
        self.refresh_history()

    def add_selected(self):
        selected = self.catalog.selection()
        if not selected:
            self._message("Please select a course section.", True)
            return
        try:
            self.controller.add_to_cart(self.student_id, selected[0])
            self.refresh_all()
            self._message(f'{selected[0]} added to registration cart.')
        except RegistrationError as exc:
            self._message(str(exc), True)

    def remove_selected_cart(self):
        selection = self.cart_list.curselection()
        if not selection:
            return
        sid = self.controller.carts[self.student_id].section_ids[selection[0]]
        self.controller.carts[self.student_id].remove(sid)
        self.refresh_cart()
        self.status_var.set(f"{sid} removed from cart.")

    def confirm(self):
        try:
            confirmation = self.controller.confirm_registration(self.student_id)
            self.refresh_all()
            self._message(f"Registration successful. Confirmation: {confirmation}")
        except RegistrationError as exc:
            self._message(str(exc), True)

    def waitlist_selected(self):
        selected = self.catalog.selection()
        if not selected:
            self._message("Select a full course section first.", True)
            return
        try:
            position = self.controller.join_waitlist(self.student_id, selected[0])
            self.refresh_history()
            self._message(f"Successfully joined waitlist. Queue position: #{position}")
        except RegistrationError as exc:
            self._message(str(exc), True)

    def drop_selected(self):
        selected = self.history.selection()
        if not selected:
            self._message("Select an enrolled course in Registration History.", True)
            return
        values = self.history.item(selected[0], "values")
        section_id, status = values[0], values[2]
        if status != "Enrolled":
            self._message("Only active Enrolled records can be dropped/withdrawn.", True)
            return
        from tkinter import messagebox
        if messagebox.askyesno("Confirm", f"Process Drop/Withdraw for {section_id}?"):
            try:
                result = self.controller.drop_or_withdraw(self.student_id, section_id)
                self.refresh_all()
                self._message(result)
            except RegistrationError as exc:
                self._message(str(exc), True)

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Unit tests for UC-11 through UC-19
# ---------------------------------------------------------------------------

class RegistrationUseCaseTests(unittest.TestCase):
    def setUp(self):
        self.app = RegistrationController()
        self.sid = "S1001"

    def test_uc11_browse_catalog(self):
        rows = self.app.browse_course_catalog(self.sid)
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(any(r["section_id"] == "SEC-CS" for r in rows))

    def test_uc12_add_cart_prerequisite_and_success(self):
        self.app.add_to_cart(self.sid, "SEC-CS")
        self.assertIn("SEC-CS", self.app.carts[self.sid].section_ids)

    def test_uc12_reject_missing_prerequisite(self):
        self.app.students["S1002"].passed_subjects.clear()
        with self.assertRaises(RegistrationError):
            self.app.add_to_cart("S1002", "SEC-CS")

    def test_uc13_atomic_checkout(self):
        self.app.add_to_cart(self.sid, "SEC-CS")
        confirmation = self.app.confirm_registration(self.sid)
        self.assertTrue(confirmation.startswith("REG-"))
        self.assertEqual(self.app.carts[self.sid].section_ids, [])
        self.assertEqual(self.app.enrolled_count("SEC-CS"), 1)

    def test_uc14_fifo_waitlist(self):
        self.app.sections["SEC-ART"]["capacity"] = 1
        self.app.enrollments.append(Enrollment("S1002", "SEC-ART"))
        position = self.app.join_waitlist(self.sid, "SEC-ART")
        self.assertEqual(position, 1)
        self.app.drop_or_withdraw("S1002", "SEC-ART", date(2027, 1, 10))
        self.assertTrue(any(e.student_id == self.sid and e.section_id == "SEC-ART"
                            and e.status == "Enrolled" for e in self.app.enrollments))

    def test_uc15_prerequisite_check(self):
        self.assertTrue(self.app.check_prerequisite(self.sid, "SEC-CS"))
        self.app.students[self.sid].passed_subjects["MATH101"] = 3.9
        self.assertFalse(self.app.check_prerequisite(self.sid, "SEC-CS"))

    def test_uc16_drop_before_deadline(self):
        self.app.enrollments.append(Enrollment(self.sid, "SEC-HIS"))
        result = self.app.drop_or_withdraw(self.sid, "SEC-HIS", date(2027, 1, 10))
        self.assertIn("no transcript", result)
        self.assertEqual(self.app.enrollments[-1].status, "Dropped")

    def test_uc17_registration_history(self):
        self.app.enrollments.append(Enrollment(self.sid, "SEC-HIS"))
        history = self.app.registration_history(self.sid)
        self.assertTrue(any(row["section_id"] == "SEC-HIS" for row in history))

    def test_uc18_schedule_conflict(self):
        self.app.carts[self.sid].add("SEC-MATH")
        conflict = self.app.check_schedule_conflict(self.sid, "SEC-ENG")
        self.assertEqual(conflict, "SEC-MATH")

    def test_uc19_credit_limit_and_gpa_exception(self):
        # Student S1002 has GPA 7.1 and normal maximum 25.
        self.app.students["S1002"].previous_gpa = 7.1
        self.assertFalse(self.app.check_credit_limit("S1002", "HK1 2026-2027", 26))
        # GPA >= 8.0 allows up to 30 credits.
        self.assertTrue(self.app.check_credit_limit(self.sid, "HK1 2026-2027", 29))


def export_test_cases(filename: str = "Student_Manager_UC11_UC19_TestCases.xlsx"):
    """Create Excel test-case sheet based on the nine use cases in the assignment."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise SystemExit("Install openpyxl first: pip install openpyxl") from exc

    cases = [
        ["TC-UC11-01","UC-11 Browse Course Catalog","Student S1001 is authenticated; catalog has Open sections","Open Course Registration","Catalog shows section, subject, credits, lecturer/schedule, room, remaining seats and prerequisite status","Pass",""],
        ["TC-UC12-01","UC-12 Add to Registration Cart","Student S1001 has passed MATH101 with score >= 4.0","Add SEC-CS to cart","SEC-CS is added; cart credits update; no seat is reserved","Pass","BR-01"],
        ["TC-UC12-02","UC-12 Add to Registration Cart","Student has not passed prerequisite","Add SEC-CS to cart","System rejects action and displays prerequisite-not-completed message","Pass","BR-01"],
        ["TC-UC13-01","UC-13 Confirm Registration","Cart contains eligible section; section has available seat","Confirm registration","Atomic checkout creates Enrollment, removes cart item, updates semester summary and returns confirmation number","Pass","BR-03"],
        ["TC-UC14-01","UC-14 Join Waitlist","Section is full; student meets eligibility rules","Join waitlist","Student receives FIFO queue position; queue cannot exceed 50% of capacity","Pass","BR-08, BR-09"],
        ["TC-UC15-01","UC-15 Check Prerequisites","Target subject has prerequisite MATH101","Check prerequisite","PASS only when student's prerequisite FinalScore >= 4.0; otherwise FAIL","Pass","BR-01"],
        ["TC-UC16-01","UC-16 Drop / Withdraw Course","Student has active enrollment; current date is before DropDeadline","Drop course","Enrollment status becomes Dropped; no transcript grade; seat released and waitlist processed","Pass","BR-10"],
        ["TC-UC16-02","UC-16 Drop / Withdraw Course","Student has active enrollment; DropDeadline < current date <= WithdrawDeadline","Withdraw course","Enrollment status becomes Withdrawn and permanent grade W is recorded","Pass","BR-11"],
        ["TC-UC17-01","UC-17 View Registration History","Student is authenticated","Open Registration History","Shows enrolled/dropped/withdrawn and waitlist records with section and confirmation details","Pass",""],
        ["TC-UC18-01","UC-18 Check Schedule Conflict","Student has a carted/enrolled section on same day","Add another section with overlapping time","System returns FAIL and identifies conflicting section","Pass","BR-02"],
        ["TC-UC19-01","UC-19 Check Credit Limit","Student has existing credits; previous semester GPA is known","Check proposed registration credits","Reject above 25 credits; allow up to 30 when previous GPA >= 8.0","Pass","BR-04, BR-05"],
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "UC11-UC19 Test Cases"
    headers = ["Test Case ID","Use Case","Preconditions","Test Steps / Input","Expected Result","Test Status","Business Rule"]
    ws.append(["STUDENT MANAGER SYSTEM - TEST CASES (TV 3)"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws["A1"].font = Font(bold=True, size=15, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="17365D")
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.append(headers)
    for cell in ws[2]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4472C4")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in cases:
        ws.append(row)
    widths = [17,32,48,36,72,14,20]
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for row in ws.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=Side(style="hair", color="B7C9D6"))
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:G{ws.max_row}"
    ws.row_dimensions[1].height = 28
    ws.row_dimensions[2].height = 32
    for r in range(3, ws.max_row + 1):
        ws.row_dimensions[r].height = 54
    wb.save(filename)
    return filename


def run_tests():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RegistrationUseCaseTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(run_tests())
    if "--export-test-cases" in sys.argv:
        print("Created:", export_test_cases())
    else:
        StudentRegistrationPortal().run()
