import pytest

from app import create_app
from app.extensions import db
from app.models import ROLE_ADMIN, ROLE_REVIEWER, ROLE_SUBMITTER, Category, Idea, User
from app.security import login_throttle
from config import TestConfig


@pytest.fixture(autouse=True)
def _reset_throttle():
    login_throttle.clear_all()
    yield
    login_throttle.clear_all()


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(username, role=ROLE_SUBMITTER, password="Passw0rd!x", active=True):
    user = User(username=username, email=f"{username}@example.com", role=role, is_active_account=active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def users(app):
    return {
        "alice": make_user("alice"),
        "bob": make_user("bob"),
        "rita": make_user("rita", ROLE_REVIEWER),
        "root": make_user("root", ROLE_ADMIN),
    }


@pytest.fixture()
def idea(app, users):
    cat = Category.query.first()
    idea = Idea(title="Solar roof for HQ", description="Install solar panels on the headquarters roof.",
                category_id=cat.id, submitter_id=users["alice"].id)
    db.session.add(idea)
    db.session.commit()
    return idea


def login(client, username, password="Passw0rd!x", **kw):
    return client.post("/login", data={"identifier": username, "password": password}, **kw)


@pytest.fixture()
def as_user(client, users):
    def _login(name):
        client.post("/logout")  # switch user cleanly if someone is already signed in
        login(client, name)
        return client
    return _login
