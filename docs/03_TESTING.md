# Step 4 – Testing

## 1. Functional testing (automated)

`pytest -v` runs **84 tests** against an in-memory SQLite database. Result of the last run: **84 passed**. A GitHub Actions workflow runs them on every push.

| Area | Test class | What is verified |
|---|---|---|
| Authentication | `TestAuth` | registration, password hashing, weak/mismatched passwords, duplicate user/e-mail (case-insensitive), login by username or e-mail, wrong password, disabled account, open-redirect blocking, protected pages redirect, password change |
| Ideas & categories | `TestIdeas` | default categories, submission, dynamic category creation (de-duplicated), validation, anonymous read-only access, XSS escaping, owner edit/delete rules, admin delete + cascade, "My ideas", search / filter / sort / pagination, wildcard escaping |
| Voting | `TestVoting` | upvote, switch, withdraw, one vote per user, totals, no self-vote, anonymous 401, invalid values, unknown idea, non-AJAX fallback |
| Comments | `TestComments` | post, threaded reply, reply to a foreign idea's comment rejected, empty/overlong rejected, delete permissions, soft-delete keeps thread, admin moderation, HTML escaping |
| Roles | `TestRoles` | reviewer evaluates, submitter forbidden, anonymous redirected, no self-review, invalid status rejected, review form visibility |
| Administration | `TestAdmin` | admin-only access (302 / 403 / 200), role change, self-protection, last-admin protection, enable/disable, disabled user's live session invalidated, category CRUD and protection, dashboard |
| v2 regressions | `TestBugFixes` | wildcard username/e-mail clash, admin search escaping, no deprecation warnings, no hard-coded secret |
| Brute force | `TestLoginThrottle` | lock-out after 5 failures, reset on success, per-account scope |
| Hardening | `TestSecurityHeaders` | CSP, no inline/external scripts, offline assets served, HSTS only on HTTPS |
| Review queue | `TestReviewQueue` | access, ordering, quick actions, note preserved, safe redirect, badge |
| Profiles & ranking | `TestPublicProfile`, `TestLeaderboardAndTrending` | stats, 404, trending vs top |
| Export & misc | `TestExportAndMisc` | CSV access + formula neutralising, related ideas, status filter, idempotent bootstrap |
| Feedback & misc | `TestFeedbackAndMisc`, `TestCSRF` | feedback round trip, validation, 404 page, health check, security headers, profile e-mail rules, CSRF enforced |

Manual smoke test on a running server (CSRF enabled): register → login → AJAX vote (+1) → vote again (withdraw) →
request without token (400) → comment → `/admin/` as submitter (403). All behaved as specified.

Browser verification (headless Chromium): light/dark theme, desktop and 390 px mobile layouts, AJAX voting, theme persistence, **zero console errors / CSP violations / failed requests**, no horizontal overflow on mobile.

## 2. Manual test checklist (browser)

| # | Steps | Expected |
|---|---|---|
| 1 | Open `/` while signed out | Landing page, stats, top ideas |
| 2 | Sign up with a weak password | Inline error, no account |
| 3 | Sign up correctly | Logged in, welcome message |
| 4 | New idea → pick category → submit | Redirected to idea page, status *Pending* |
| 5 | New idea → type a new category | Category appears in filters, only once |
| 6 | Click ▲ on someone else's idea | Score +1 instantly, arrow highlighted |
| 7 | Click ▲ again | Vote withdrawn |
| 8 | Click ▲ on your own idea | Message "can't vote on your own idea" |
| 9 | Comment, then *Reply* to it | Reply nested under parent |
| 10 | Delete a comment that has replies | Shows "[comment removed]", replies stay |
| 11 | Sign in as `reviewer`, evaluate an idea | Status badge + note shown to all |
| 12 | Sign in as `admin`, change a role / disable a user | Applied; disabled user cannot sign in |
| 13 | Resize to phone width | Layout stacks, nothing overflows |
| 14 | Toggle dark mode, reload | Preference persists |

## 3. User testing

Ask 3–5 people to complete these tasks **without help** while you observe (think-aloud):

1. Create an account and submit an idea.
2. Find the most popular idea in a given category and vote for it.
3. Reply to a comment.
4. Report a problem through the feedback form.

Record for each task: success (Y/N), time, confusion points, quotes.

| Tester | T1 | T2 | T3 | T4 | Comments |
|---|---|---|---|---|---|
| | | | | | |

Satisfaction questions (1 = strongly disagree … 5 = strongly agree): *"It was easy to submit an idea"*, *"I understood
how voting works"*, *"I would use this platform regularly"*. Feed the findings into the platform's own Feedback inbox
(admin → Feedback) to close the loop.
