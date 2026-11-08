# Step 5 – Deployment

The app is a standard WSGI application (`run:app`) and is configured purely through environment variables.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | **Required in production.** `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | PostgreSQL URL. If unset, SQLite is used (`instance/idea_tracker.db`). `postgres://` is auto-corrected. |
| `SESSION_COOKIE_SECURE` | Set to `1` when served over HTTPS |
| `TRUST_PROXY` | Set to `1` behind Render/Heroku/nginx (correct client IP for login throttling, HTTPS detection) |

After the first deploy create an administrator: `flask --app run.py create-admin`
(or `python seed.py` to load demo data – **do not** use demo passwords in production).

## Option A – Render (free tier, recommended)

1. Push the project to GitHub.
2. Render → **New → PostgreSQL** (copy the *Internal Database URL*).
3. Render → **New → Web Service** → pick the repo.
   * Build command: `pip install -r requirements.txt`
   * Start command: `gunicorn run:app`
   * Environment: `SECRET_KEY`, `DATABASE_URL`, `SESSION_COOKIE_SECURE=1`, `TRUST_PROXY=1`
4. Open the *Shell* tab → `flask --app run.py create-admin`.
5. Health check path: `/healthz`.

## Option B – Heroku

```bash
heroku create my-idea-tracker
heroku addons:create heroku-postgresql:essential-0
heroku config:set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") SESSION_COOKIE_SECURE=1 TRUST_PROXY=1
git push heroku main                   # uses the Procfile
heroku run flask --app run.py create-admin
```

## Option C – PythonAnywhere (free, SQLite is fine)

1. Upload the project, create a virtualenv, `pip install -r requirements.txt`.
2. *Web* tab → new Flask app → WSGI file: `from run import app as application`.
3. Set `SECRET_KEY` in the WSGI file via `os.environ`.
4. Reload the web app.

## Option D – Docker

```bash
docker compose up --build            # app on http://localhost:8000 with PostgreSQL
docker compose exec web flask --app run.py create-admin
```

## AWS (as mentioned in the assignment)

Any of the above runs on AWS: Elastic Beanstalk (Python platform, uses the `Procfile`), or ECS/App Runner with the
supplied `Dockerfile` and RDS PostgreSQL for the database.

## Production checklist

- [ ] Strong random `SECRET_KEY`
- [ ] PostgreSQL instead of SQLite
- [ ] HTTPS and `SESSION_COOKIE_SECURE=1`
- [ ] Demo accounts not present / passwords changed
- [ ] Regular database backups
- [ ] `FLASK_DEBUG` unset (never run the debugger in production)
