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
from app.models.user import User
from app.utils.decorators import csrf_protect, role_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard")
@role_required("Admin")
def dashboard():
    db = current_app.extensions["db"]
    with db.connection() as conn:
        total_students = conn.execute("SELECT COUNT(*) FROM STUDENTS").fetchone()[0]
        total_classes = conn.execute("SELECT COUNT(*) FROM CLASSES").fetchone()[0]
        active_courses = conn.execute(
            "SELECT COUNT(*) FROM COURSES WHERE Status = 'Open'"
        ).fetchone()[0]
        pending_enrollments = conn.execute(
            "SELECT COUNT(*) FROM REGISTRATION_CART WHERE Status = 'InCart'"
        ).fetchone()[0]
    stats = {
        "total_students": total_students,
        "total_classes": total_classes,
        "active_courses": active_courses,
        "pending_enrollments": pending_enrollments,
    }
    return render_template("admin/dashboard.html", stats=stats)


@admin_bp.route("/accounts", methods=["GET"])
@role_required("Admin")
def accounts():
    db = current_app.extensions["db"]
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    role_filter = request.args.get("role", "").strip()
    pagination = User.list_paginated(
        db,
        page=page,
        per_page=current_app.config["PER_PAGE"],
        search=search,
        role_filter=role_filter,
    )
    return render_template(
        "admin/accounts.html",
        pagination=pagination,
        search=search,
        role_filter=role_filter,
        roles=User.VALID_ROLES,
    )


@admin_bp.route("/accounts/create", methods=["POST"])
@role_required("Admin")
@csrf_protect
def create_account():
    db = current_app.extensions["db"]
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    role = request.form.get("role", "")
    email = request.form.get("email", "")
    user, message = User.create(db, username, password, role, email)
    flash(message, "success" if user else "danger")
    return redirect(url_for("admin.accounts"))


@admin_bp.route("/accounts/<int:user_id>/role", methods=["POST"])
@role_required("Admin")
@csrf_protect
def update_account_role(user_id: int):
    db = current_app.extensions["db"]
    new_role = request.form.get("role", "")
    ok, message = User.update_role(db, user_id, new_role, session["user_id"])
    flash(message, "success" if ok else "danger")
    return redirect(url_for("admin.accounts"))


@admin_bp.route("/accounts/<int:user_id>/toggle-status", methods=["POST"])
@role_required("Admin")
@csrf_protect
def toggle_account_status(user_id: int):
    db = current_app.extensions["db"]
    ok, message = User.toggle_status(db, user_id, session["user_id"])
    flash(message, "success" if ok else "danger")
    return redirect(url_for("admin.accounts"))
