"""Populate the database with demo accounts and realistic sample data.

    python seed.py            # add demo data (idempotent)
    python seed.py --reset    # wipe everything first

Demo accounts (password for all: Demo1234):
    admin / reviewer / alice / bob / carol / dave
"""
import random
import sys
from datetime import timedelta

from app import create_app, ensure_default_categories
from app.extensions import db
from app.models import (
    ROLE_ADMIN, ROLE_REVIEWER, ROLE_SUBMITTER,
    Category, Comment, Idea, User, Vote, utcnow,
)

PASSWORD = "Demo1234"

USERS = [
    ("admin", ROLE_ADMIN), ("reviewer", ROLE_REVIEWER),
    ("alice", ROLE_SUBMITTER), ("bob", ROLE_SUBMITTER),
    ("carol", ROLE_SUBMITTER), ("dave", ROLE_SUBMITTER),
]

IDEAS = [
    ("Mobile app for timesheets", "Technology", "alice",
     "Replace paper timesheets with a simple mobile app. Employees clock in and out with one tap, managers approve "
     "hours in bulk and payroll receives clean data without manual re-typing.", "approved",
     "Strong business case and low implementation cost. Approved for a 3-month pilot."),
    ("Paperless onboarding checklist", "Process Improvement", "bob",
     "New hires currently sign around 12 paper forms. A single digital checklist with e-signatures would cut onboarding "
     "time from two days to a few hours and avoid lost documents.", "under_review", ""),
    ("Customer feedback kiosk at reception", "Customer Experience", "carol",
     "Place a small tablet at reception where visitors rate their experience with three smiley buttons and an optional "
     "comment. Results feed a weekly dashboard for the service team.", "pending", ""),
    ("Solar panels on the main roof", "Sustainability", "dave",
     "The main building has a large south-facing roof. Installing solar panels could cover roughly a third of our "
     "electricity needs and pay for itself within seven years.", "under_review",
     "Waiting for a structural survey of the roof."),
    ("Monthly lunch-and-learn sessions", "Education & Training", "alice",
     "Every month a team member presents something they learned (a tool, a book, a project) over lunch. It spreads "
     "knowledge across departments and gives people a friendly speaking opportunity.", "implemented",
     "Running since September — attendance averages 25 people."),
    ("Quiet focus rooms", "Workplace Culture", "bob",
     "Convert two unused meeting rooms into bookable quiet rooms with no phones or meetings, so people can do deep "
     "work without interruptions.", "pending", ""),
    ("AI assistant for the internal wiki", "Technology", "carol",
     "Add a search assistant to our internal wiki that answers questions in natural language and links to the source "
     "pages, reducing the time people spend hunting for documentation.", "pending", ""),
    ("Reusable cup deposit scheme", "Sustainability", "dave",
     "Introduce reusable cups at the coffee machines with a small deposit. Estimated saving: 15,000 disposable cups a "
     "year.", "rejected", "Hygiene regulations make a shared-cup return process too costly for now. Please revisit "
     "with a personal-cup discount instead."),
    ("Self-service knowledge base for customers", "Customer Experience", "alice",
     "Publish the top 50 support answers as a public knowledge base with search. Expected to deflect about 20% of "
     "incoming tickets.", "pending", ""),
    ("Weekly 15-minute stand-up across teams", "Process Improvement", "bob",
     "A short cross-team stand-up so blockers are visible early and duplicated work is avoided.", "pending", ""),
    ("Bike-to-work incentive programme", "Sustainability", "carol",
     "Offer secure bike parking, showers and a monthly bonus for staff who cycle. Healthier employees, fewer cars "
     "and less pressure on the parking lot.", "approved", "Great fit with our sustainability goals."),
    ("Shared roadmap visible to everyone", "Process Improvement", "dave",
     "Publish the product roadmap on the intranet so every team knows what is planned and can flag conflicts early.",
     "pending", ""),
    ("Mentorship pairing for new joiners", "Workplace Culture", "alice",
     "Pair each new hire with a mentor from another department for their first three months.", "under_review", ""),
    ("Voice search in the customer app", "Customer Experience", "bob",
     "Let customers search products by voice. Useful for accessibility and while driving or cooking.", "pending", ""),
    ("Automated invoice matching", "Technology", "carol",
     "Match purchase orders and invoices automatically and surface only the exceptions to finance.", "pending", ""),
    ("Four-day workshop on design thinking", "Education & Training", "dave",
     "A hands-on workshop series on design thinking for all product teams, led by internal champions.", "pending", ""),
]

COMMENTS = [
    "Great idea — I would use this every day.",
    "Have we estimated the cost? It would help the review.",
    "We tried something similar in my previous company and it worked well.",
    "Could we start with a small pilot group first?",
    "I'd add accessibility requirements from the start.",
    "Agreed, this solves a real problem for our team.",
]


def run(reset: bool = False) -> None:
    app = create_app()
    with app.app_context():
        if reset:
            db.drop_all()
            db.create_all()
        ensure_default_categories()

        if User.query.filter_by(username="admin").first():
            print("Demo data already present (use --reset to rebuild).")
            return

        rng = random.Random(42)
        users = {}
        for name, role in USERS:
            u = User(username=name, email=f"{name}@example.com", role=role)
            u.set_password(PASSWORD)
            db.session.add(u)
            users[name] = u
        db.session.commit()

        cats = {c.name: c for c in Category.query.all()}
        now = utcnow()
        ideas = []
        for i, (title, cat, author, desc, status, note) in enumerate(IDEAS):
            idea = Idea(
                title=title, description=desc, category_id=cats[cat].id,
                submitter_id=users[author].id, status=status, review_note=note,
                created_at=now - timedelta(days=len(IDEAS) - i, hours=rng.randint(0, 8)),
            )
            idea.updated_at = idea.created_at  # seeded ideas were never edited
            if status != "pending":
                idea.reviewed_by_id = users["reviewer"].id
                idea.reviewed_at = idea.created_at + timedelta(days=1)
            db.session.add(idea)
            ideas.append(idea)
        db.session.commit()

        voters = [u for u in users.values()]
        for idea in ideas:
            for voter in voters:
                if voter.id == idea.submitter_id or rng.random() < 0.25:
                    continue
                db.session.add(Vote(idea_id=idea.id, user_id=voter.id,
                                    vote_type=1 if rng.random() < 0.8 else -1))
        db.session.commit()

        for idea in ideas[:6]:
            roots = []
            for _ in range(rng.randint(1, 3)):
                author = rng.choice([u for u in voters if u.id != idea.submitter_id])
                c = Comment(idea_id=idea.id, user_id=author.id, content=rng.choice(COMMENTS),
                            created_at=idea.created_at + timedelta(hours=rng.randint(2, 40)))
                db.session.add(c)
                roots.append(c)
            db.session.commit()
            parent = roots[0]
            reply = Comment(idea_id=idea.id, user_id=idea.submitter_id, parent_id=parent.id,
                            content="Thanks for the feedback! I'll add more detail to the description.",
                            created_at=parent.created_at + timedelta(hours=3))
            db.session.add(reply)
            db.session.commit()
            db.session.add(Comment(idea_id=idea.id, user_id=parent.user_id, parent_id=reply.id,
                                   content="Sounds good — looking forward to it.",
                                   created_at=reply.created_at + timedelta(hours=2)))
            db.session.commit()

        print(f"Seeded {len(users)} users, {len(ideas)} ideas. Sign in as 'admin' / '{PASSWORD}'.")


if __name__ == "__main__":
    run(reset="--reset" in sys.argv)
