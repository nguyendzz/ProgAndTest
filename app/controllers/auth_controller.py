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
from app.utils.decorators import csrf_protect, login_required


auth_bp = Blueprint("auth", __name__)


def resolve_dashboard_url(user: User) -> str:
    endpoint = user.get_dashboard_endpoint()
    if endpoint in current_app.view_functions:
        return url_for(endpoint)
    return url_for("auth.portal_home")


@auth_bp.route("/")
def index():
    if session.get("user_id"):
        db = current_app.extensions["db"]
        user = User.find_by_id(db, session["user_id"])
        if user and user.status == "Active":
            return redirect(resolve_dashboard_url(user))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
@csrf_protect
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = current_app.extensions["db"]
        user = User.find_by_username(db, username)
        if not user:
            flash("Invalid username or password", "danger")
            return render_template("auth/login.html", username=username), 401
        ok, message = user.login(
            db,
            password,
            max_attempts=current_app.config["MAX_FAILED_LOGIN_ATTEMPTS"],
            lock_minutes=current_app.config["LOCK_DURATION_MINUTES"],
        )
        if not ok:
            flash(message, "danger")
            status_code = 403 if "locked" in message.lower() else 401
            return render_template("auth/login.html", username=username), status_code
        session.clear()
        session["user_id"] = user.user_id
        session["username"] = user.username
        session["role"] = user.role
        session["email"] = user.email
        session["session_version"] = user.session_version
        return redirect(resolve_dashboard_url(user))
    return render_template("auth/login.html", username="")


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    user_id = session.get("user_id")
    if user_id:
        db = current_app.extensions["db"]
        user = User.find_by_id(db, user_id)
        if user:
            user.logout(db)
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/reset-password", methods=["GET", "POST"])
@csrf_protect
def reset_password():
    token = request.args.get("token") or request.form.get("token", "").strip()
    generated_link = None
    if request.method == "POST":
        action = request.form.get("action", "request")
        db = current_app.extensions["db"]
        if action == "request":
            identifier = request.form.get("identifier", "").strip()
            user = User.find_by_username_or_email(db, identifier)
            if not user:
                flash(
                    "Account with the provided username or email was not found.",
                    "danger",
                )
                return (
                    render_template(
                        "auth/reset_password.html", token="", generated_link=None
                    ),
                    404,
                )
            new_token = user.create_reset_token(
                db, expiry_minutes=current_app.config["RESET_TOKEN_EXPIRY_MINUTES"]
            )
            generated_link = url_for(
                "auth.reset_password", token=new_token, _external=False
            )
            flash("Verification link generated. Valid for 15 minutes.", "success")
            return render_template(
                "auth/reset_password.html",
                token=new_token,
                generated_link=generated_link,
            )
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if new_password != confirm_password:
            flash("Password confirmation does not match.", "danger")
            return (
                render_template(
                    "auth/reset_password.html", token=token, generated_link=None
                ),
                400,
            )
        user = User.find_by_reset_token(db, token)
        if not user:
            flash("Invalid or expired password reset token.", "danger")
            return (
                render_template(
                    "auth/reset_password.html", token=token, generated_link=None
                ),
                400,
            )
        ok, message = user.resetPassword(db, token, new_password)
        if not ok:
            flash(message, "danger")
            return (
                render_template(
                    "auth/reset_password.html", token=token, generated_link=None
                ),
                400,
            )
        flash(message, "success")
        return redirect(url_for("auth.login"))
    return render_template(
        "auth/reset_password.html", token=token, generated_link=generated_link
    )


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
@csrf_protect
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if new_password != confirm_password:
            flash("New password confirmation does not match.", "danger")
            return render_template("auth/change_password.html"), 400
        db = current_app.extensions["db"]
        user = User.find_by_id(db, session["user_id"])
        ok, message = user.changePassword(db, current_password, new_password)
        if not ok:
            flash(message, "danger")
            return render_template("auth/change_password.html"), 400
        session["session_version"] = user.session_version
        flash(message, "success")
        return redirect(resolve_dashboard_url(user))
    return render_template("auth/change_password.html")


@auth_bp.route("/portal")
@login_required
def portal_home():
    return render_template("admin/dashboard.html", stats=None)
