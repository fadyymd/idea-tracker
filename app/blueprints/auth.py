import math

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..forms import ChangePasswordForm, LoginForm, ProfileForm, RegisterForm
from ..models import ROLE_SUBMITTER, Comment, Idea, User, Vote
from ..security import login_throttle
from ..utils import is_safe_redirect

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip().lower(),
            role=ROLE_SUBMITTER,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Welcome aboard! Your account has been created.", "success")
        return redirect(url_for("main.index"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = LoginForm()
    if form.validate_on_submit():
        ident = form.identifier.data.strip()
        limit = current_app.config["LOGIN_MAX_ATTEMPTS"]
        window = current_app.config["LOGIN_WINDOW_SECONDS"]
        throttle_key = login_throttle.key(ident)

        wait = login_throttle.retry_after(throttle_key, limit, window)
        if wait:
            flash(f"Too many failed attempts. Please try again in {math.ceil(wait / 60)} minute(s).", "danger")
            return render_template("auth/login.html", form=form), 429

        user = User.query.filter(
            (db.func.lower(User.username) == ident.lower()) | (db.func.lower(User.email) == ident.lower())
        ).first()
        if user is None or not user.check_password(form.password.data):
            login_throttle.register_failure(throttle_key)
            flash("Invalid username/email or password.", "danger")
        elif not user.is_active_account:
            flash("This account has been disabled. Please contact an administrator.", "danger")
        else:
            login_throttle.reset(throttle_key)
            login_user(user, remember=form.remember.data)
            flash(f"Welcome back, {user.username}!", "success")
            nxt = request.args.get("next")
            return redirect(nxt if is_safe_redirect(nxt) else url_for("main.index"))
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    profile_form = ProfileForm(current_user, prefix="p", obj=current_user)
    password_form = ChangePasswordForm(prefix="c")

    if "p-submit" in request.form and profile_form.validate_on_submit():
        current_user.email = profile_form.email.data.strip().lower()
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("auth.profile"))

    if "c-submit" in request.form and password_form.validate_on_submit():
        if not current_user.check_password(password_form.current_password.data):
            password_form.current_password.errors.append("Current password is incorrect.")
        else:
            current_user.set_password(password_form.new_password.data)
            db.session.commit()
            flash("Password changed.", "success")
            return redirect(url_for("auth.profile"))

    stats = {
        "ideas": Idea.query.filter_by(submitter_id=current_user.id).count(),
        "votes": Vote.query.filter_by(user_id=current_user.id).count(),
        "comments": Comment.query.filter_by(user_id=current_user.id, is_deleted=False).count(),
    }
    return render_template(
        "auth/profile.html", profile_form=profile_form, password_form=password_form, stats=stats
    )
