"""Functional test-suite (Step 4 – Testing). Run with:  pytest -v"""
from app import create_app
from app.extensions import db
from app.models import (
    Category, Comment, Feedback, Idea, User, Vote,
    STATUS_APPROVED, STATUS_PENDING,
)
from config import TestConfig
from tests.conftest import login, make_user

FETCH = {"X-Requested-With": "fetch"}


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
class TestAuth:
    def test_register_creates_submitter_and_hashes_password(self, client):
        r = client.post("/register", data={
            "username": "newbie", "email": "n@example.com",
            "password": "Secret123", "confirm": "Secret123"}, follow_redirects=True)
        assert r.status_code == 200
        user = User.query.filter_by(username="newbie").one()
        assert user.role == "submitter"
        assert user.password_hash != "Secret123" and user.check_password("Secret123")

    def test_register_rejects_weak_or_mismatched_password(self, client):
        r = client.post("/register", data={
            "username": "weak", "email": "w@example.com", "password": "short", "confirm": "short"})
        assert b"8" in r.data and User.query.filter_by(username="weak").first() is None
        r = client.post("/register", data={
            "username": "weak", "email": "w@example.com", "password": "Secret123", "confirm": "Other123"})
        assert b"do not match" in r.data

    def test_register_rejects_duplicates_case_insensitively(self, client, users):
        r = client.post("/register", data={
            "username": "ALICE", "email": "x@example.com", "password": "Secret123", "confirm": "Secret123"})
        assert b"already taken" in r.data
        r = client.post("/register", data={
            "username": "other", "email": "ALICE@example.com", "password": "Secret123", "confirm": "Secret123"})
        assert b"already exists" in r.data

    def test_login_logout(self, client, users):
        r = login(client, "alice", follow_redirects=True)
        assert b"Welcome back" in r.data
        r = client.post("/logout", follow_redirects=True)
        assert b"signed out" in r.data

    def test_login_with_email_and_wrong_password(self, client, users):
        assert b"Welcome back" in login(client, "alice@example.com", follow_redirects=True).data
        client.post("/logout")
        assert b"Invalid" in login(client, "alice", "wrong", follow_redirects=True).data

    def test_disabled_account_cannot_login(self, client, users):
        users["bob"].is_active_account = False
        db.session.commit()
        assert b"disabled" in login(client, "bob", follow_redirects=True).data

    def test_open_redirect_is_blocked(self, client, users):
        r = client.post("/login?next=https://evil.example/", data={"identifier": "alice", "password": "Passw0rd!x"})
        assert r.status_code == 302 and "evil.example" not in r.headers["Location"]
        client.post("/logout")
        r = client.post("/login?next=/ideas", data={"identifier": "alice", "password": "Passw0rd!x"})
        assert r.headers["Location"].endswith("/ideas")

    def test_protected_pages_redirect_to_login(self, client):
        for url in ("/ideas/new", "/my-ideas", "/profile", "/feedback"):
            r = client.get(url)
            assert r.status_code == 302 and "/login" in r.headers["Location"]

    def test_change_password(self, client, users):
        login(client, "alice")
        client.post("/profile", data={"c-current_password": "wrong", "c-new_password": "NewPass123",
                                      "c-confirm": "NewPass123", "c-submit": "1"})
        assert users["alice"].check_password("Passw0rd!x")
        client.post("/profile", data={"c-current_password": "Passw0rd!x", "c-new_password": "NewPass123",
                                      "c-confirm": "NewPass123", "c-submit": "1"})
        db.session.refresh(users["alice"])
        assert users["alice"].check_password("NewPass123")


# --------------------------------------------------------------------------- #
# Ideas & categories
# --------------------------------------------------------------------------- #
class TestIdeas:
    def test_default_categories_exist(self, app):
        names = {c.name for c in Category.query.all()}
        assert {"Technology", "Process Improvement", "Customer Experience"} <= names

    def test_submit_idea_with_existing_category(self, as_user, users):
        c = as_user("alice")
        cat = Category.query.filter_by(name="Technology").one()
        r = c.post("/ideas/new", data={"title": "Chatbot for support", "description": "A chatbot that answers common questions quickly.",
                                       "category": cat.id}, follow_redirects=True)
        assert r.status_code == 200 and b"Chatbot for support" in r.data
        idea = Idea.query.one()
        assert idea.status == STATUS_PENDING and idea.submitter_id == users["alice"].id

    def test_submit_idea_creates_dynamic_category_once(self, as_user):
        c = as_user("alice")
        data = {"title": "Standing desks", "description": "Offer adjustable standing desks to everybody.",
                "category": 0, "new_category": "  health   &  safety "}
        c.post("/ideas/new", data=data)
        c.post("/ideas/new", data={**data, "title": "Eye breaks", "new_category": "HEALTH & SAFETY"})
        assert Category.query.filter(db.func.lower(Category.name) == "health & safety").count() == 1
        assert Idea.query.count() == 2

    def test_idea_validation(self, as_user):
        c = as_user("alice")
        r = c.post("/ideas/new", data={"title": "abc", "description": "short", "category": 0})
        assert Idea.query.count() == 0 and r.status_code == 200
        r = c.post("/ideas/new", data={"title": "Valid title here", "description": "A long enough description text.", "category": 0})
        assert b"Choose a category" in r.data and Idea.query.count() == 0

    def test_anonymous_can_read_but_not_write(self, client, idea):
        assert client.get("/ideas").status_code == 200
        assert b"Solar roof" in client.get(f"/ideas/{idea.id}").data
        r = client.post(f"/ideas/{idea.id}/comments", data={"content": "hi"})
        assert r.status_code == 302 and "/login" in r.headers["Location"]

    def test_xss_is_escaped(self, as_user, users):
        c = as_user("alice")
        cat = Category.query.first()
        c.post("/ideas/new", data={"title": "<script>alert(1)</script>", "description": "<img src=x onerror=alert(1)> padding text",
                                   "category": cat.id})
        html = c.get("/ideas").data
        assert b"<script>alert(1)</script>" not in html and b"&lt;script&gt;" in html

    def test_owner_edit_delete_rules(self, client, users, idea):
        login(client, "bob")
        assert client.get(f"/ideas/{idea.id}/edit").status_code == 403
        assert client.post(f"/ideas/{idea.id}/delete").status_code == 403
        client.post("/logout")
        login(client, "alice")
        cat = Category.query.first()
        r = client.post(f"/ideas/{idea.id}/edit", data={"title": "Solar roof v2", "description": "Updated description with details.",
                                                        "category": cat.id}, follow_redirects=True)
        assert b"Solar roof v2" in r.data
        # once reviewed, the owner can no longer change it
        idea.status = STATUS_APPROVED
        db.session.commit()
        assert client.get(f"/ideas/{idea.id}/edit").status_code == 403
        assert client.post(f"/ideas/{idea.id}/delete").status_code == 403

    def test_admin_can_delete_any_idea_and_cascade_cleans_up(self, client, users, idea):
        db.session.add(Vote(idea_id=idea.id, user_id=users["bob"].id, vote_type=1))
        db.session.add(Comment(idea_id=idea.id, user_id=users["bob"].id, content="nice"))
        db.session.commit()
        login(client, "root")
        client.post(f"/ideas/{idea.id}/delete")
        assert Idea.query.count() == 0 and Vote.query.count() == 0 and Comment.query.count() == 0

    def test_my_ideas_only_lists_own(self, as_user, users, idea):
        assert b"Solar roof" in as_user("alice").get("/my-ideas").data
        assert b"Solar roof" not in as_user("bob").get("/my-ideas").data

    def test_search_filter_sort_pagination(self, client, users):
        cats = Category.query.order_by(Category.id).all()
        for i in range(12):
            db.session.add(Idea(title=f"Idea number {i:02d}", description="d" * 30,
                                category_id=cats[i % 2].id, submitter_id=users["alice"].id))
        db.session.commit()
        assert client.get("/ideas").data.count(b'class="card idea-card') == 8       # page size
        assert client.get("/ideas?page=2").data.count(b'class="card idea-card') == 4
        assert b"Idea number 07" in client.get("/ideas?q=number+07").data
        assert b"Idea number 06" not in client.get("/ideas?q=number+07").data
        only = client.get(f"/ideas?category={cats[0].id}&per=1").data
        assert only.count(b'class="card idea-card') == 6
        assert client.get("/ideas?q=%25").data.count(b'class="card idea-card') == 0     # wildcard is escaped
        assert client.get("/ideas?sort=bogus").status_code == 200

    def test_sort_by_top(self, client, users):
        cat = Category.query.first()
        a = Idea(title="Low scoring idea", description="d" * 30, category_id=cat.id, submitter_id=users["alice"].id)
        b = Idea(title="High scoring idea", description="d" * 30, category_id=cat.id, submitter_id=users["alice"].id)
        db.session.add_all([a, b]); db.session.commit()
        db.session.add_all([Vote(idea_id=b.id, user_id=users["bob"].id, vote_type=1),
                            Vote(idea_id=b.id, user_id=users["rita"].id, vote_type=1),
                            Vote(idea_id=a.id, user_id=users["bob"].id, vote_type=-1)])
        db.session.commit()
        html = client.get("/ideas?sort=top").data.decode()
        assert html.index("High scoring idea") < html.index("Low scoring idea")


# --------------------------------------------------------------------------- #
# Voting
# --------------------------------------------------------------------------- #
class TestVoting:
    def vote(self, c, idea, value):
        return c.post(f"/ideas/{idea.id}/vote", data={"value": value}, headers=FETCH)

    def test_upvote_change_and_withdraw(self, as_user, idea):
        c = as_user("bob")
        j = self.vote(c, idea, 1).get_json()
        assert (j["score"], j["upvotes"], j["my_vote"]) == (1, 1, 1)
        j = self.vote(c, idea, -1).get_json()
        assert (j["score"], j["downvotes"], j["my_vote"]) == (-1, 1, -1)
        j = self.vote(c, idea, -1).get_json()      # same arrow again = withdraw
        assert (j["score"], j["my_vote"]) == (0, 0)
        assert Vote.query.count() == 0

    def test_one_vote_per_user_and_scores_add_up(self, client, users, idea):
        for name in ("bob", "rita"):
            login(client, name)
            self.vote(client, idea, 1)
            self.vote(client, idea, 1); self.vote(client, idea, 1)  # toggled off then on
            client.post("/logout")
        assert Vote.query.count() == 2
        db.session.refresh(idea)
        assert idea.score == 2

    def test_cannot_vote_on_own_idea(self, as_user, idea):
        r = self.vote(as_user("alice"), idea, 1)
        assert r.status_code == 403 and Vote.query.count() == 0

    def test_anonymous_vote_returns_401_json(self, client, idea):
        r = self.vote(client, idea, 1)
        assert r.status_code == 401 and "login" in r.get_json()

    def test_invalid_vote_value(self, as_user, idea):
        assert self.vote(as_user("bob"), idea, 5).status_code == 400
        assert self.vote(as_user("bob"), idea, "x").status_code == 400

    def test_vote_unknown_idea_404(self, as_user):
        assert as_user("bob").post("/ideas/999/vote", data={"value": 1}, headers=FETCH).status_code == 404

    def test_non_ajax_vote_redirects(self, as_user, idea):
        r = as_user("bob").post(f"/ideas/{idea.id}/vote", data={"value": 1})
        assert r.status_code == 302 and Vote.query.count() == 1


# --------------------------------------------------------------------------- #
# Comments
# --------------------------------------------------------------------------- #
class TestComments:
    def test_post_comment_and_threaded_reply(self, as_user, idea):
        c = as_user("bob")
        c.post(f"/ideas/{idea.id}/comments", data={"content": "Great idea!"})
        root = Comment.query.one()
        c.post(f"/ideas/{idea.id}/comments", data={"content": "Agreed", "parent_id": str(root.id)})
        reply = Comment.query.filter_by(content="Agreed").one()
        assert reply.parent_id == root.id and reply.idea_id == idea.id
        html = c.get(f"/ideas/{idea.id}").data
        assert b"Great idea!" in html and b"Agreed" in html and b"comment-children" in html

    def test_reply_to_comment_of_other_idea_is_rejected(self, as_user, users, idea):
        other = Idea(title="Another idea entirely", description="d" * 30, category_id=idea.category_id, submitter_id=users["bob"].id)
        db.session.add(other); db.session.commit()
        foreign = Comment(idea_id=other.id, user_id=users["bob"].id, content="elsewhere")
        db.session.add(foreign); db.session.commit()
        c = as_user("rita")
        c.post(f"/ideas/{idea.id}/comments", data={"content": "sneaky", "parent_id": str(foreign.id)})
        assert Comment.query.filter_by(content="sneaky").count() == 0

    def test_empty_and_overlong_comments_rejected(self, as_user, idea):
        c = as_user("bob")
        c.post(f"/ideas/{idea.id}/comments", data={"content": "   "})
        c.post(f"/ideas/{idea.id}/comments", data={"content": "x" * 2001})
        assert Comment.query.count() == 0

    def test_delete_rules(self, client, users, idea):
        mine = Comment(idea_id=idea.id, user_id=users["bob"].id, content="mine")
        db.session.add(mine); db.session.commit()
        login(client, "rita")
        assert client.post(f"/comments/{mine.id}/delete").status_code == 403
        client.post("/logout"); login(client, "bob")
        client.post(f"/comments/{mine.id}/delete")
        assert Comment.query.count() == 0           # leaf -> hard delete

    def test_deleting_parent_keeps_thread(self, client, users, idea):
        parent = Comment(idea_id=idea.id, user_id=users["bob"].id, content="parent text")
        db.session.add(parent); db.session.commit()
        db.session.add(Comment(idea_id=idea.id, user_id=users["rita"].id, parent_id=parent.id, content="child text"))
        db.session.commit()
        login(client, "bob")
        client.post(f"/comments/{parent.id}/delete")
        html = client.get(f"/ideas/{idea.id}").data
        assert b"[comment removed]" in html and b"child text" in html and b"parent text" not in html

    def test_admin_can_delete_any_comment(self, client, users, idea):
        c = Comment(idea_id=idea.id, user_id=users["bob"].id, content="spam")
        db.session.add(c); db.session.commit()
        login(client, "root")
        client.post(f"/comments/{c.id}/delete")
        assert Comment.query.count() == 0

    def test_comment_html_is_escaped(self, as_user, idea):
        c = as_user("bob")
        c.post(f"/ideas/{idea.id}/comments", data={"content": "<b onmouseover=x>bold</b>"})
        assert b"<b onmouseover" not in c.get(f"/ideas/{idea.id}").data


# --------------------------------------------------------------------------- #
# Roles, evaluation, admin area
# --------------------------------------------------------------------------- #
class TestRoles:
    def review(self, c, idea, status="approved", note="Looks good"):
        return c.post(f"/ideas/{idea.id}/review", data={"status": status, "review_note": note}, follow_redirects=True)

    def test_reviewer_can_evaluate(self, as_user, users, idea):
        r = self.review(as_user("rita"), idea)
        assert b"Evaluation saved" in r.data
        db.session.refresh(idea)
        assert idea.status == "approved" and idea.reviewed_by_id == users["rita"].id and idea.review_note == "Looks good"

    def test_submitter_cannot_evaluate(self, as_user, idea):
        assert as_user("bob").post(f"/ideas/{idea.id}/review", data={"status": "approved"}).status_code == 403

    def test_anonymous_review_redirects_to_login(self, client, idea):
        r = client.post(f"/ideas/{idea.id}/review", data={"status": "approved"})
        assert r.status_code == 302 and "/login" in r.headers["Location"]

    def test_reviewer_cannot_review_own_idea(self, client, users):
        cat = Category.query.first()
        own = Idea(title="Reviewer's own idea", description="d" * 30, category_id=cat.id, submitter_id=users["rita"].id)
        db.session.add(own); db.session.commit()
        login(client, "rita")
        assert client.post(f"/ideas/{own.id}/review", data={"status": "approved"}).status_code == 403

    def test_invalid_status_rejected(self, as_user, idea):
        self.review(as_user("rita"), idea, status="hacked")
        db.session.refresh(idea)
        assert idea.status == "pending"

    def test_review_form_only_shown_to_reviewers(self, client, users, idea):
        login(client, "bob")
        assert b"Reviewer evaluation" not in client.get(f"/ideas/{idea.id}").data
        client.post("/logout"); login(client, "rita")
        assert b"Reviewer evaluation" in client.get(f"/ideas/{idea.id}").data


class TestAdmin:
    def test_admin_area_requires_admin(self, client, users):
        for url in ("/admin/", "/admin/users", "/admin/categories", "/admin/feedback"):
            assert client.get(url).status_code == 302
        login(client, "rita")
        for url in ("/admin/", "/admin/users", "/admin/categories", "/admin/feedback"):
            assert client.get(url).status_code == 403
        client.post("/logout"); login(client, "root")
        for url in ("/admin/", "/admin/users", "/admin/categories", "/admin/feedback"):
            assert client.get(url).status_code == 200

    def test_change_role(self, as_user, users):
        c = as_user("root")
        c.post(f"/admin/users/{users['bob'].id}/role", data={"role": "reviewer"})
        db.session.refresh(users["bob"])
        assert users["bob"].role == "reviewer"
        assert c.post(f"/admin/users/{users['bob'].id}/role", data={"role": "god"}).status_code == 400

    def test_admin_cannot_demote_or_disable_self(self, as_user, users):
        c = as_user("root")
        c.post(f"/admin/users/{users['root'].id}/role", data={"role": "submitter"})
        c.post(f"/admin/users/{users['root'].id}/toggle")
        db.session.refresh(users["root"])
        assert users["root"].is_admin and users["root"].is_active_account

    def test_cannot_disable_last_active_admin(self, as_user, users):
        other = make_user("root2", "administrator")
        c = as_user("root")
        c.post(f"/admin/users/{other.id}/toggle")            # fine, root still active
        assert not db.session.get(User, other.id).is_active_account
        users["bob"].role = "administrator"; db.session.commit()
        c.post(f"/admin/users/{users['bob'].id}/toggle")
        assert not db.session.get(User, users["bob"].id).is_active_account

    def test_disable_toggle(self, as_user, users):
        c = as_user("root")
        c.post(f"/admin/users/{users['bob'].id}/toggle")
        assert not db.session.get(User, users["bob"].id).is_active_account

    def test_disabled_user_session_is_invalidated(self, client, users):
        login(client, "bob")
        users["bob"].is_active_account = False
        db.session.commit()
        r = client.get("/ideas/new")
        assert r.status_code == 302 and "/login" in r.headers["Location"]

    def test_category_crud_and_protection(self, as_user, users, idea):
        c = as_user("root")
        c.post("/admin/categories", data={"name": "Finance", "description": "Money matters"})
        fin = Category.query.filter_by(name="Finance").one()
        c.post("/admin/categories", data={"name": "finance"})                    # duplicate
        assert Category.query.filter(db.func.lower(Category.name) == "finance").count() == 1
        c.post(f"/admin/categories/{fin.id}/rename", data={"name": "Finance & Budget"})
        assert db.session.get(Category, fin.id).name == "Finance & Budget"
        c.post(f"/admin/categories/{idea.category_id}/delete")                    # still has an idea
        assert db.session.get(Category, idea.category_id) is not None
        c.post(f"/admin/categories/{fin.id}/delete")
        assert db.session.get(Category, fin.id) is None

    def test_dashboard_counts(self, as_user, idea):
        html = as_user("root").get("/admin/").data
        assert b"Awaiting review" in html and b"statusChart" in html


# --------------------------------------------------------------------------- #
# Feedback loop, misc
# --------------------------------------------------------------------------- #
class TestFeedbackAndMisc:
    def test_feedback_roundtrip(self, client, users):
        login(client, "bob")
        client.post("/feedback", data={"kind": "bug", "message": "The vote button flickers on mobile."})
        fb = Feedback.query.one()
        assert fb.kind == "bug" and fb.user_id == users["bob"].id and not fb.resolved
        client.post("/logout"); login(client, "root")
        assert b"flickers" in client.get("/admin/feedback").data
        client.post(f"/admin/feedback/{fb.id}/resolve")
        assert db.session.get(Feedback, fb.id).resolved
        assert b"flickers" not in client.get("/admin/feedback").data           # hidden from "open"
        assert b"flickers" in client.get("/admin/feedback?show=all").data

    def test_feedback_too_short(self, as_user):
        as_user("bob").post("/feedback", data={"kind": "bug", "message": "bad"})
        assert Feedback.query.count() == 0

    def test_home_page_and_404_and_health(self, client, idea):
        assert b"Solar roof" in client.get("/").data
        r = client.get("/nope")
        assert r.status_code == 404 and b"Page not found" in r.data
        assert client.get("/healthz").get_json() == {"status": "ok"}

    def test_security_headers(self, client):
        h = client.get("/").headers
        assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"

    def test_profile_email_update_and_conflict(self, as_user, users):
        c = as_user("alice")
        c.post("/profile", data={"p-email": "bob@example.com", "p-submit": "1"})
        assert users["alice"].email == "alice@example.com"
        c.post("/profile", data={"p-email": "alice2@example.com", "p-submit": "1"})
        db.session.refresh(users["alice"])
        assert users["alice"].email == "alice2@example.com"


class TestCSRF:
    def test_csrf_enforced_when_enabled(self):
        class Strict(TestConfig):
            WTF_CSRF_ENABLED = True
        app = create_app(Strict)
        with app.app_context():
            c = app.test_client()
            r = c.post("/login", data={"identifier": "x", "password": "y"})
            assert r.status_code == 400 and b"expired" in r.data
            db.session.remove(); db.drop_all()
