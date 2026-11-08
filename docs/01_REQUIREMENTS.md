# Step 1 – Requirements

## 1. Target audience

The platform is designed for **organizations and communities** (employees of a company, members of a university
club, a student cohort) that want a structured way to collect and evaluate improvement ideas.

| Persona | Goal | Pain point today |
|---|---|---|
| **Sara – employee / student (Submitter)** | Share an idea and see if others like it | Ideas get lost in e-mail threads and meetings; no feedback |
| **Karim – team lead (Reviewer)** | Quickly see the most promising ideas and record a decision | No overview; decisions are not documented |
| **Nadia – innovation manager (Administrator)** | Keep the platform tidy and measure participation | No statistics, no way to manage categories or users |

## 2. Gathering requirements – interview / survey guide

Suggested questions (5–10 respondents are enough for a mini-project; record answers in the table at the end).

1. How do you currently share improvement ideas? What works and what does not?
2. Have you ever had an idea that was never heard? Why?
3. What information must an idea contain for you to judge it? (title, description, expected benefit, cost…)
4. Which categories matter most in your organization?
5. Would you rather *upvote/downvote* or give *star ratings*? (We implemented up/down – simpler and unambiguous.)
6. Do you want to discuss ideas in comments? Is a threaded view important?
7. Who should decide which idea is realised? Should that decision be visible to everyone?
8. Would you use the platform on a phone?
9. What would make you stop using it?

| # | Respondent | Key findings |
|---|---|---|
| 1 | | |
| 2 | | |

> The design decisions below already reflect the typical answers to these questions; update them with your own survey results.

## 3. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Visitors can register with username, e-mail and password | Must |
| FR-2 | Registered users can sign in/out; passwords are stored hashed | Must |
| FR-3 | Roles: submitter, reviewer, administrator with different permissions | Must |
| FR-4 | Signed-in users submit ideas (title, description, category) | Must |
| FR-5 | Categories are predefined and users can create new ones | Must |
| FR-6 | Everyone can browse, search, filter and sort ideas | Must |
| FR-7 | Signed-in users upvote/downvote an idea once; vote counts are displayed | Must |
| FR-8 | Signed-in users comment on ideas and reply to comments (threads) | Must |
| FR-9 | Reviewers set an idea's status and leave a visible note | Should |
| FR-10 | Admins manage users (role, enable/disable) and categories | Should |
| FR-11 | Users can edit/delete their idea while it is still pending | Should |
| FR-12 | Users can send feedback about the platform; admins triage it | Should |
| FR-13 | Admin dashboard with key statistics | Could |

## 4. Non-functional requirements

| ID | Requirement | How it is met |
|---|---|---|
| NFR-1 Security | Passwords hashed, CSRF/XSS/SQL-injection protection, RBAC on the server | scrypt hashes, CSRFProtect, Jinja auto-escape, SQLAlchemy ORM, decorators |
| NFR-2 Usability | Usable on phones and desktops | Bootstrap 5 responsive layout, dark mode |
| NFR-3 Performance | List pages stay fast with many ideas | Pagination, indexed columns, single-query vote lookup, scalar sub-queries for counts |
| NFR-4 Portability | Runs locally with SQLite, in production with PostgreSQL | `DATABASE_URL` switch |
| NFR-5 Maintainability | Clear structure, tests, docs | Blueprints, application factory, 54 automated tests |
| NFR-6 Accessibility | Labels, ARIA attributes, keyboard-usable controls | Semantic HTML, `aria-*` on buttons/alerts |

## 5. Business rules

* A user may vote **once** per idea; clicking the same arrow again withdraws the vote; changing arrows switches it.
* Users **cannot vote on their own idea** (prevents self-promotion).
* The owner can edit/delete an idea only while its status is **Pending** (keeps evaluations trustworthy); admins always can.
* Reviewers **cannot evaluate their own ideas** (conflict of interest).
* A category can only be deleted when no idea uses it.
* The last active administrator cannot be disabled; admins cannot demote or disable themselves.
* Deleting a comment that has replies blanks it ("[comment removed]") instead of destroying the discussion.

## 6. User stories (excerpt)

* *As a submitter I want to post an idea with a category so that others can find it.*
* *As a member I want to upvote ideas so that the best ones become visible.*
* *As a reviewer I want to mark an idea "Approved" with a note so that everybody knows the decision.*
* *As an administrator I want to promote a user to reviewer so that evaluation work can be shared.*
