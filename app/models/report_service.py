from datetime import datetime
from io import BytesIO
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


class ReportService:
    REPORT_TEMPLATES = {
        "student_roster": "Student Roster by Class",
        "grade_distribution": "Grade Distribution by Course",
        "enrollment_fill": "Enrollment Fill Rates",
        "waitlist_metrics": "Waitlist Metrics",
    }

    DAYS_ORDER = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat")

    @classmethod
    def get_weekly_schedule(
        cls, db, role: str, user_id: int, semester: str = ""
    ) -> dict:
        params = [user_id]
        sem_clause = ""
        if semester.strip():
            sem_clause = "AND c.Semester = ?"
            params.append(semester.strip())

        with db.connection() as conn:
            if role == "Lecturer":
                rows = conn.execute(
                    f"""
                    SELECT c.SectionID, c.SubjectID, s.SubjectName, s.Credits,
                           c.Semester, c.DayOfWeek, c.StartTime, c.EndTime,
                           c.Room, l.FullName AS LecturerName
                    FROM COURSES c
                    JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                    JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                    WHERE l.UserID = ?
                      AND c.Status != 'Cancelled'
                      {sem_clause}
                    ORDER BY c.StartTime ASC
                    """,
                    params,
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT c.SectionID, c.SubjectID, s.SubjectName, s.Credits,
                           c.Semester, c.DayOfWeek, c.StartTime, c.EndTime,
                           c.Room, l.FullName AS LecturerName
                    FROM ENROLLMENTS e
                    JOIN STUDENTS st ON e.StudentID = st.StudentID
                    JOIN COURSES c ON e.SectionID = c.SectionID
                    JOIN SUBJECTS s ON c.SubjectID = s.SubjectID
                    JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                    WHERE st.UserID = ?
                      AND e.Status = 'Enrolled'
                      AND c.Status != 'Cancelled'
                      {sem_clause}
                    ORDER BY c.StartTime ASC
                    """,
                    params,
                ).fetchall()

        grid = {day: [] for day in cls.DAYS_ORDER}
        semesters = sorted({r["Semester"] for r in rows}, reverse=True)
        for r in rows:
            day = r["DayOfWeek"]
            if day in grid:
                grid[day].append(dict(r))

        return {
            "days": cls.DAYS_ORDER,
            "grid": grid,
            "total_classes": len(rows),
            "semesters": semesters,
        }

    @classmethod
    def generate_report(
        cls,
        db,
        report_type: str,
        faculty_id: str = "",
        semester: str = "",
        subject_id: str = "",
    ) -> dict:
        if report_type not in cls.REPORT_TEMPLATES:
            report_type = "student_roster"

        title = cls.REPORT_TEMPLATES[report_type]
        fid = faculty_id.strip().upper()
        sem = semester.strip()
        sid = subject_id.strip().upper()

        with db.connection() as conn:
            if report_type == "student_roster":
                conditions = []
                params = []
                if fid:
                    conditions.append("f.FacultyID = ?")
                    params.append(fid)
                where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                rows = conn.execute(
                    f"""
                    SELECT s.StudentID, s.FullName, s.ClassID, c.ClassName,
                           f.FacultyName, s.Email, s.Status
                    FROM STUDENTS s
                    JOIN CLASSES c ON s.ClassID = c.ClassID
                    JOIN FACULTIES f ON c.FacultyID = f.FacultyID
                    {where_sql}
                    ORDER BY s.ClassID ASC, s.StudentID ASC
                    """,
                    params,
                ).fetchall()
                headers = [
                    "Student ID",
                    "Full Name",
                    "Class ID",
                    "Class Name",
                    "Faculty",
                    "Email",
                    "Status",
                ]
                data_rows = [
                    [
                        r["StudentID"],
                        r["FullName"],
                        r["ClassID"],
                        r["ClassName"],
                        r["FacultyName"],
                        r["Email"],
                        r["Status"],
                    ]
                    for r in rows
                ]
                active_cnt = sum(1 for r in rows if r["Status"] == "Active")
                metrics = [
                    ("Total Students", len(rows)),
                    ("Active Students", active_cnt),
                    ("Inactive / Other", len(rows) - active_cnt),
                ]

            elif report_type == "grade_distribution":
                conditions = ["g.GradeStatus != 'Draft'"]
                params = []
                if fid:
                    conditions.append("l.FacultyID = ?")
                    params.append(fid)
                if sem:
                    conditions.append("c.Semester = ?")
                    params.append(sem)
                if sid:
                    conditions.append("c.SubjectID = ?")
                    params.append(sid)
                where_sql = f"WHERE {' AND '.join(conditions)}"
                rows = conn.execute(
                    f"""
                    SELECT c.SectionID, c.SubjectID, sub.SubjectName, c.Semester,
                           COUNT(g.GradeID) AS GradedCount,
                           ROUND(AVG(CASE WHEN g.GradeStatus != 'W' THEN g.FinalScore END), 2) AS AvgScore,
                           SUM(CASE WHEN g.GradeStatus != 'W' AND g.FinalScore >= 4.0 THEN 1 ELSE 0 END) AS PassCount,
                           SUM(CASE WHEN g.GradeStatus != 'W' AND g.FinalScore < 4.0 THEN 1 ELSE 0 END) AS FailCount,
                           SUM(CASE WHEN g.GradeStatus = 'W' THEN 1 ELSE 0 END) AS WithdrawCount
                    FROM GRADES g
                    JOIN ENROLLMENTS e ON g.EnrollmentID = e.EnrollmentID
                    JOIN COURSES c ON e.SectionID = c.SectionID
                    JOIN SUBJECTS sub ON c.SubjectID = sub.SubjectID
                    JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                    {where_sql}
                    GROUP BY c.SectionID, c.SubjectID, sub.SubjectName, c.Semester
                    ORDER BY c.Semester DESC, c.SectionID ASC
                    """,
                    params,
                ).fetchall()
                headers = [
                    "Section ID",
                    "Subject ID",
                    "Subject Name",
                    "Semester",
                    "Graded",
                    "Avg Score",
                    "Pass",
                    "Fail",
                    "Withdrawn (W)",
                ]
                data_rows = [
                    [
                        r["SectionID"],
                        r["SubjectID"],
                        r["SubjectName"],
                        r["Semester"],
                        r["GradedCount"],
                        r["AvgScore"] if r["AvgScore"] is not None else "—",
                        r["PassCount"],
                        r["FailCount"],
                        r["WithdrawCount"],
                    ]
                    for r in rows
                ]
                total_pass = sum(r["PassCount"] for r in rows)
                total_fail = sum(r["FailCount"] for r in rows)
                total_eval = total_pass + total_fail
                pass_rate = f"{round((total_pass / total_eval) * 100, 1)}%" if total_eval else "0%"
                metrics = [
                    ("Sections Evaluated", len(rows)),
                    ("Total Pass", total_pass),
                    ("Total Fail", total_fail),
                    ("Overall Pass Rate", pass_rate),
                ]

            elif report_type == "enrollment_fill":
                conditions = []
                params = []
                if fid:
                    conditions.append("l.FacultyID = ?")
                    params.append(fid)
                if sem:
                    conditions.append("c.Semester = ?")
                    params.append(sem)
                if sid:
                    conditions.append("c.SubjectID = ?")
                    params.append(sid)
                where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                rows = conn.execute(
                    f"""
                    SELECT c.SectionID, c.SubjectID, sub.SubjectName, c.Semester,
                           c.Capacity,
                           COUNT(CASE WHEN e.Status = 'Enrolled' THEN 1 END) AS EnrolledCount,
                           c.Status
                    FROM COURSES c
                    JOIN SUBJECTS sub ON c.SubjectID = sub.SubjectID
                    JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                    LEFT JOIN ENROLLMENTS e ON c.SectionID = e.SectionID
                    {where_sql}
                    GROUP BY c.SectionID, c.SubjectID, sub.SubjectName, c.Semester, c.Capacity, c.Status
                    ORDER BY c.Semester DESC, c.SectionID ASC
                    """,
                    params,
                ).fetchall()
                headers = [
                    "Section ID",
                    "Subject ID",
                    "Subject Name",
                    "Semester",
                    "Enrolled",
                    "Capacity",
                    "Fill Rate (%)",
                    "Status",
                ]
                data_rows = []
                total_cap = 0
                total_enr = 0
                for r in rows:
                    cap = int(r["Capacity"])
                    enr = int(r["EnrolledCount"])
                    total_cap += cap
                    total_enr += enr
                    rate = round((enr / cap) * 100, 1) if cap > 0 else 0.0
                    data_rows.append(
                        [
                            r["SectionID"],
                            r["SubjectID"],
                            r["SubjectName"],
                            r["Semester"],
                            enr,
                            cap,
                            f"{rate}%",
                            r["Status"],
                        ]
                    )
                overall_rate = f"{round((total_enr / total_cap) * 100, 1)}%" if total_cap else "0%"
                metrics = [
                    ("Total Sections", len(rows)),
                    ("Total Enrolled Seats", total_enr),
                    ("Total Capacity", total_cap),
                    ("Average Fill Rate", overall_rate),
                ]

            else:
                conditions = []
                params = []
                if fid:
                    conditions.append("l.FacultyID = ?")
                    params.append(fid)
                if sem:
                    conditions.append("c.Semester = ?")
                    params.append(sem)
                if sid:
                    conditions.append("c.SubjectID = ?")
                    params.append(sid)
                where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                rows = conn.execute(
                    f"""
                    SELECT c.SectionID, c.SubjectID, sub.SubjectName, c.Semester,
                           SUM(CASE WHEN w.Status = 'Waiting' THEN 1 ELSE 0 END) AS WaitingCount,
                           SUM(CASE WHEN w.Status = 'Enrolled' THEN 1 ELSE 0 END) AS PromotedCount,
                           SUM(CASE WHEN w.Status = 'Cancelled' THEN 1 ELSE 0 END) AS CancelledCount
                    FROM WAITLIST w
                    JOIN COURSES c ON w.SectionID = c.SectionID
                    JOIN SUBJECTS sub ON c.SubjectID = sub.SubjectID
                    JOIN LECTURERS l ON c.LecturerID = l.LecturerID
                    {where_sql}
                    GROUP BY c.SectionID, c.SubjectID, sub.SubjectName, c.Semester
                    ORDER BY WaitingCount DESC, c.SectionID ASC
                    """,
                    params,
                ).fetchall()
                headers = [
                    "Section ID",
                    "Subject ID",
                    "Subject Name",
                    "Semester",
                    "Waiting",
                    "Auto-Promoted",
                    "Cancelled",
                ]
                data_rows = [
                    [
                        r["SectionID"],
                        r["SubjectID"],
                        r["SubjectName"],
                        r["Semester"],
                        r["WaitingCount"],
                        r["PromotedCount"],
                        r["CancelledCount"],
                    ]
                    for r in rows
                ]
                metrics = [
                    ("Waitlisted Sections", len(rows)),
                    ("Currently Waiting", sum(r["WaitingCount"] for r in rows)),
                    ("Promoted to Enrolled", sum(r["PromotedCount"] for r in rows)),
                ]

        return {
            "report_type": report_type,
            "title": title,
            "headers": headers,
            "rows": data_rows,
            "metrics": metrics,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    def export_to_excel(cls, report_data: dict) -> BytesIO:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Report"

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(1, len(report_data["headers"])))
        title_cell = ws.cell(1, 1, f"UNIVERSITY PORTAL — {report_data['title'].upper()}")
        title_cell.font = Font(bold=True, size=14, color="FFFFFF")
        title_cell.fill = PatternFill(start_color="0F2544", end_color="0F2544", fill_type="solid")
        title_cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.cell(2, 1, f"Generated At: {report_data['generated_at']}")

        header_row = 4
        header_fill = PatternFill(start_color="E8F0FE", end_color="E8F0FE", fill_type="solid")
        for col_idx, header in enumerate(report_data["headers"], start=1):
            c = ws.cell(header_row, col_idx, header)
            c.font = Font(bold=True)
            c.fill = header_fill
            c.alignment = Alignment(horizontal="center")

        for row_idx, r in enumerate(report_data["rows"], start=header_row + 1):
            for col_idx, val in enumerate(r, start=1):
                ws.cell(row_idx, col_idx, val)

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    @classmethod
    def export_to_pdf(cls, report_data: dict) -> BytesIO:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=28, bottomMargin=28)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(
            Paragraph(
                f"<b>STUDENT MANAGER SYSTEM — {report_data['title']}</b>",
                styles["Title"],
            )
        )
        elements.append(
            Paragraph(
                f"Generated At: {report_data['generated_at']}",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 12))

        if report_data["rows"]:
            table_data = [report_data["headers"]] + [
                [str(v) for v in row] for row in report_data["rows"]
            ]
            table = Table(table_data, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2544")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ]
                )
            )
            elements.append(table)
        else:
            elements.append(Paragraph("No data found.", styles["Normal"]))

        doc.build(elements)
        buffer.seek(0)
        return buffer
