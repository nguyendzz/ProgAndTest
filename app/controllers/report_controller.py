from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    send_file,
)
from app.models.report_service import ReportService
from app.utils.decorators import role_required


report_bp = Blueprint("reports", __name__, url_prefix="/reports")


@report_bp.route("/", methods=["GET"])
@role_required("Staff", "Admin")
def analytics():
    db = current_app.extensions["db"]
    report_type = request.args.get("report_type", "student_roster").strip()
    faculty_id = request.args.get("faculty_id", "").strip()
    semester = request.args.get("semester", "").strip()
    subject_id = request.args.get("subject_id", "").strip()

    report_data = ReportService.generate_report(
        db,
        report_type=report_type,
        faculty_id=faculty_id,
        semester=semester,
        subject_id=subject_id,
    )

    with db.connection() as conn:
        faculties = [
            dict(r)
            for r in conn.execute(
                "SELECT FacultyID, FacultyName FROM FACULTIES ORDER BY FacultyID ASC"
            ).fetchall()
        ]
        subjects = [
            dict(r)
            for r in conn.execute(
                "SELECT SubjectID, SubjectName FROM SUBJECTS ORDER BY SubjectID ASC"
            ).fetchall()
        ]
        semesters = [
            r["Semester"]
            for r in conn.execute(
                "SELECT DISTINCT Semester FROM COURSES ORDER BY Semester DESC"
            ).fetchall()
        ]

    return render_template(
        "reports/analytics.html",
        report_data=report_data,
        templates=ReportService.REPORT_TEMPLATES,
        faculties=faculties,
        subjects=subjects,
        semesters=semesters,
        faculty_id=faculty_id,
        semester=semester,
        subject_id=subject_id,
    )


@report_bp.route("/export/excel", methods=["GET"])
@role_required("Staff", "Admin")
def export_excel():
    db = current_app.extensions["db"]
    report_type = request.args.get("report_type", "student_roster").strip()
    report_data = ReportService.generate_report(
        db,
        report_type=report_type,
        faculty_id=request.args.get("faculty_id", ""),
        semester=request.args.get("semester", ""),
        subject_id=request.args.get("subject_id", ""),
    )
    stream = ReportService.export_to_excel(report_data)
    return send_file(
        stream,
        as_attachment=True,
        download_name=f"report_{report_data['report_type']}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@report_bp.route("/export/pdf", methods=["GET"])
@role_required("Staff", "Admin")
def export_pdf():
    db = current_app.extensions["db"]
    report_type = request.args.get("report_type", "student_roster").strip()
    report_data = ReportService.generate_report(
        db,
        report_type=report_type,
        faculty_id=request.args.get("faculty_id", ""),
        semester=request.args.get("semester", ""),
        subject_id=request.args.get("subject_id", ""),
    )
    stream = ReportService.export_to_pdf(report_data)
    return send_file(
        stream,
        as_attachment=True,
        download_name=f"report_{report_data['report_type']}.pdf",
        mimetype="application/pdf",
    )
