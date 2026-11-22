from functools import wraps
from flask import abort, current_app, flash, redirect, request, session, url_for
from app.models.user import User
from app.utils.security import SecurityService


def get_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = SecurityService.generate_csrf_token()
        session["csrf_token"] = token
    return token


def csrf_protect(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if request.method == "POST":
            session_token = session.get("csrf_token")
            form_token = request.form.get("csrf_token") or request.headers.get(
                "X-CSRF-Token"
            )
            if not session_token or not form_token or session_token != form_token:
                abort(400, description="Invalid CSRF token.")
        return view_func(*args, **kwargs)

    return wrapped


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        session_version = session.get("session_version")
        if not user_id:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("auth.login"))
        db = current_app.extensions["db"]
        user = User.find_by_id(db, user_id)
        if not user or user.status != "Active" or user.session_version != session_version:
            session.clear()
            flash("Your session has expired. Please sign in again.", "warning")
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)

    return wrapped


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") not in allowed_roles:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator
