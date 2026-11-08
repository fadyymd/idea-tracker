"""Innovation Idea Tracker – application factory."""
import os
from datetime import datetime, timezone

import click
from flask import Flask, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from config import Config

from .extensions import csrf, db, login_manager
from .models import (
    DEFAULT_CATEGORIES,
    ROLE_ADMIN,
    ROLES,
    STATUS_COLORS,
    STATUS_ICONS,
    STATUS_LABELS,
    STATUS_PENDING,
    Category,
    Idea,
    User,
)
from .security import register_security


def ensure_default_categories() -> int:
    """Insert the predefined categories that do not exist yet. Returns how many were added."""
    added = 0
    for name, description in DEFAULT_CATEGORIES:
        if not Category.query.filter(db.func.lower(Category.name) == name.lower()).first():
            db.session.add(Category(name=name, description=description))
            added += 1
    if added:
        db.session.commit()
    return added


def bootstrap_database() -> None:
    """Create tables + default categories.

    Several gunicorn workers may start at the same moment and race on this; whoever loses
    simply finds the work already done, so integrity/operational errors are swallowed.
    """
    try:
        db.create_all()
        ensure_default_categories()
    except (IntegrityError, OperationalError, ProgrammingError):
        db.session.rollback()


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    os.makedirs(os.path.join(app.root_path, "..", "instance"), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .blueprints.admin import bp as admin_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.ideas import bp as ideas_bp
    from .blueprints.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(ideas_bp)
    app.register_blueprint(admin_bp)

    register_template_helpers(app)
    register_error_handlers(app)
    register_security(app)
    register_cli(app)

    with app.app_context():
        bootstrap_database()

    return app


# --------------------------------------------------------------------------- #
def register_template_helpers(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        queue_count = 0
        if current_user.is_authenticated and current_user.is_reviewer:
            queue_count = Idea.query.filter_by(status=STATUS_PENDING).count()
        return {
            "STATUS_LABELS": STATUS_LABELS,
            "STATUS_COLORS": STATUS_COLORS,
            "STATUS_ICONS": STATUS_ICONS,
            "ROLES": ROLES,
            "queue_count": queue_count,
        }

    @app.template_filter("datetime")
    def fmt_datetime(value, fmt="%b %d, %Y · %H:%M"):
        return value.strftime(fmt) if value else ""

    @app.template_filter("timeago")
    def timeago(value):
        if not value:
            return ""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        seconds = int((now - value).total_seconds())
        if seconds < 60:
            return "just now"
        for limit, size, unit in ((3600, 60, "minute"), (86400, 3600, "hour"), (86400 * 30, 86400, "day")):
            if seconds < limit:
                n = seconds // size
                return f"{n} {unit}{'s' if n != 1 else ''} ago"
        return value.strftime("%b %d, %Y")

    @app.template_filter("compact")
    def compact(n):
        """1200 -> 1.2k"""
        try:
            n = int(n)
        except (TypeError, ValueError):
            return n
        if abs(n) >= 1000:
            return f"{n / 1000:.1f}k".replace(".0k", "k")
        return str(n)

    @app.template_global()
    def hue(obj_id):
        """Stable colour slot (0-7) for avatars and category chips."""
        return (obj_id or 0) % 8

    @app.template_global()
    def url_with(**changes):
        """Current URL with some query args replaced (used by pagination/filters)."""
        args = request.args.to_dict()
        for key, val in changes.items():
            if val in (None, ""):
                args.pop(key, None)
            else:
                args[key] = val
        return url_for(request.endpoint, **{**(request.view_args or {}), **args})


def register_error_handlers(app: Flask) -> None:
    def _render(code, title, message):
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def bad_request(_e):
        return _render(400, "Bad request", "The request could not be understood.")

    @app.errorhandler(403)
    def forbidden(_e):
        return _render(403, "Access denied", "You do not have permission to view this page.")

    @app.errorhandler(404)
    def not_found(_e):
        return _render(404, "Page not found", "The page you are looking for does not exist.")

    @app.errorhandler(429)
    def too_many(_e):
        return _render(429, "Too many requests", "Please slow down and try again in a few minutes.")

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return _render(400, "Session expired", "Your form session expired. Please go back, refresh the page and try again.")

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return _render(500, "Something went wrong", "An unexpected error occurred. Please try again later.")


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Create tables and the predefined categories."""
        db.create_all()
        added = ensure_default_categories()
        click.echo(f"Database ready. {added} default categories added.")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin(username, email, password):
        """Create an administrator account."""
        if User.query.filter(
            (db.func.lower(User.username) == username.lower()) | (db.func.lower(User.email) == email.lower())
        ).first():
            raise click.ClickException("Username or email already exists.")
        user = User(username=username, email=email.lower(), role=ROLE_ADMIN)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Administrator '{username}' created.")
