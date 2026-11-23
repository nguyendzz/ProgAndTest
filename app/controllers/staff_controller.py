from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from app.models.administrative_class import AdministrativeClass
from app.models.course_section import CourseSection
from app.models.faculty import Faculty
from app.models.registration_period import RegistrationPeriod
from app.models.student_profile import StudentProfileManager
from app.models.subject import Subject
from app.utils.decorators import csrf_protect, role_required


staff_bp = Blueprint("staff", __name__, url_prefix="/staff")


@staff_bp.route("/dashboard")
@role_required("Staff", "Admin")
def dashboard():
    db = current_app.extensions["db"]
    with db.connection() as conn:
        stats = {
            "total_faculties": conn.execute("SELECT COUNT(*) FROM FACULTIES").fetchone()[0],
            "total_classes": conn.execute("SELECT COUNT(*) FROM CLASSES").fetchone()[0],
            "total_subjects": conn.execute(
                "SELECT COUNT(*) FROM SUBJECTS WHERE Status = 'Active'"
            ).fetchone()[0],
            "total_students": conn.execute("SELECT COUNT(*) FROM STUDENTS").fetchone()[0],
            "open_sections": conn.execute(
                "SELECT COUNT(*) FROM COURSES WHERE Status = 'Open'"
            ).fetchone()[0],
            "active_periods": conn.execute(
                "SELECT COUNT(*) FROM REGISTRATION_PERIODS WHERE Status IN ('Open', 'LateReg')"
            ).fetchone()[0],
        }
    return render_template("staff/dashboard.html", stats=stats)


@staff_bp.route("/classes-faculties", methods=["GET"])
@role_required("Staff", "Admin")
def classes_faculties():
    db = current_app.extensions["db"]
    faculty_filter = request.args.get("faculty_id", "").strip()
    faculties = Faculty.get_all(db)
    classes = AdministrativeClass.get_all(db, faculty_id=faculty_filter)
    return render_template(
        "staff/classes_faculties.html",
        faculties=faculties,
        classes=classes,
        faculty_filter=faculty_filter,
    )


@staff_bp.route("/faculties/create", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def create_faculty():
    db = current_app.extensions["db"]
    faculty, message = Faculty.create(
        db,
        request.form.get("faculty_id", ""),
        request.form.get("faculty_name", ""),
    )
    flash(message, "success" if faculty else "danger")
    return redirect(url_for("staff.classes_faculties"))


@staff_bp.route("/faculties/<faculty_id>/update", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def update_faculty(faculty_id: str):
    db = current_app.extensions["db"]
    ok, message = Faculty.update(db, faculty_id, request.form.get("faculty_name", ""))
    flash(message, "success" if ok else "danger")
    return redirect(url_for("staff.classes_faculties"))


@staff_bp.route("/classes/create", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def create_class():
    db = current_app.extensions["db"]
    cls_obj, message = AdministrativeClass.create(
        db,
        request.form.get("class_id", ""),
        request.form.get("faculty_id", ""),
        request.form.get("class_name", ""),
        request.form.get("academic_year", ""),
    )
    flash(message, "success" if cls_obj else "danger")
    return redirect(url_for("staff.classes_faculties"))


@staff_bp.route("/classes/<class_id>/update", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def update_class(class_id: str):
    db = current_app.extensions["db"]
    ok, message = AdministrativeClass.update(
        db,
        class_id,
        request.form.get("faculty_id", ""),
        request.form.get("class_name", ""),
        request.form.get("academic_year", ""),
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("staff.classes_faculties"))


@staff_bp.route("/subjects", methods=["GET"])
@role_required("Staff", "Admin")
def subjects():
    db = current_app.extensions["db"]
    subject_list = Subject.get_all(db)
    return render_template("staff/subjects.html", subjects=subject_list)


@staff_bp.route("/subjects/create", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def create_subject():
    db = current_app.extensions["db"]
    sub, message = Subject.create(
        db,
        request.form.get("subject_id", ""),
        request.form.get("subject_name", ""),
        request.form.get("credits", ""),
        request.form.get("prerequisite_id", ""),
    )
    flash(message, "success" if sub else "danger")
    return redirect(url_for("staff.subjects"))


@staff_bp.route("/subjects/<subject_id>/update", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def update_subject(subject_id: str):
    db = current_app.extensions["db"]
    ok, message = Subject.update(
        db,
        subject_id,
        request.form.get("subject_name", ""),
        request.form.get("credits", ""),
        request.form.get("prerequisite_id", ""),
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("staff.subjects"))


@staff_bp.route("/subjects/<subject_id>/status", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def update_subject_status(subject_id: str):
    db = current_app.extensions["db"]
    ok, message = Subject.set_status(db, subject_id, request.form.get("status", ""))
    flash(message, "success" if ok else "danger")
    return redirect(url_for("staff.subjects"))


@staff_bp.route("/students", methods=["GET"])
@role_required("Staff", "Admin")
def students():
    db = current_app.extensions["db"]
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    class_filter = request.args.get("class_id", "").strip()
    pagination = StudentProfileManager.list_paginated(
        db,
        page=page,
        per_page=current_app.config["PER_PAGE"],
        search=search,
        class_filter=class_filter,
    )
    classes = AdministrativeClass.get_all(db)
    return render_template(
        "staff/students.html",
        pagination=pagination,
        classes=classes,
        search=search,
        class_filter=class_filter,
    )


@staff_bp.route("/students/create", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def create_student():
    db = current_app.extensions["db"]
    student, message = StudentProfileManager.create_student(
        db,
        request.form.get("student_id", ""),
        request.form.get("full_name", ""),
        request.form.get("dob", ""),
        request.form.get("email", ""),
        request.form.get("phone", ""),
        request.form.get("class_id", ""),
    )
    flash(message, "success" if student else "danger")
    return redirect(url_for("staff.students"))


@staff_bp.route("/students/<student_id>", methods=["GET"])
@role_required("Staff", "Admin")
def view_student(student_id: str):
    db = current_app.extensions["db"]
    student = StudentProfileManager.find_by_id(db, student_id)
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for("staff.students"))
    classes = AdministrativeClass.get_all(db)
    return render_template(
        "staff/student_detail.html",
        student=student,
        classes=classes,
        statuses=StudentProfileManager.VALID_STATUSES,
    )


@staff_bp.route("/students/<student_id>/update", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def update_student(student_id: str):
    db = current_app.extensions["db"]
    ok, message = StudentProfileManager.update_student(
        db,
        student_id,
        request.form.get("full_name", ""),
        request.form.get("dob", ""),
        request.form.get("email", ""),
        request.form.get("phone", ""),
        request.form.get("class_id", ""),
        request.form.get("status", "Active"),
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("staff.view_student", student_id=student_id))


@staff_bp.route("/students/<student_id>/deactivate", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def deactivate_student(student_id: str):
    db = current_app.extensions["db"]
    ok, message = StudentProfileManager.deactivate_profile(db, student_id)
    flash(message, "success" if ok else "danger")
    return redirect(url_for("staff.students"))


@staff_bp.route("/students/<student_id>/delete", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def delete_student(student_id: str):
    db = current_app.extensions["db"]
    ok, message = StudentProfileManager.delete_profile_if_no_history(db, student_id)
    flash(message, "success" if ok else "danger")
    return redirect(url_for("staff.students"))


@staff_bp.route("/sections", methods=["GET"])
@role_required("Staff", "Admin")
def sections():
    db = current_app.extensions["db"]
    semester_filter = request.args.get("semester", "").strip()
    section_list = CourseSection.get_all(db, semester=semester_filter)
    subjects_list = Subject.get_all(db)
    with db.connection() as conn:
        lecturers = [
            dict(r)
            for r in conn.execute(
                "SELECT LecturerID, FullName FROM LECTURERS ORDER BY LecturerID ASC"
            ).fetchall()
        ]
    periods = RegistrationPeriod.get_all(db)
    return render_template(
        "staff/sections.html",
        sections=section_list,
        subjects=subjects_list,
        lecturers=lecturers,
        periods=periods,
        days=CourseSection.VALID_DAYS,
        statuses=CourseSection.VALID_STATUSES,
        semester_filter=semester_filter,
    )


@staff_bp.route("/sections/create", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def create_section():
    db = current_app.extensions["db"]
    sec, message = CourseSection.open_section(
        db,
        request.form.get("section_id", ""),
        request.form.get("subject_id", ""),
        request.form.get("lecturer_id", ""),
        request.form.get("semester", ""),
        request.form.get("capacity", ""),
        request.form.get("day_of_week", ""),
        request.form.get("start_time", ""),
        request.form.get("end_time", ""),
        request.form.get("room", ""),
    )
    flash(message, "success" if sec else "danger")
    return redirect(url_for("staff.sections"))


@staff_bp.route("/sections/<section_id>/status", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def update_section_status(section_id: str):
    db = current_app.extensions["db"]
    ok, message = CourseSection.update_status(
        db, section_id, request.form.get("status", "")
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("staff.sections"))


@staff_bp.route("/periods", methods=["GET"])
@role_required("Staff", "Admin")
def periods():
    db = current_app.extensions["db"]
    period_list = RegistrationPeriod.get_all(db)
    return render_template(
        "staff/periods.html",
        periods=period_list,
        statuses=RegistrationPeriod.VALID_STATUSES,
    )


@staff_bp.route("/periods/create", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def create_period():
    db = current_app.extensions["db"]
    period, message = RegistrationPeriod.create(
        db,
        request.form.get("semester", ""),
        request.form.get("reg_open_date", ""),
        request.form.get("reg_close_date", ""),
        request.form.get("late_reg_deadline", ""),
        request.form.get("drop_deadline", ""),
        request.form.get("withdraw_deadline", ""),
        request.form.get("min_credits", 14),
        request.form.get("max_credits", 25),
        request.form.get("status", "Upcoming"),
    )
    flash(message, "success" if period else "danger")
    return redirect(url_for("staff.periods"))


@staff_bp.route("/periods/<int:period_id>/status", methods=["POST"])
@role_required("Staff", "Admin")
@csrf_protect
def update_period_status(period_id: int):
    db = current_app.extensions["db"]
    ok, message = RegistrationPeriod.update_status(
        db, period_id, request.form.get("status", "")
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("staff.periods"))
