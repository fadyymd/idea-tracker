from flask import Blueprint, abort, flash, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..forms import FeedbackForm
from ..models import STATUS_APPROVED, STATUS_IMPLEMENTED, Category, Comment, Feedback, Idea, User, Vote

bp = Blueprint("main", __name__)


def top_contributors(limit=5):
    """Members ranked by the net votes their ideas received (ties: number of ideas)."""
    idea_counts = dict(
        db.session.query(Idea.submitter_id, db.func.count(Idea.id)).group_by(Idea.submitter_id).all()
    )
    votes_received = dict(
        db.session.query(Idea.submitter_id, db.func.coalesce(db.func.sum(Vote.vote_type), 0))
        .join(Vote, Vote.idea_id == Idea.id)
        .group_by(Idea.submitter_id)
        .all()
    )
    ranked = sorted(idea_counts, key=lambda uid: (votes_received.get(uid, 0), idea_counts[uid]), reverse=True)[:limit]
    users = {u.id: u for u in User.query.filter(User.id.in_(ranked)).all()} if ranked else {}
    return [
        {"user": users[uid], "ideas": idea_counts[uid], "score": int(votes_received.get(uid, 0))}
        for uid in ranked
        if uid in users
    ]


@bp.route("/")
def index():
    stats = {
        "ideas": Idea.query.count(),
        "users": User.query.count(),
        "votes": Vote.query.count(),
        "comments": Comment.query.filter_by(is_deleted=False).count(),
    }
    top_ideas = (
        Idea.query.options(joinedload(Idea.category), joinedload(Idea.submitter))
        .order_by(Idea.score.desc(), Idea.created_at.desc())
        .limit(5)
        .all()
    )
    recent_ideas = (
        Idea.query.options(joinedload(Idea.category), joinedload(Idea.submitter))
        .order_by(Idea.created_at.desc())
        .limit(5)
        .all()
    )
    rows = (
        db.session.query(Category.id, Category.name, db.func.count(Idea.id))
        .outerjoin(Idea, Idea.category_id == Category.id)
        .group_by(Category.id, Category.name)
        .order_by(db.func.count(Idea.id).desc(), Category.name)
        .all()
    )
    top_count = max([r[2] for r in rows] + [1])
    categories = [{"id": r[0], "name": r[1], "count": r[2], "pct": round(100 * r[2] / top_count)} for r in rows]
    return render_template(
        "index.html",
        stats=stats,
        top_ideas=top_ideas,
        recent_ideas=recent_ideas,
        categories=categories,
        contributors=top_contributors(),
    )


@bp.route("/u/<username>")
def user_profile(username):
    """Public profile: who someone is and what they have contributed."""
    user = User.query.filter(db.func.lower(User.username) == username.lower()).first() or abort(404)
    ideas = (
        Idea.query.options(joinedload(Idea.category))
        .filter_by(submitter_id=user.id)
        .order_by(Idea.created_at.desc())
        .all()
    )
    votes_received = (
        db.session.query(db.func.coalesce(db.func.sum(Vote.vote_type), 0))
        .join(Idea, Idea.id == Vote.idea_id)
        .filter(Idea.submitter_id == user.id)
        .scalar()
    )
    stats = {
        "ideas": len(ideas),
        "accepted": sum(1 for i in ideas if i.status in (STATUS_APPROVED, STATUS_IMPLEMENTED)),
        "score": int(votes_received or 0),
        "comments": Comment.query.filter_by(user_id=user.id, is_deleted=False).count(),
    }
    return render_template("user.html", member=user, ideas=ideas, stats=stats)


@bp.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    form = FeedbackForm()
    if form.validate_on_submit():
        db.session.add(
            Feedback(user_id=current_user.id, kind=form.kind.data, message=form.message.data.strip())
        )
        db.session.commit()
        flash("Thank you! Your feedback has been sent to the administrators.", "success")
        return redirect(url_for("main.feedback"))
    return render_template("feedback.html", form=form)


@bp.route("/about")
def about():
    return render_template("about.html")


@bp.route("/healthz")
def healthz():
    """Used by hosting platforms as a liveness probe."""
    db.session.execute(db.text("SELECT 1"))
    return jsonify(status="ok")
