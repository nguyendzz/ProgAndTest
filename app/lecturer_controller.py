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
from app.models.grade import Grade
from app.models.lecturer import Lecturer
from app.models.report_service import ReportService
from app.utils.decorators import csrf_protect, login_required, role_required


lecturer_bp = Blueprint("lecturer", __name__, url_prefix="/lecturer")
academic_bp = Blueprint("academic", __name__, url_prefix="/academic")


@lecturer_bp.route("/dashboard")
@role_required("Lecturer", "Admin")
def dashboard():
    db = current_app.extensions["db"]
    lecturer = Lecturer.find_by_user_id(db, session["user_id"])
    sections = lecturer.viewAssignedSections(db) if lecturer else []
    total_students = sum(s["EnrolledCount"] for s in sections)
    return render_template(
        "lecturer/dashboard.html",
        lecturer=lecturer,
        sections=sections,
        total_students=total_students,
    )


@lecturer_bp.route("/schedule")
@role_required("Lecturer")
def schedule():
    db = current_app.extensions["db"]
    semester = request.args.get("semester", "").strip()
    schedule_data = ReportService.get_weekly_schedule(
        db, "Lecturer", session["user_id"], semester=semester
    )
    return render_template(
        "lecturer/schedule.html",
        schedule_data=schedule_data,
        selected_semester=semester,
        portal_title="Teaching Schedule (UC-23)",
    )


@lecturer_bp.route("/grades", methods=["GET", "POST"])
@role_required("Lecturer")
@csrf_protect
def grade_entry():
    db = current_app.extensions["db"]
    lecturer = Lecturer.find_by_user_id(db, session["user_id"])
    if not lecturer:
        flash("Lecturer profile not linked to this account.", "danger")
        return redirect(url_for("lecturer.dashboard"))

    sections = lecturer.viewAssignedSections(db)
    selected_section_id = (
        request.form.get("section_id")
        or request.args.get("section_id")
        or (sections[0]["SectionID"] if sections else "")
    )

    if request.method == "POST" and selected_section_id:
        action = request.form.get("action", "compute")
        save_as_draft = action == "draft"
        enrollment_ids = request.form.getlist("enrollment_id")
        errors = []
        saved_count = 0
        for eid_str in enrollment_ids:
            try:
                eid = int(eid_str)
            except ValueError:
                continue
            att = request.form.get(f"attendance_{eid}", "")
            mid = request.form.get(f"midterm_{eid}", "")
            fin = request.form.get(f"final_exam_{eid}", "")
            if att.strip() == "" and mid.strip() == "" and fin.strip() == "":
                continue
            grade_obj, msg = lecturer.enterGrades(
                db,
                selected_section_id,
                eid,
                att,
                mid,
                fin,
                save_as_draft=save_as_draft,
            )
            if not grade_obj:
                errors.append(f"Enrollment #{eid}: {msg}")
            else:
                saved_count += 1

        if errors:
            for err in errors:
                flash(err, "danger")
        elif saved_count > 0:
            flash(
                f"Saved grades for {saved_count} student(s) successfully.",
                "success",
            )
        else:
            flash("No score values were entered.", "info")
        return redirect(
            url_for("lecturer.grade_entry", section_id=selected_section_id)
        )

    roster = lecturer.getRoster(db, selected_section_id) if selected_section_id else []
    selected_section = next(
        (s for s in sections if s["SectionID"] == selected_section_id), None
    )
    return render_template(
        "lecturer/grade_entry.html",
        lecturer=lecturer,
        sections=sections,
        selected_section=selected_section,
        roster=roster,
    )


@academic_bp.route("/results")
@role_required("Student")
def academic_results():
    db = current_app.extensions["db"]
    with db.connection() as conn:
        st = conn.execute(
            "SELECT StudentID, FullName, ClassID FROM STUDENTS WHERE UserID = ?",
            (session["user_id"],),
        ).fetchone()
    if not st:
        flash("Student profile not linked to this account.", "danger")
        return redirect(url_for("auth.portal_home"))
    results = Grade.get_student_academic_results(db, st["StudentID"])
    return render_template(
        "student/results.html",
        student=dict(st),
        results=results,
    )


@academic_bp.route("/schedule")
@login_required
def class_schedule():
    role = session.get("role")
    if role not in ("Student", "Lecturer"):
        flash("Schedule view is available for Students and Lecturers only.", "warning")
        return redirect(url_for("auth.index"))
    db = current_app.extensions["db"]
    semester = request.args.get("semester", "").strip()
    schedule_data = ReportService.get_weekly_schedule(
        db, role, session["user_id"], semester=semester
    )
    return render_template(
        "lecturer/schedule.html",
        schedule_data=schedule_data,
        selected_semester=semester,
        portal_title="Weekly Class Schedule (UC-23)",
    )
