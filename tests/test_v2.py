"""Tests for the second iteration: bug fixes, review queue, profiles, export, throttling, CSP."""
import csv
import io
from datetime import timedelta

from app import create_app
from app.extensions import db
from app.models import Category, Comment, Idea, User, Vote, utcnow
from app.security import login_throttle
from config import TestConfig
from tests.conftest import login, make_user

FETCH = {"X-Requested-With": "fetch"}


def new_idea(author, title="Another useful idea", status="pending", cat=None):
    cat = cat or Category.query.first()
    idea = Idea(title=title, description="d" * 30, category_id=cat.id, submitter_id=author.id, status=status)
    db.session.add(idea)
    db.session.commit()
    return idea


class TestBugFixes:
    def test_underscore_username_is_not_a_wildcard_clash(self, client, users):
        """Regression: ilike() treated '_' as a wildcard, so 'a_ice' was reported as taken by 'alice'."""
        r = client.post("/register", data={"username": "a_ice", "email": "a_ice@example.com",
                                           "password": "Secret123", "confirm": "Secret123"}, follow_redirects=True)
        assert User.query.filter_by(username="a_ice").count() == 1 and r.status_code == 200

    def test_percent_in_email_is_not_a_wildcard(self, client, users):
        r = client.post("/register", data={"username": "pct", "email": "%@example.com",
                                           "password": "Secret123", "confirm": "Secret123"})
        assert b"already exists" not in r.data

    def test_admin_user_search_escapes_wildcards(self, as_user, users):
        html = as_user("root").get("/admin/users?q=%25").data
        assert b"No users found" in html

    def test_no_wtforms_deprecation_warnings(self, app, recwarn):
        from app.forms import IdeaForm, ReviewForm
        with app.test_request_context():
            IdeaForm(); ReviewForm()
        assert not [w for w in recwarn if issubclass(w.category, DeprecationWarning) and "SelectField" in str(w.message)]

    def test_secret_key_is_not_the_old_hardcoded_default(self):
        from config import Config
        assert Config.SECRET_KEY != "dev-only-change-me" and len(Config.SECRET_KEY) >= 32


class TestLoginThrottle:
    def test_blocks_after_repeated_failures_then_recovers(self, client, users):
        for _ in range(5):
            r = login(client, "alice", "wrong-password")
            assert r.status_code == 200
        r = login(client, "alice", "Passw0rd!x")          # correct password, but locked out
        assert r.status_code == 429 and b"Too many failed attempts" in r.data
        login_throttle.clear_all()
        assert b"Welcome back" in login(client, "alice", follow_redirects=True).data

    def test_success_resets_counter(self, client, users):
        for _ in range(4):
            login(client, "alice", "nope")
        assert b"Welcome back" in login(client, "alice", follow_redirects=True).data
        client.post("/logout")
        for _ in range(4):
            assert login(client, "alice", "nope").status_code == 200

    def test_throttle_is_per_account(self, client, users):
        for _ in range(5):
            login(client, "alice", "nope")
        assert b"Welcome back" in login(client, "bob", follow_redirects=True).data


class TestSecurityHeaders:
    def test_csp_and_friends(self, client):
        h = client.get("/").headers
        csp = h["Content-Security-Policy"]
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
        assert "cdn" not in csp and h["Permissions-Policy"]

    def test_pages_have_no_inline_or_external_scripts(self, client, users, idea):
        import re
        for url in ("/", "/ideas", f"/ideas/{idea.id}", "/login", "/register", "/about"):
            html = client.get(url).data.decode()
            for tag in re.findall(r"<script\b[^>]*>", html):
                assert "src=" in tag and "http" not in tag, f"{url}: {tag}"
            assert "onclick=" not in html and "https://cdn" not in html

    def test_admin_dashboard_has_only_json_data_block(self, as_user):
        html = as_user("root").get("/admin/").data.decode()
        assert 'type="application/json" id="chart-data"' in html

    def test_vendored_assets_are_served(self, client):
        for path in ("vendor/bootstrap/bootstrap.min.css", "vendor/bootstrap/bootstrap.bundle.min.js",
                     "vendor/icons/bootstrap-icons.min.css", "vendor/icons/fonts/bootstrap-icons.woff2",
                     "vendor/chartjs/chart.umd.min.js", "vendor/fonts/inter-latin-wght-normal.woff2",
                     "css/style.css", "js/app.js", "logo.svg"):
            assert client.get(f"/static/{path}").status_code == 200, path

    def test_hsts_only_on_https(self, client):
        assert "Strict-Transport-Security" not in client.get("/").headers
        assert "Strict-Transport-Security" in client.get("/", base_url="https://localhost").headers


class TestReviewQueue:
    def test_requires_reviewer(self, client, users):
        assert client.get("/review").status_code == 302
        login(client, "bob")
        assert client.get("/review").status_code == 403

    def test_lists_pending_oldest_first_and_quick_approve(self, client, users):
        old = new_idea(users["alice"], "Older pending idea")
        old.created_at = utcnow() - timedelta(days=3)
        new = new_idea(users["bob"], "Newer pending idea")
        done = new_idea(users["bob"], "Already approved idea", status="approved")
        db.session.commit()
        login(client, "rita")
        html = client.get("/review").data.decode()
        assert html.index("Older pending idea") < html.index("Newer pending idea")
        assert "Already approved idea" not in html
        r = client.post(f"/ideas/{old.id}/review", data={"status": "approved", "next": "/review"})
        assert r.status_code == 302 and r.headers["Location"].endswith("/review")
        db.session.refresh(old)
        assert old.status == "approved" and old.reviewed_by.username == "rita"

    def test_quick_action_keeps_existing_note(self, client, users):
        idea = new_idea(users["alice"])
        idea.review_note = "Please add a budget."
        db.session.commit()
        login(client, "rita")
        client.post(f"/ideas/{idea.id}/review", data={"status": "under_review"})
        db.session.refresh(idea)
        assert idea.review_note == "Please add a budget." and idea.status == "under_review"

    def test_review_redirect_rejects_external_next(self, client, users):
        idea = new_idea(users["alice"])
        login(client, "rita")
        r = client.post(f"/ideas/{idea.id}/review", data={"status": "approved", "next": "https://evil.example"})
        assert "evil.example" not in r.headers["Location"]

    def test_nav_badge_shows_pending_count_for_reviewers_only(self, client, users):
        new_idea(users["alice"]); new_idea(users["bob"])
        login(client, "rita")
        assert b'class="nav-badge">2<' in client.get("/").data
        client.post("/logout"); login(client, "bob")
        assert b"nav-badge" not in client.get("/").data


class TestPublicProfile:
    def test_profile_stats(self, client, users):
        a = new_idea(users["alice"], "Alice approved idea", status="approved")
        new_idea(users["alice"], "Alice pending idea")
        db.session.add_all([Vote(idea_id=a.id, user_id=users["bob"].id, vote_type=1),
                            Vote(idea_id=a.id, user_id=users["rita"].id, vote_type=1)])
        db.session.commit()
        html = client.get("/u/Alice").data.decode()          # case-insensitive
        assert "Alice approved idea" in html and "Alice pending idea" in html
        assert "Votes received" in html

    def test_unknown_user_404(self, client):
        assert client.get("/u/nobody").status_code == 404

    def test_profile_is_xss_safe(self, client, app):
        make_user("evil.name")
        assert client.get("/u/evil.name").status_code == 200


class TestLeaderboardAndTrending:
    def test_home_lists_contributors(self, client, users):
        i = new_idea(users["alice"])
        db.session.add(Vote(idea_id=i.id, user_id=users["bob"].id, vote_type=1)); db.session.commit()
        html = client.get("/").data.decode()
        assert "Top contributors" in html and "alice" in html

    def test_trending_prefers_recent_activity(self, client, users):
        old = new_idea(users["alice"], "Old but popular idea")
        fresh = new_idea(users["alice"], "Fresh and active idea")
        stale = utcnow() - timedelta(days=30)
        db.session.add_all([
            Vote(idea_id=old.id, user_id=users["bob"].id, vote_type=1, created_at=stale),
            Vote(idea_id=old.id, user_id=users["rita"].id, vote_type=1, created_at=stale),
            Vote(idea_id=fresh.id, user_id=users["bob"].id, vote_type=1),
        ])
        db.session.commit()
        html = client.get("/ideas?sort=trending").data.decode()
        assert html.index("Fresh and active idea") < html.index("Old but popular idea")
        html = client.get("/ideas?sort=top").data.decode()
        assert html.index("Old but popular idea") < html.index("Fresh and active idea")


class TestExportAndMisc:
    def test_csv_export_admin_only_and_safe(self, client, users):
        new_idea(users["alice"], "=HYPERLINK(\"http://x\")")
        assert client.get("/admin/export/ideas.csv").status_code == 302
        login(client, "rita")
        assert client.get("/admin/export/ideas.csv").status_code == 403
        client.post("/logout"); login(client, "root")
        r = client.get("/admin/export/ideas.csv")
        assert r.mimetype == "text/csv" and "attachment" in r.headers["Content-Disposition"]
        rows = list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
        assert rows[0][:3] == ["id", "title", "category"]
        assert rows[1][1].startswith("'=")                      # formula injection neutralised

    def test_about_page(self, client):
        assert b"Idea lifecycle" in client.get("/about").data

    def test_detail_shows_related_ideas_and_stepper(self, client, users, idea):
        other = new_idea(users["bob"], "Sibling idea in category", cat=idea.category)
        html = client.get(f"/ideas/{idea.id}").data.decode()
        assert "Sibling idea in category" in html and 'class="stepper' in html

    def test_vote_buttons_disabled_on_own_idea(self, as_user, idea):
        html = as_user("alice").get(f"/ideas/{idea.id}").data.decode()
        assert html.count("vote-btn") >= 2 and "disabled" in html.split("vote-up")[1][:200]

    def test_status_filter_tabs(self, client, users):
        new_idea(users["alice"], "Approved one here", status="approved")
        new_idea(users["alice"], "Pending one here")
        html = client.get("/ideas?status=approved").data.decode()
        assert "Approved one here" in html and "Pending one here" not in html

    def test_bootstrap_is_idempotent(self, app):
        from app import bootstrap_database
        before = Category.query.count()
        bootstrap_database(); bootstrap_database()
        assert Category.query.count() == before

    def test_error_pages_render_with_layout(self, client):
        r = client.get("/missing")
        assert r.status_code == 404 and b"Page not found" in r.data and b"error-code" in r.data
