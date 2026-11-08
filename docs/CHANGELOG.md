# Changelog

## v2.0 – Polish, security and UX overhaul

### Bugs fixed
| # | Problem | Fix |
|---|---|---|
| 1 | Registration said a username/e-mail was "taken" when it only *looked like* another (`a_ice` vs `alice`, `%@…`) because `ILIKE` treats `_` and `%` as wildcards | Exact case-insensitive comparison (`lower(x) = lower(y)`) |
| 2 | Admin user search interpreted `%` / `_` as wildcards | Wildcards are escaped |
| 3 | Hard-coded fallback `SECRET_KEY` (`dev-only-change-me`) – a real vulnerability if deployed without configuration | Random key generated once and stored in `instance/.secret_key` |
| 4 | Several gunicorn workers could crash on first start racing to create tables/categories | Idempotent, race-tolerant bootstrap |
| 5 | WTForms 3.3 deprecation warnings (`SelectField` tuples) | `SelectChoice` objects |
| 6 | Seed data showed "edited just now" on every idea | `updated_at` initialised to `created_at` |
| 7 | Vote buttons were clickable on your own idea and only failed after the click | Disabled with an explanatory tooltip |
| 8 | CSV export (new) could execute spreadsheet formulas | Leading `= + - @` neutralised |
| 9 | CDN dependency: UI broke offline, and a strict CSP was impossible | All assets vendored locally |
| 10 | Dashboard used an inline script | JSON data block + external script (CSP-compatible) |

### Security
Login throttling · Content-Security-Policy · Permissions-Policy · HSTS on HTTPS · `Cache-Control` on dynamic pages · secure remember-me cookie · optional `ProxyFix` · DB connection `pool_pre_ping`.

### New features
Review queue with quick actions · trending sort · status tabs · public profiles · top-contributors leaderboard · related ideas · community-sentiment bar · status stepper · copy-link · CSV export · About page · pending badge for reviewers · OS-aware dark mode.

### UI
New design system (tokens, light/dark palettes, Inter font, colour-coded categories & statuses, avatars), hero section, toast notifications, loading buttons, split-layout auth pages, cards with status accent, responsive tweaks, print styles, reduced-motion support, skip link & focus rings.

### Quality
Tests 54 → 84 · CI workflow · screenshots · expanded README and docs.
