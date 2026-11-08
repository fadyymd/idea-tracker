from datetime import timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..forms import CommentForm, IdeaForm, ReviewForm
from ..models import (
    STATUS_PENDING,
    STATUS_REVIEW,
    STATUSES,
    Category,
    Comment,
    Idea,
    Vote,
    utcnow,
)
from ..utils import build_comment_tree, is_safe_redirect, normalize_name, reviewer_required

bp = Blueprint("ideas", __name__)

def _trending_order():
    """Activity in the last 7 days: votes (net) + comments, then all-time score."""
    cutoff = utcnow() - timedelta(days=7)
    recent_votes = (
        db.select(db.func.coalesce(db.func.sum(Vote.vote_type), 0))
        .where(Vote.idea_id == Idea.id, Vote.created_at >= cutoff)
        .correlate_except(Vote)
        .scalar_subquery()
    )
    recent_comments = (
        db.select(db.func.count(Comment.id))
        .where(Comment.idea_id == Idea.id, Comment.created_at >= cutoff, Comment.is_deleted.is_(False))
        .correlate_except(Comment)
        .scalar_subquery()
    )
    return ((recent_votes + recent_comments).desc(), Idea.score.desc(), Idea.created_at.desc())


SORTS = {
    "new": ("Newest", lambda: (Idea.created_at.desc(),)),
    "trending": ("Trending (7 days)", _trending_order),
    "top": ("Top voted", lambda: (Idea.score.desc(), Idea.created_at.desc())),
    "discussed": ("Most discussed", lambda: (Idea.comment_count.desc(), Idea.created_at.desc())),
    "old": ("Oldest", lambda: (Idea.created_at.asc(),)),
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def wants_json() -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def get_or_create_category(name: str, user) -> Category:
    """Find a category case-insensitively or create it (dynamic categories)."""
    name = normalize_name(name)
    existing = Category.query.filter(db.func.lower(Category.name) == name.lower()).first()
    if existing:
        return existing
    category = Category(name=name, created_by_id=user.id)
    db.session.add(category)
    db.session.flush()
    return category


def can_modify(idea: Idea) -> bool:
    """Owners may edit/delete while the idea is still pending; admins always."""
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin:
        return True
    return idea.submitter_id == current_user.id and idea.status == STATUS_PENDING


def paginate_ideas(stmt, per_page=None):
    page = request.args.get("page", 1, type=int)
    return db.paginate(
        stmt, page=page, per_page=per_page or current_app.config["IDEAS_PER_PAGE"], error_out=False
    )


def user_votes_for(ideas) -> dict:
    """{idea_id: +1/-1} for the current user, fetched in a single query."""
    if not current_user.is_authenticated or not ideas:
        return {}
    ids = [i.id for i in ideas]
    rows = Vote.query.filter(Vote.user_id == current_user.id, Vote.idea_id.in_(ids)).all()
    return {v.idea_id: v.vote_type for v in rows}


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --------------------------------------------------------------------------- #
# List / create
# --------------------------------------------------------------------------- #
@bp.route("/ideas")
def list_ideas():
    q = (request.args.get("q") or "").strip()
    category_id = request.args.get("category", type=int)
    status = request.args.get("status")
    sort = request.args.get("sort", "new")
    if sort not in SORTS:
        sort = "new"

    stmt = db.select(Idea).options(joinedload(Idea.category), joinedload(Idea.submitter))
    if q:
        like = f"%{escape_like(q)}%"
        stmt = stmt.where(Idea.title.ilike(like, escape="\\") | Idea.description.ilike(like, escape="\\"))
    if category_id:
        stmt = stmt.where(Idea.category_id == category_id)
    if status in STATUSES:
        stmt = stmt.where(Idea.status == status)
    stmt = stmt.order_by(*SORTS[sort][1]())

    pagination = paginate_ideas(stmt)
    categories = Category.query.order_by(Category.name).all()
    return render_template(
        "ideas/list.html",
        pagination=pagination,
        ideas=pagination.items,
        my_votes=user_votes_for(pagination.items),
        categories=categories,
        sorts={k: v[0] for k, v in SORTS.items()},
        filters={"q": q, "category": category_id, "status": status, "sort": sort},
        title="All ideas",
    )


@bp.route("/my-ideas")
@login_required
def my_ideas():
    stmt = (
        db.select(Idea)
        .where(Idea.submitter_id == current_user.id)
        .options(joinedload(Idea.category), joinedload(Idea.submitter))
        .order_by(Idea.created_at.desc())
    )
    pagination = paginate_ideas(stmt)
    return render_template(
        "ideas/list.html",
        pagination=pagination,
        ideas=pagination.items,
        my_votes=user_votes_for(pagination.items),
        categories=[],
        sorts={},
        filters={"q": "", "category": None, "status": None, "sort": "new"},
        title="My ideas",
        mine=True,
    )


@bp.route("/ideas/new", methods=["GET", "POST"])
@login_required
def create():
    form = IdeaForm()
    if form.validate_on_submit():
        new_name = normalize_name(form.new_category.data)
        if new_name:
            category = get_or_create_category(new_name, current_user)
        else:
            category = db.session.get(Category, form.category.data)
            if category is None:
                form.category.errors.append("Unknown category.")
                return render_template("ideas/form.html", form=form, editing=False)
        idea = Idea(
            title=form.title.data.strip(),
            description=form.description.data.strip(),
            category_id=category.id,
            submitter_id=current_user.id,
        )
        db.session.add(idea)
        db.session.commit()
        flash("Your idea has been submitted. Thank you!", "success")
        return redirect(url_for("ideas.detail", idea_id=idea.id))
    return render_template("ideas/form.html", form=form, editing=False)


# --------------------------------------------------------------------------- #
# Detail / edit / delete
# --------------------------------------------------------------------------- #
@bp.route("/ideas/<int:idea_id>")
def detail(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    comments = (
        Comment.query.filter_by(idea_id=idea.id)
        .options(joinedload(Comment.user))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .all()
    )
    roots = build_comment_tree(comments)
    review_form = ReviewForm(status=idea.status, review_note=idea.review_note)
    can_review = current_user.is_authenticated and current_user.is_reviewer and (
        current_user.is_admin or idea.submitter_id != current_user.id
    )
    related = (
        Idea.query.options(joinedload(Idea.submitter))
        .filter(Idea.category_id == idea.category_id, Idea.id != idea.id)
        .order_by(Idea.score.desc(), Idea.created_at.desc())
        .limit(3)
        .all()
    )
    return render_template(
        "ideas/detail.html",
        idea=idea,
        related=related,
        comment_roots=roots,
        comment_total=sum(1 for c in comments if not c.is_deleted),
        comment_form=CommentForm(),
        review_form=review_form,
        can_review=can_review,
        can_modify=can_modify(idea),
        my_vote=idea.vote_of(current_user),
    )


@bp.route("/ideas/<int:idea_id>/edit", methods=["GET", "POST"])
@login_required
def edit(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    if not can_modify(idea):
        abort(403)
    form = IdeaForm(obj=idea)
    if request.method == "GET":
        form.category.data = idea.category_id
    if form.validate_on_submit():
        new_name = normalize_name(form.new_category.data)
        category = (
            get_or_create_category(new_name, current_user)
            if new_name
            else db.session.get(Category, form.category.data)
        )
        if category is None:
            form.category.errors.append("Unknown category.")
        else:
            idea.title = form.title.data.strip()
            idea.description = form.description.data.strip()
            idea.category_id = category.id
            db.session.commit()
            flash("Idea updated.", "success")
            return redirect(url_for("ideas.detail", idea_id=idea.id))
    return render_template("ideas/form.html", form=form, editing=True, idea=idea)


@bp.route("/ideas/<int:idea_id>/delete", methods=["POST"])
@login_required
def delete(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    if not can_modify(idea):
        abort(403)
    db.session.delete(idea)
    db.session.commit()
    flash("Idea deleted.", "info")
    return redirect(url_for("ideas.list_ideas"))


# --------------------------------------------------------------------------- #
# Voting
# --------------------------------------------------------------------------- #
@bp.route("/ideas/<int:idea_id>/vote", methods=["POST"])
def vote(idea_id):
    if not current_user.is_authenticated:
        if wants_json():
            return jsonify(error="Please sign in to vote.", login=url_for("auth.login")), 401
        return current_app.login_manager.unauthorized()

    idea = db.session.get(Idea, idea_id) or abort(404)
    value = request.form.get("value", type=int)
    if value is None and request.is_json:
        value = (request.get_json(silent=True) or {}).get("value")
    if value not in (1, -1):
        if wants_json():
            return jsonify(error="Invalid vote."), 400
        abort(400)

    if idea.submitter_id == current_user.id:
        if wants_json():
            return jsonify(error="You cannot vote on your own idea."), 403
        flash("You cannot vote on your own idea.", "warning")
        return redirect(url_for("ideas.detail", idea_id=idea.id))

    existing = Vote.query.filter_by(idea_id=idea.id, user_id=current_user.id).first()
    if existing is None:
        db.session.add(Vote(idea_id=idea.id, user_id=current_user.id, vote_type=value))
        my_vote = value
    elif existing.vote_type == value:  # clicking the same arrow again withdraws the vote
        db.session.delete(existing)
        my_vote = 0
    else:
        existing.vote_type = value
        my_vote = value
    try:
        db.session.commit()
    except IntegrityError:
        # Two simultaneous clicks raced on the unique (idea, user) constraint: keep the first.
        db.session.rollback()
        current = Vote.query.filter_by(idea_id=idea.id, user_id=current_user.id).first()
        my_vote = current.vote_type if current else 0
    db.session.refresh(idea)

    if wants_json():
        return jsonify(
            score=idea.score,
            upvotes=idea.upvotes,
            downvotes=idea.downvotes,
            my_vote=my_vote,
        )
    return redirect(request.referrer or url_for("ideas.detail", idea_id=idea.id))


# --------------------------------------------------------------------------- #
# Comments
# --------------------------------------------------------------------------- #
@bp.route("/ideas/<int:idea_id>/comments", methods=["POST"])
@login_required
def add_comment(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    form = CommentForm()
    if not form.validate_on_submit():
        flash("Your comment cannot be empty and must be under 2000 characters.", "danger")
        return redirect(url_for("ideas.detail", idea_id=idea.id) + "#comments")

    parent_id = None
    raw_parent = (form.parent_id.data or "").strip()
    if raw_parent:
        parent = db.session.get(Comment, int(raw_parent)) if raw_parent.isdigit() else None
        if parent is None or parent.idea_id != idea.id or parent.is_deleted:
            flash("The comment you replied to no longer exists.", "warning")
            return redirect(url_for("ideas.detail", idea_id=idea.id) + "#comments")
        parent_id = parent.id

    comment = Comment(
        idea_id=idea.id,
        user_id=current_user.id,
        parent_id=parent_id,
        content=form.content.data.strip(),
    )
    db.session.add(comment)
    db.session.commit()
    flash("Comment posted.", "success")
    return redirect(url_for("ideas.detail", idea_id=idea.id) + f"#comment-{comment.id}")


@bp.route("/comments/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = db.session.get(Comment, comment_id) or abort(404)
    if comment.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    idea_id = comment.idea_id
    if comment.replies:
        # Keep the thread intact: blank the content but leave the node.
        comment.is_deleted = True
        comment.content = ""
    else:
        db.session.delete(comment)
    db.session.commit()
    flash("Comment removed.", "info")
    return redirect(url_for("ideas.detail", idea_id=idea_id) + "#comments")


# --------------------------------------------------------------------------- #
# Evaluation (reviewers / administrators)
# --------------------------------------------------------------------------- #
@bp.route("/ideas/<int:idea_id>/review", methods=["POST"])
@reviewer_required
def review(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    if idea.submitter_id == current_user.id and not current_user.is_admin:
        abort(403)  # conflict of interest: reviewers cannot judge their own idea
    form = ReviewForm()
    if form.validate_on_submit() and form.status.data in STATUSES:
        idea.status = form.status.data
        if "review_note" in request.form:  # quick actions from the queue leave the note untouched
            idea.review_note = (form.review_note.data or "").strip()
        idea.reviewed_by_id = current_user.id
        idea.reviewed_at = utcnow()
        db.session.commit()
        flash("Evaluation saved.", "success")
    else:
        flash("Could not save the evaluation. Check the form and try again.", "danger")
    nxt = request.form.get("next")
    return redirect(nxt if is_safe_redirect(nxt) else url_for("ideas.detail", idea_id=idea.id))


@bp.route("/review")
@reviewer_required
def review_queue():
    """Work list for reviewers: ideas waiting for a decision, oldest first."""
    show = request.args.get("show", "pending")
    statuses = {
        "pending": (STATUS_PENDING,),
        "under_review": (STATUS_REVIEW,),
        "open": (STATUS_PENDING, STATUS_REVIEW),
    }.get(show, (STATUS_PENDING,))
    if show not in ("pending", "under_review", "open"):
        show = "pending"
    stmt = (
        db.select(Idea)
        .where(Idea.status.in_(statuses))
        .options(joinedload(Idea.category), joinedload(Idea.submitter))
        .order_by(Idea.created_at.asc())
    )
    pagination = paginate_ideas(stmt)
    counts = dict(db.session.query(Idea.status, db.func.count(Idea.id)).group_by(Idea.status).all())
    return render_template(
        "ideas/queue.html",
        pagination=pagination,
        ideas=pagination.items,
        show=show,
        counts=counts,
    )
