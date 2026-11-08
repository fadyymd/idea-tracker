# 💡 Innovation Idea Tracker

> A full-featured web platform to **submit, discuss, vote on and evaluate innovative ideas** — from first proposal to implementation.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask)
![Tests](https://img.shields.io/badge/tests-84%20passing-16a34a)
![UI](https://img.shields.io/badge/UI-Bootstrap%205%20%C2%B7%20dark%20mode-7952B3?logo=bootstrap&logoColor=white)
![DB](https://img.shields.io/badge/DB-SQLite%20%7C%20PostgreSQL-336791)

🌐 **Live demo:** https://idea-tracker-nf9p.onrender.com · 💻 **Source:** https://github.com/fadyymd/idea-tracker

Built for **Innovation Management – Mini Project 1** (Flask · SQLite/PostgreSQL · HTML/CSS/JavaScript).

<p align="center">
  <img src="docs/screenshots/home.png" alt="Home page" width="85%">
</p>

| Idea list | Idea detail (dark mode) |
|---|---|
| <img src="docs/screenshots/ideas.png" alt="Idea list"> | <img src="docs/screenshots/idea-detail-dark.png" alt="Idea detail in dark mode"> |

| Admin dashboard | Review queue | Mobile |
|---|---|---|
| <img src="docs/screenshots/admin-dashboard-dark.png" alt="Admin dashboard"> | <img src="docs/screenshots/review-queue-dark.png" alt="Review queue"> | <img src="docs/screenshots/mobile.png" alt="Mobile layout" width="200"> |

---

## Table of contents

1. [Features](#features) · 2. [Quick start](#quick-start) · 3. [Demo accounts](#demo-accounts) · 4. [Configuration](#configuration)
5. [Project structure](#project-structure) · 6. [Data model](#data-model) · 7. [Roles & permissions](#roles--permissions)
8. [Security](#security) · 9. [Testing](#testing) · 10. [Deployment](#deployment) · 11. [Documentation](#documentation)
12. [Assignment mapping](#assignment-mapping) · 13. [Troubleshooting](#troubleshooting) · 14. [Roadmap](#roadmap)

## Features

**Ideas & discovery**
- Submit, edit and delete ideas (title, description, category); owners can edit while the idea is *Pending*
- Predefined categories **and** dynamic creation by users (case-insensitive, de-duplicated)
- Full-text-style search, category and status filters, sorting by *Newest · Trending (7 days) · Top voted · Most discussed · Oldest*, pagination
- Live status stepper (Submitted → Under review → Approved/Rejected → Implemented), related ideas, copy-link button
- Public member profiles (`/u/<name>`) with contribution stats, and a **Top contributors** leaderboard

**Voting & discussion**
- Up/down voting, **one vote per user per idea** (enforced by a DB constraint), click again to withdraw, no self-voting
- Instant AJAX updates with graceful non-JavaScript fallback; community-sentiment bar
- Threaded comments (unlimited depth), delete own comment, admin moderation, soft-delete keeps threads intact

**Roles & administration**
- Three roles: **submitter**, **reviewer**, **administrator** — enforced server-side
- **Review queue** for reviewers with one-click *Start review / Approve / Reject* and a pending-count badge
- Admin dashboard (charts), user management (roles, enable/disable), category management, **CSV export** of all ideas
- Feedback loop: users report issues or suggest improvements; admins triage them in an inbox

**Experience**
- Modern, responsive UI (Bootstrap 5 + custom design system), **light & dark theme** (follows the OS, remembers your choice)
- Toast notifications, loading states on forms, accessible markup (skip link, ARIA, focus rings, reduced-motion support), print styles
- **Works fully offline** — Bootstrap, icons, Chart.js and the Inter font are vendored locally (no CDN calls)

## Quick start

Requires **Python 3.10+**.

```bash
git clone <your-repo-url> idea_tracker && cd idea_tracker

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python seed.py                       # optional: demo users + sample ideas
python run.py                        # → http://127.0.0.1:5000
```

No seed data? Create your own administrator:

```bash
flask --app run.py create-admin
```

### Docker (app + PostgreSQL)

```bash
docker compose up --build            # → http://localhost:8000
docker compose exec web flask --app run.py create-admin
```

## Demo accounts

After `python seed.py` (password for all: **`Demo1234`**):

| Username | Role | Try this |
|---|---|---|
| `admin` | administrator | Dashboard, users, categories, CSV export |
| `reviewer` | reviewer | Review queue, evaluate ideas |
| `alice`, `bob`, `carol`, `dave` | submitter | Submit, vote, comment |

> ⚠️ Demo passwords are for local use only. Never seed demo data in production.

## Configuration

All settings are environment variables (see [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | auto-generated & stored in `instance/.secret_key` | Session/CSRF signing. **Set explicitly in production.** |
| `DATABASE_URL` | SQLite file in `instance/` | e.g. `postgresql://user:pass@host/db` (`postgres://` is auto-fixed) |
| `SESSION_COOKIE_SECURE` | `0` | Set `1` when served over HTTPS (also enables secure remember-me cookie) |
| `TRUST_PROXY` | `0` | Set `1` behind Render/Heroku/nginx so client IPs and HTTPS are detected |
| `HOST`, `PORT`, `FLASK_DEBUG` | `127.0.0.1`, `5000`, `0` | Dev server only |

## Project structure

```
idea_tracker/
├── run.py                    entry point (python run.py · gunicorn run:app)
├── config.py                 environment-driven configuration
├── seed.py                   demo data
├── app/
│   ├── __init__.py           application factory, error handlers, CLI
│   ├── models.py             User · Category · Idea · Vote · Comment · Feedback
│   ├── forms.py              Flask-WTF forms & validation
│   ├── security.py           CSP/headers, login throttling
│   ├── utils.py              RBAC decorators, safe redirects, comment tree
│   ├── blueprints/           main · auth · ideas · admin
│   ├── templates/            Jinja2 (macros, pages, admin)
│   └── static/               css/ (design system) · js/ · vendor/ (offline assets)
├── tests/                    84 pytest tests
├── docs/                     requirements · data model · testing · deployment · guides · screenshots
├── Procfile · Dockerfile · docker-compose.yml · .github/workflows/ci.yml
```

## Data model

`users` ─┬─< `ideas` >─ `categories` · `ideas` ─┬─< `votes` (unique per user+idea) · `ideas` ─< `comments` (self-referencing for replies) · `users` ─< `feedback`

Vote totals and comment counts are **computed** (never stored) so they cannot drift. Full ER diagram: [docs/02_DATA_MODEL.md](docs/02_DATA_MODEL.md).

## Roles & permissions

| Action | Visitor | Submitter | Reviewer | Admin |
|---|:--:|:--:|:--:|:--:|
| Browse ideas, profiles | ✅ | ✅ | ✅ | ✅ |
| Submit / vote / comment | – | ✅ | ✅ | ✅ |
| Edit/delete own idea (while pending) | – | ✅ | ✅ | ✅ |
| Evaluate ideas (not own) | – | – | ✅ | ✅ |
| Review queue | – | – | ✅ | ✅ |
| Delete any idea/comment | – | – | – | ✅ |
| Manage users & categories, feedback, CSV export | – | – | – | ✅ |

Business rules: no self-voting · reviewers can't evaluate their own ideas · the last active admin can't be disabled · admins can't demote or disable themselves · categories with ideas can't be deleted.

## Security

| Threat | Protection |
|---|---|
| Password theft | Salted **scrypt** hashes (Werkzeug default); strength rules |
| Brute force | Login throttling (5 failures / 15 min per IP + account) |
| CSRF | Global token check, including AJAX (`X-CSRFToken`) |
| XSS | Auto-escaping everywhere + strict **Content-Security-Policy** (`script-src 'self'`, no inline scripts) |
| SQL injection | ORM only; `LIKE` wildcards escaped |
| Broken access control | Role decorator **and** object-level checks |
| Open redirect, clickjacking, MIME sniffing | Same-host `next`, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, HSTS on HTTPS |
| CSV formula injection | Cells starting with `= + - @` are neutralised in exports |
| Weak default secret | Random key generated on first run (no hard-coded secret) |

## Testing

```bash
pip install -r requirements-dev.txt
pytest -v                    # 84 tests, ~30 s
```

Covers authentication, RBAC, ideas/categories, voting, comments, reviews, admin tools, CSV export, throttling, CSP, offline assets and regression tests for fixed bugs. CI runs on every push ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). Manual checklist and user-testing script: [docs/03_TESTING.md](docs/03_TESTING.md).

## Deployment

Standard WSGI app (`gunicorn run:app`). Step-by-step guides for **Render, Heroku, PythonAnywhere, Docker and AWS** are in [docs/04_DEPLOYMENT.md](docs/04_DEPLOYMENT.md).

Production checklist: strong `SECRET_KEY` · PostgreSQL · HTTPS + `SESSION_COOKIE_SECURE=1` · `TRUST_PROXY=1` behind a proxy · no demo accounts · backups.

## Documentation

| Document | Content |
|---|---|
| [docs/01_REQUIREMENTS.md](docs/01_REQUIREMENTS.md) | Users, interview guide, functional & non-functional requirements, business rules |
| [docs/02_DATA_MODEL.md](docs/02_DATA_MODEL.md) | ER diagram, schema, integrity rules |
| [docs/03_TESTING.md](docs/03_TESTING.md) | Automated test matrix, manual checklist, user testing |
| [docs/04_DEPLOYMENT.md](docs/04_DEPLOYMENT.md) | Hosting guides and checklist |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | End-user guide |
| [docs/TECHNICAL.md](docs/TECHNICAL.md) | Architecture, routes, security, extension points |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | What changed in v2 |

## Assignment mapping

| Step | Where |
|---|---|
| 1. Define requirements | `docs/01_REQUIREMENTS.md` |
| 2. Data model | `app/models.py`, `docs/02_DATA_MODEL.md` |
| 3. Develop the application | `app/` |
| 4. Testing | `tests/`, `docs/03_TESTING.md` |
| 5. Deployment | `Procfile`, `Dockerfile`, `docs/04_DEPLOYMENT.md` |
| 6. Documentation | this README + `docs/` |
| Final touches | design system in `static/css/style.css`, feedback form + admin inbox |

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Activate the virtualenv and run `pip install -r requirements.txt` |
| "Your form session expired" | Reload the page; forms expire after 8 h |
| Sessions reset on every restart in production | Set a fixed `SECRET_KEY` (a read-only disk cannot store the generated one) |
| `Too many failed attempts` | Wait 15 minutes (or restart the app in development) |
| Login throttle seems weaker with many workers | Counters are per process; use Redis + Flask-Limiter for a shared limit |
| Database schema changed after update | There are no migrations yet — re-seed in development or add Flask-Migrate |
| Want to start over | Delete `instance/idea_tracker.db` and run `python seed.py` |

## Roadmap

E-mail verification & password reset · Flask-Migrate (Alembic) · notifications (e-mail / in-app) · attachments on ideas · REST API · i18n (Arabic / French, RTL).

---

<sub>Idea Tracker is an educational project. Inter font © The Inter Project Authors (SIL OFL). Bootstrap, Bootstrap Icons and Chart.js are MIT-licensed.</sub>
