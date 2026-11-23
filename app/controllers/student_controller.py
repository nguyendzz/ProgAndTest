from datetime import date
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from app.models.enrollment import Enrollment
from app.models.registration_cart import RegistrationCart
from app.models.semester_registration import SemesterRegistration
from app.models.student import Student
from app.models.waitlist import Waitlist
from app.utils.decorators import csrf_protect, role_required


student_bp = Blueprint("student", __name__, url_prefix="/student")


def _resolve_active_semester(db, requested_semester: str = "") -> tuple[str, dict | None, list[dict]]:
    with db.connection() as conn:
        periods = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM REGISTRATION_PERIODS ORDER BY PeriodID DESC"
            ).fetchall()
        ]
    if not periods:
        return requested_semester.strip(), None, []
    if requested_semester.strip():
        matched = next(
            (p for p in periods if p["Semester"] == requested_semester.strip()), None
        )
        if matched:
            return matched["Semester"], matched, periods
    open_period = next(
        (p for p in periods if p["Status"] in ("Open", "LateReg")), periods[0]
    )
    return open_period["Semester"], open_period, periods


@student_bp.route("/dashboard", methods=["GET"])
@role_required("Student")
def dashboard():
    db = current_app.extensions["db"]
    student = Student.find_by_user_id(db, session["user_id"])
    if not student:
        flash("Student profile not linked to this account.", "danger")
        return redirect(url_for("auth.portal_home"))

    semester, active_period, periods = _resolve_active_semester(
        db, request.args.get("semester", "")
    )
    search = request.args.get("search", "").strip()
    faculty_id = request.args.get("faculty_id", "").strip()
    day = request.args.get("day", "").strip()
    available_only = request.args.get("available_only") == "1"

    catalog = student.browseCourseCatalog(
        db,
        semester=semester,
        search=search,
        faculty_id=faculty_id,
        day=day,
        available_only=available_only,
    )
    cart_items = RegistrationCart.get_items(db, student.student_id, semester)
    waitlists = [
        w
        for w in Waitlist.get_student_waitlists(db, student.student_id, semester)
        if w["Status"] == "Waiting"
    ]
    credit_summary = student.getCreditSummary(db, semester)
    sem_reg = (
        SemesterRegistration.find_by_student_semester(db, student.student_id, semester)
        if semester
        else None
    )

    with db.connection() as conn:
        faculties = [
            dict(r)
            for r in conn.execute(
                "SELECT FacultyID, FacultyName FROM FACULTIES ORDER BY FacultyID ASC"
            ).fetchall()
        ]

    period_open = bool(active_period and active_period["Status"] in ("Open", "LateReg"))
    return render_template(
        "student/registration_portal.html",
        student=student,
        semester=semester,
        active_period=active_period,
        periods=periods,
        period_open=period_open,
        catalog=catalog,
        cart_items=cart_items,
        waitlists=waitlists,
        credit_summary=credit_summary,
        sem_reg=sem_reg,
        faculties=faculties,
        days=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat"),
        search=search,
        faculty_id=faculty_id,
        day=day,
        available_only=available_only,
    )


@student_bp.route("/cart/add", methods=["POST"])
@role_required("Student")
@csrf_protect
def add_to_cart():
    db = current_app.extensions["db"]
    student = Student.find_by_user_id(db, session["user_id"])
    semester = request.form.get("semester", "").strip()
    section_id = request.form.get("section_id", "").strip()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for("auth.portal_home"))
    ok, message = student.addToCart(db, section_id)
    flash(message, "success" if ok else "danger")
    return redirect(url_for("student.dashboard", semester=semester))


@student_bp.route("/cart/remove", methods=["POST"])
@role_required("Student")
@csrf_protect
def remove_from_cart():
    db = current_app.extensions["db"]
    student = Student.find_by_user_id(db, session["user_id"])
    semester = request.form.get("semester", "").strip()
    section_id = request.form.get("section_id", "").strip()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for("auth.portal_home"))
    ok, message = student.removeFromCart(db, section_id)
    flash(message, "info" if ok else "danger")
    return redirect(url_for("student.dashboard", semester=semester))


@student_bp.route("/checkout", methods=["POST"])
@role_required("Student")
@csrf_protect
def checkout():
    db = current_app.extensions["db"]
    student = Student.find_by_user_id(db, session["user_id"])
    semester = request.form.get("semester", "").strip()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for("auth.portal_home"))
    result = student.confirmRegistration(db, semester)
    flash(result["message"], "success" if result["ok"] else "danger")
    return redirect(url_for("student.dashboard", semester=semester))


@student_bp.route("/waitlist/join", methods=["POST"])
@role_required("Student")
@csrf_protect
def join_waitlist():
    db = current_app.extensions["db"]
    student = Student.find_by_user_id(db, session["user_id"])
    semester = request.form.get("semester", "").strip()
    section_id = request.form.get("section_id", "").strip()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for("auth.portal_home"))
    wl, message = student.joinWaitlist(db, section_id)
    flash(message, "success" if wl else "danger")
    return redirect(url_for("student.dashboard", semester=semester))


@student_bp.route("/waitlist/<int:waitlist_id>/cancel", methods=["POST"])
@role_required("Student")
@csrf_protect
def cancel_waitlist(waitlist_id: int):
    db = current_app.extensions["db"]
    student = Student.find_by_user_id(db, session["user_id"])
    semester = request.form.get("semester", "").strip()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for("auth.portal_home"))
    ok, message = Waitlist.cancel_by_id(db, waitlist_id, student.student_id)
    flash(message, "info" if ok else "danger")
    return redirect(url_for("student.history", semester=semester))


@student_bp.route("/history", methods=["GET"])
@role_required("Student")
def history():
    db = current_app.extensions["db"]
    student = Student.find_by_user_id(db, session["user_id"])
    if not student:
        flash("Student profile not linked to this account.", "danger")
        return redirect(url_for("auth.portal_home"))

    semester, active_period, periods = _resolve_active_semester(
        db, request.args.get("semester", "")
    )
    enrollments = Enrollment.get_registration_history(db, student.student_id, semester)
    waitlists = Waitlist.get_student_waitlists(db, student.student_id, semester)
    credit_summary = student.getCreditSummary(db, semester)
    sem_reg = (
        SemesterRegistration.find_by_student_semester(db, student.student_id, semester)
        if semester
        else None
    )

    today = date.today()
    action_mode = "closed"
    if active_period:
        drop_d = Enrollment._parse_date(active_period["DropDeadline"])
        withdraw_d = Enrollment._parse_date(active_period["WithdrawDeadline"])
        if today <= drop_d:
            action_mode = "drop"
        elif today <= withdraw_d:
            action_mode = "withdraw"

    return render_template(
        "student/history.html",
        student=student,
        semester=semester,
        active_period=active_period,
        periods=periods,
        enrollments=enrollments,
        waitlists=waitlists,
        credit_summary=credit_summary,
        sem_reg=sem_reg,
        action_mode=action_mode,
    )


@student_bp.route("/drop", methods=["POST"])
@role_required("Student")
@csrf_protect
def drop_course():
    db = current_app.extensions["db"]
    student = Student.find_by_user_id(db, session["user_id"])
    semester = request.form.get("semester", "").strip()
    section_id = request.form.get("section_id", "").strip()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for("auth.portal_home"))
    ok, message = student.dropCourse(db, section_id)
    flash(message, "success" if ok else "danger")
    return redirect(url_for("student.history", semester=semester))
