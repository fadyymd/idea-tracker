import csv
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..forms import CategoryForm
from ..models import (
    ROLE_ADMIN,
    ROLES,
    STATUS_LABELS,
    STATUSES,
    Category,
    Comment,
    Feedback,
    Idea,
    User,
    Vote,
)
from ..utils import admin_required, normalize_name

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _active_admin_count() -> int:
    return User.query.filter_by(role=ROLE_ADMIN, is_active_account=True).count()


@bp.route("/")
@admin_required
def dashboard():
    by_status = dict(db.session.query(Idea.status, db.func.count(Idea.id)).group_by(Idea.status).all())
    status_data = [{"key": s, "label": STATUS_LABELS[s], "count": by_status.get(s, 0)} for s in STATUSES]
    cat_rows = (
        db.session.query(Category.name, db.func.count(Idea.id))
        .outerjoin(Idea, Idea.category_id == Category.id)
        .group_by(Category.id, Category.name)
        .order_by(db.func.count(Idea.id).desc())
        .all()
    )
    stats = {
        "users": User.query.count(),
        "ideas": Idea.query.count(),
        "votes": Vote.query.count(),
        "comments": Comment.query.filter_by(is_deleted=False).count(),
        "open_feedback": Feedback.query.filter_by(resolved=False).count(),
        "awaiting": by_status.get("pending", 0),
    }
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        status_data=status_data,
        category_data=[{"label": n, "count": c} for n, c in cat_rows],
    )


# ---------------------------- users --------------------------------------- #
@bp.route("/users")
@admin_required
def users():
    q = (request.args.get("q") or "").strip()
    query = User.query
    if q:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{esc}%"
        query = query.filter(User.username.ilike(like, escape="\\") | User.email.ilike(like, escape="\\"))
    return render_template("admin/users.html", users=query.order_by(User.created_at.desc()).all(), q=q)


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@admin_required
def set_role(user_id):
    user = db.session.get(User, user_id) or abort(404)
    role = request.form.get("role")
    if role not in ROLES:
        abort(400)
    if user.id == current_user.id and role != ROLE_ADMIN:
        flash("You cannot remove your own administrator role.", "warning")
    else:
        user.role = role
        db.session.commit()
        flash(f"{user.username} is now a {role}.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("You cannot disable your own account.", "warning")
    elif user.is_active_account and user.is_admin and _active_admin_count() <= 1:
        flash("At least one active administrator is required.", "warning")
    else:
        user.is_active_account = not user.is_active_account
        db.session.commit()
        flash(f"{user.username} {'enabled' if user.is_active_account else 'disabled'}.", "success")
    return redirect(url_for("admin.users"))


# ---------------------------- categories ---------------------------------- #
@bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    form = CategoryForm()
    if form.validate_on_submit():
        name = normalize_name(form.name.data)
        if Category.query.filter(db.func.lower(Category.name) == name.lower()).first():
            form.name.errors.append("A category with this name already exists.")
        else:
            db.session.add(
                Category(name=name, description=(form.description.data or "").strip(), created_by_id=current_user.id)
            )
            db.session.commit()
            flash("Category added.", "success")
            return redirect(url_for("admin.categories"))
    rows = (
        db.session.query(Category, db.func.count(Idea.id))
        .outerjoin(Idea, Idea.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.name)
        .all()
    )
    return render_template("admin/categories.html", form=form, rows=rows)


@bp.route("/categories/<int:category_id>/rename", methods=["POST"])
@admin_required
def rename_category(category_id):
    category = db.session.get(Category, category_id) or abort(404)
    name = normalize_name(request.form.get("name", ""))
    if not (2 <= len(name) <= 50):
        flash("Category name must be between 2 and 50 characters.", "danger")
    else:
        clash = Category.query.filter(db.func.lower(Category.name) == name.lower(), Category.id != category.id).first()
        if clash:
            flash("Another category already uses that name.", "danger")
        else:
            category.name = name
            db.session.commit()
            flash("Category renamed.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def delete_category(category_id):
    category = db.session.get(Category, category_id) or abort(404)
    if category.ideas:
        flash("This category still contains ideas and cannot be deleted.", "warning")
    else:
        db.session.delete(category)
        db.session.commit()
        flash("Category deleted.", "info")
    return redirect(url_for("admin.categories"))


# ---------------------------- feedback ------------------------------------ #
@bp.route("/feedback")
@admin_required
def feedback():
    show = request.args.get("show", "open")
    query = Feedback.query
    if show == "open":
        query = query.filter_by(resolved=False)
    items = query.order_by(Feedback.created_at.desc()).all()
    return render_template("admin/feedback.html", items=items, show=show)


@bp.route("/feedback/<int:item_id>/resolve", methods=["POST"])
@admin_required
def resolve_feedback(item_id):
    item = db.session.get(Feedback, item_id) or abort(404)
    item.resolved = not item.resolved
    db.session.commit()
    return redirect(request.referrer or url_for("admin.feedback"))


# ---------------------------- export -------------------------------------- #
def _csv_safe(value):
    """Neutralise spreadsheet formula injection (cells starting with = + - @)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.route("/export/ideas.csv")
@admin_required
def export_ideas():
    ideas = Idea.query.order_by(Idea.id).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "title", "category", "status", "score", "upvotes", "downvotes", "comments",
         "submitter", "created_at", "reviewed_by", "review_note"]
    )
    for i in ideas:
        writer.writerow(
            [i.id, _csv_safe(i.title), _csv_safe(i.category.name), i.status, i.score, i.upvotes, i.downvotes,
             i.comment_count, _csv_safe(i.submitter.username), i.created_at.isoformat(timespec="seconds"),
             _csv_safe(i.reviewed_by.username if i.reviewed_by else ""), _csv_safe(i.review_note)]
        )
    return Response(
        "\ufeff" + buf.getvalue(),  # BOM so Excel opens UTF-8 correctly
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ideas.csv"},
    )
