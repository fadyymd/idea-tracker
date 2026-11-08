# Technical Documentation

## Stack

Python 3.10+ · Flask 3 · Flask-SQLAlchemy 3 (SQLAlchemy 2) · Flask-Login · Flask-WTF (CSRF + forms) · Jinja2 ·
SQLite (dev) / PostgreSQL (prod) · Bootstrap 5.3 + Bootstrap Icons + Chart.js + Inter font (all vendored in `static/vendor`, no CDN) · vanilla JavaScript · pytest · gunicorn.

## Architecture

```
Browser ──HTTP──▶ gunicorn ──▶ Flask app (application factory: create_app)
                                 ├─ Blueprints:  main · auth · ideas · admin
                                 ├─ Forms (WTForms) → validation + CSRF
                                 ├─ Models (SQLAlchemy ORM) ──▶ SQLite / PostgreSQL
                                 └─ Templates (Jinja2) + static (CSS/JS)
```

* **Application factory** (`app/__init__.py`) – builds the app, registers extensions, blueprints, error handlers,
  security headers, CLI commands. Tests build a separate app with `TestConfig`.
* **Blueprints** keep responsibilities separate: `auth` (accounts), `ideas` (ideas, votes, comments, review),
  `admin` (back office), `main` (home, feedback, health check).
* **Computed columns** – `Idea.score` and `Idea.comment_count` are correlated scalar sub-queries mapped with
  `column_property`, so they can be used in `ORDER BY` for "Top voted"/"Most discussed" without N+1 queries.
* **Comment threads** – flat query → `build_comment_tree()` builds a forest in O(n); rendered with a recursive Jinja macro.
* **Trending** – `_trending_order()` ranks by votes + comments of the last 7 days, then all-time score.
* **Frontend** – `static/css/style.css` is a token-based design system (light/dark via CSS variables); `static/js/app.js` handles theme, toasts, AJAX voting, replies and charts. No inline scripts (CSP).
* **Voting** – `POST /ideas/<id>/vote`; with header `X-Requested-With: fetch` returns JSON, otherwise redirects
  (works without JavaScript). A DB unique constraint + `IntegrityError` handling makes double-clicks safe.

## Routes

| Method & path | Access | Purpose |
|---|---|---|
| `GET /` | public | landing page, stats |
| `GET/POST /register`, `/login`; `POST /logout` | public / auth | accounts |
| `GET/POST /profile` | user | e-mail, password |
| `GET /ideas` | public | list with `q`, `category`, `status`, `sort` (new/trending/top/discussed/old), `page` |
| `GET /u/<username>` | public | member profile |
| `GET /review` | reviewer / admin | review queue (`show=pending/under_review/open`) |
| `GET /about` | public | about page |
| `GET /my-ideas` | user | own ideas |
| `GET/POST /ideas/new` | user | submit |
| `GET /ideas/<id>` | public | detail + comments |
| `GET/POST /ideas/<id>/edit`, `POST /ideas/<id>/delete` | owner (pending) / admin | modify |
| `POST /ideas/<id>/vote` | user | vote / toggle |
| `POST /ideas/<id>/comments` | user | comment / reply (`parent_id`) |
| `POST /comments/<id>/delete` | author / admin | remove |
| `POST /ideas/<id>/review` | reviewer / admin | status + note |
| `GET/POST /feedback` | user | send feedback |
| `GET /admin/`, `/admin/users`, `/admin/categories`, `/admin/feedback` (+ POST actions) | admin | back office |
| `GET /admin/export/ideas.csv` | admin | CSV export |
| `GET /healthz` | public | liveness probe |

## Security measures

| Threat | Countermeasure |
|---|---|
| Password theft | scrypt salted hashes (`werkzeug.security`, memory-hard), never logged or displayed |
| CSRF | `CSRFProtect` globally; forms carry a token, AJAX sends `X-CSRFToken` from a meta tag |
| XSS | Jinja auto-escaping everywhere, user text never marked `|safe`; `X-Content-Type-Options: nosniff` |
| SQL injection | ORM / bound parameters only; `LIKE` wildcards in search are escaped |
| Broken access control | `roles_required` decorator + object-level checks (owner, status, self-review, self-vote) |
| Open redirect | `next` accepted only if it stays on the same host |
| Clickjacking | `X-Frame-Options: DENY` |
| Brute force | `LoginThrottle` (sliding window, per IP+account, 5 failures / 15 min) → HTTP 429 |
| Script injection (defence in depth) | CSP `script-src 'self'`: no inline scripts, no third-party hosts |
| CSV formula injection | `_csv_safe()` prefixes cells beginning with `= + - @` |
| Session safety | `HttpOnly`, `SameSite=Lax`, optional `Secure` cookies; disabled users are rejected on the next request |
| Privilege loss | Cannot demote/disable yourself or the last active administrator |

Known limitations (reasonable next steps): login throttle is per process (use Redis + Flask-Limiter for several workers), no e-mail verification / password reset, no schema migrations (add Flask-Migrate/Alembic before changing the schema in production).

## Developer setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python seed.py --reset         # demo data
FLASK_DEBUG=1 python run.py    # auto-reload on http://127.0.0.1:5000
pytest -v
```

CLI: `flask --app run.py init-db`, `flask --app run.py create-admin`.

## Extending

* **Star ratings instead of up/down** – change `Vote.vote_type` range (e.g. 1–5), replace the `CheckConstraint`,
  and score with `avg()` instead of `sum()` in `Idea.score`.
* **New status** – add it to `STATUSES`, `STATUS_LABELS`, `STATUS_COLORS` in `models.py`.
* **E-mail notifications** – hook into `add_comment` and `review` views.
