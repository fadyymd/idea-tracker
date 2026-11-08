import re
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import abort, current_app, request
from flask_login import current_user

from .models import ROLE_ADMIN, ROLE_REVIEWER


def roles_required(*roles):
    """Role-based access control decorator (not signed in -> login page, wrong role -> 403)."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


admin_required = roles_required(ROLE_ADMIN)
reviewer_required = roles_required(ROLE_REVIEWER, ROLE_ADMIN)


def is_safe_redirect(target: str | None) -> bool:
    """Only allow redirects that stay on this host (prevents open-redirect attacks)."""
    if not target:
        return False
    host_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and host_url.netloc == test_url.netloc


def normalize_name(value: str) -> str:
    """Trim and collapse inner whitespace: '  Green   Tech ' -> 'Green Tech'."""
    return re.sub(r"\s+", " ", (value or "").strip())


def build_comment_tree(comments):
    """Turn a flat, time-ordered list of comments into a forest.

    Each comment receives a transient ``children`` list; the list of root
    comments is returned.
    """
    by_id = {c.id: c for c in comments}
    for c in comments:
        c.children = []
    roots = []
    for c in comments:
        parent = by_id.get(c.parent_id)
        if parent is not None:
            parent.children.append(c)
        else:
            roots.append(c)
    return roots
