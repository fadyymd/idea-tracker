"""Database models.

Tables required by the assignment:
    Users, Ideas, Votes, Comments
Additional tables:
    Categories (dynamic categories) and Feedback (feedback loop, "Final Touches")
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import column_property
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


def utcnow() -> datetime:
    """Timezone-aware UTC "now" stored as naive UTC (portable across SQLite/PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# SQLite ignores foreign keys unless asked; we rely on ON DELETE CASCADE.
@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _record):
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# --------------------------------------------------------------------------- #
# Roles & statuses
# --------------------------------------------------------------------------- #
ROLE_SUBMITTER = "submitter"
ROLE_REVIEWER = "reviewer"
ROLE_ADMIN = "administrator"
ROLES = (ROLE_SUBMITTER, ROLE_REVIEWER, ROLE_ADMIN)

STATUS_PENDING = "pending"
STATUS_REVIEW = "under_review"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_IMPLEMENTED = "implemented"
STATUSES = (STATUS_PENDING, STATUS_REVIEW, STATUS_APPROVED, STATUS_REJECTED, STATUS_IMPLEMENTED)

STATUS_LABELS = {
    STATUS_PENDING: "Pending",
    STATUS_REVIEW: "Under review",
    STATUS_APPROVED: "Approved",
    STATUS_REJECTED: "Rejected",
    STATUS_IMPLEMENTED: "Implemented",
}
STATUS_COLORS = {
    STATUS_PENDING: "secondary",
    STATUS_REVIEW: "info",
    STATUS_APPROVED: "success",
    STATUS_REJECTED: "danger",
    STATUS_IMPLEMENTED: "primary",
}

STATUS_ICONS = {
    STATUS_PENDING: "hourglass-split",
    STATUS_REVIEW: "search",
    STATUS_APPROVED: "check-circle-fill",
    STATUS_REJECTED: "x-circle-fill",
    STATUS_IMPLEMENTED: "rocket-takeoff-fill",
}

DEFAULT_CATEGORIES = (
    ("Technology", "New tools, software, hardware and automation."),
    ("Process Improvement", "Faster, cheaper or simpler ways of working."),
    ("Customer Experience", "Better products, services and support for users."),
    ("Sustainability", "Reducing waste and environmental impact."),
    ("Education & Training", "Learning, skills and knowledge sharing."),
    ("Workplace Culture", "Collaboration, wellbeing and team life."),
)


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_SUBMITTER)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    ideas = db.relationship(
        "Idea", back_populates="submitter", foreign_keys="Idea.submitter_id",
        passive_deletes=True,
    )
    votes = db.relationship("Vote", back_populates="user", passive_deletes=True)
    comments = db.relationship("Comment", back_populates="user", passive_deletes=True)

    # -- password helpers -------------------------------------------------- #
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # -- role helpers ------------------------------------------------------ #
    @property
    def is_active(self) -> bool:  # Flask-Login hook: inactive users cannot log in
        return bool(self.is_active_account)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_reviewer(self) -> bool:
        return self.role in (ROLE_REVIEWER, ROLE_ADMIN)

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=False, default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    ideas = db.relationship("Idea", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"


class Idea(db.Model):
    __tablename__ = "ideas"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    submitter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING, index=True)
    review_note = db.Column(db.Text, nullable=False, default="")
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    category = db.relationship("Category", back_populates="ideas")
    submitter = db.relationship("User", back_populates="ideas", foreign_keys=[submitter_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    votes = db.relationship(
        "Vote", back_populates="idea", cascade="all, delete-orphan", passive_deletes=True
    )
    comments = db.relationship(
        "Comment", back_populates="idea", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Comment.created_at",
    )

    # -- helpers ----------------------------------------------------------- #
    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self) -> str:
        return STATUS_COLORS.get(self.status, "secondary")

    @property
    def status_icon(self) -> str:
        return STATUS_ICONS.get(self.status, "circle")

    @property
    def upvotes(self) -> int:
        return sum(1 for v in self.votes if v.vote_type == 1)

    @property
    def downvotes(self) -> int:
        return sum(1 for v in self.votes if v.vote_type == -1)

    def vote_of(self, user) -> int:
        """Return +1, -1 or 0 for the given user."""
        if user is None or not getattr(user, "is_authenticated", False):
            return 0
        for v in self.votes:
            if v.user_id == user.id:
                return v.vote_type
        return 0

    def __repr__(self) -> str:
        return f"<Idea {self.id} {self.title!r}>"


class Vote(db.Model):
    __tablename__ = "votes"

    id = db.Column(db.Integer, primary_key=True)
    idea_id = db.Column(db.Integer, db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    vote_type = db.Column(db.SmallInteger, nullable=False)  # +1 upvote, -1 downvote
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    idea = db.relationship("Idea", back_populates="votes")
    user = db.relationship("User", back_populates="votes")

    __table_args__ = (
        db.UniqueConstraint("idea_id", "user_id", name="uq_vote_idea_user"),
        db.CheckConstraint("vote_type IN (-1, 1)", name="ck_vote_type"),
    )


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    idea_id = db.Column(db.Integer, db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id", ondelete="CASCADE"), index=True)
    content = db.Column(db.Text, nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)  # "Timestamp"

    idea = db.relationship("Idea", back_populates="comments")
    user = db.relationship("User", back_populates="comments")
    parent = db.relationship("Comment", remote_side=[id], back_populates="replies")
    replies = db.relationship(
        "Comment", back_populates="parent", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Comment.created_at",
    )


class Feedback(db.Model):
    """Feedback loop: users report issues or suggest improvements for the platform."""
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    kind = db.Column(db.String(20), nullable=False, default="suggestion")  # bug / suggestion / other
    message = db.Column(db.Text, nullable=False)
    resolved = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")


# --------------------------------------------------------------------------- #
# Computed columns usable in ORDER BY (defined after Vote/Comment exist)
# --------------------------------------------------------------------------- #
Idea.score = column_property(
    select(func.coalesce(func.sum(Vote.vote_type), 0))
    .where(Vote.idea_id == Idea.id)
    .correlate_except(Vote)
    .scalar_subquery()
)
Idea.comment_count = column_property(
    select(func.count(Comment.id))
    .where(Comment.idea_id == Idea.id, Comment.is_deleted.is_(False))
    .correlate_except(Comment)
    .scalar_subquery()
)
