# Accessibility Audit Platform — Phase 1

Phase 1 delivers the foundation the rest of the platform builds on:

- JWT-based auth (signup, login, silent refresh, logout)
- Projects (one project = one site/app you want to audit)
- An async site crawler that discovers unique pages (deduplicated by
  normalized path, ignoring query strings/fragments) so later phases know
  what pages exist before running any WCAG checks

WCAG scanning itself, defect reports, teams/roles, and billing are **out of
scope for Phase 1** — see the top-level project brief for what's deferred to
Phase 2.

## Tech stack

| Layer     | Technology |
|-----------|------------|
| Backend   | FastAPI (strict MVC), SQLAlchemy ORM, Alembic migrations |
| Database  | PostgreSQL |
| Frontend  | React (Vite) + MUI |
| Auth      | JWT access tokens + opaque, revocable refresh tokens; bcrypt via passlib |
| Crawler   | httpx (async) + BeautifulSoup4 |

## Project layout

```
backend/
  app/
    main.py            FastAPI app, CORS, router registration, error handlers
    config.py           Settings (pydantic-settings, reads .env)
    database.py         SQLAlchemy engine/session/Base
    models/              ORM tables only (user, refresh_token, project, crawled_page)
    schemas/             Pydantic request/response DTOs
    controllers/         Business logic (no HTTP, no raw queries)
    views/               FastAPI routers = HTTP layer
    services/            Crawler engine, security/token primitives
    repositories/         The only layer that touches the DB session
    middleware/           JWT auth dependency
    utils/                URL normalization/dedup helpers
  alembic/               Migrations
  tests/                 pytest suite
frontend/
  src/
    api/                 axios client + endpoint wrappers, silent token refresh
    context/             AuthContext (in-memory access token)
    components/           ProtectedRoute, AppHeader
    pages/                Login, Signup, Dashboard, Project (crawl + DataGrid)
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 13+ running locally (or reachable over the network)

## 1. Create the PostgreSQL database

Using `psql` (adjust user/password/db name as you like — just keep them in
sync with `backend/.env` in the next step). **Pick a database name that
isn't already in use by another project** — the migration below creates
tables named `users`, `projects`, and `refresh_tokens`, which will collide
with an existing database that happens to have tables of the same name.

```sql
CREATE DATABASE a11y;
```

(If you're reusing an existing Postgres user/role instead of creating one,
that's fine too — just make sure `POSTGRES_USER`/`POSTGRES_PASSWORD` in
`.env` match a role that can create tables in that database.)

## 2. Backend setup

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# edit .env: set POSTGRES_SERVER / POSTGRES_USER / POSTGRES_PASSWORD /
# POSTGRES_DB / POSTGRES_PORT to match the DB you created above (these are
# assembled into the SQLAlchemy connection string by app/config.py), and set
# a real random JWT_SECRET_KEY (e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`)
```

Run migrations (creates `users`, `refresh_tokens`, `projects`, `crawled_pages`):

```bash
alembic upgrade head
```

Optionally seed a default login (reads `DEFAULT_ADMIN_*` from `.env`; safe to
re-run, skips if the account already exists):

```bash
python -m scripts.seed_admin
```

With the values in `.env.example`, this logs in as:

- Email: `info@winvinaya.com`
- Password: `Testpass@123`

Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now at `http://localhost:8000`. Interactive docs at
`http://localhost:8000/docs`. Health check: `GET /api/health`.

### Running backend tests

```bash
pytest
```

Tests use an isolated in-memory SQLite database and a mocked HTTP layer
(`respx`) for the crawler — no live Postgres or network access is required
to run the suite. Covers: URL normalization/dedup rules, the crawler's
same-domain + skip-link + dedup behavior end-to-end, and the full
signup → login → refresh (with rotation) → logout flow.

## 3. Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
# .env: VITE_API_BASE_URL should point at the backend, default http://localhost:8000
npm run dev
```

The app is now at `http://localhost:3000`.

## 4. Using the app end-to-end

1. Open `http://localhost:3000`, click **Sign up**, create an account.
2. Log in.
3. Click **New project**, give it a name and a base URL (e.g.
   `https://example.com`).
4. On the project page, click **Crawl Site**. The crawl runs in the
   background; the page polls for status and the pages table fills in once
   it completes.

## How auth works

- **Access token**: short-lived JWT (default 20 min), kept only in React
  state/context in the browser — never written to `localStorage` — and sent
  as `Authorization: Bearer <token>`.
- **Refresh token**: a high-entropy opaque string (not a JWT), stored
  server-side only as a SHA-256 hash so it can be revoked. The raw value is
  kept in the browser's `localStorage` so a page reload can silently
  re-establish a session; each use rotates it (the old one is revoked and a
  new one issued) to limit the blast radius of a leaked token.
- `POST /api/auth/refresh` exchanges a valid, non-revoked, non-expired
  refresh token for a new access + refresh token pair. The frontend's axios
  client automatically retries any request that gets a 401 by refreshing
  once and replaying it.
- `POST /api/auth/logout` revokes the refresh token server-side.

## Crawler rules implemented

- Same domain/subdomain as the project's base URL only; external links are
  skipped.
- Every `<a href>` is resolved to an absolute URL, then normalized:
  query string and fragment stripped, hostname lowercased, default ports
  dropped, trailing slash collapsed (`/about` and `/about/` are the same
  page). `/products?id=1`, `/products?id=2`, and `/products` all dedupe to
  one row: `/products`.
- `sitemap.xml` is read (if present) as extra seed URLs.
- `robots.txt` is respected by default; `respect_robots: false` in the
  `POST /api/projects/{id}/crawl` body overrides this for auditing your own
  site.
- Skips non-page resources (`.pdf`, images, `.zip`, `.css`, `.js`, fonts,
  etc.), `mailto:`, `tel:`, `javascript:`, and anchor-only links.
- Configurable `max_depth` (default 3) and `max_pages` (default 200).
- Runs concurrently (default 8 in-flight requests, configurable via
  `CRAWLER_CONCURRENCY`) so larger sites don't time out the request.
- Redirects are followed; the page is stored under its final, normalized
  destination.
- Re-crawling a project replaces its page set, so removed/renamed pages
  don't linger.

## API summary

| Method | Path | Auth | Description |
|--------|------|------|--------------|
| POST | `/api/auth/signup` | – | Create an account |
| POST | `/api/auth/login` | – | Get access + refresh tokens |
| POST | `/api/auth/refresh` | – | Rotate refresh token, get new access token |
| POST | `/api/auth/logout` | – | Revoke a refresh token |
| GET | `/api/users/me` | ✅ | Current user's profile |
| POST | `/api/projects` | ✅ | Create a project |
| GET | `/api/projects` | ✅ | List your projects |
| GET | `/api/projects/{id}` | ✅ | Get one project |
| POST | `/api/projects/{id}/crawl` | ✅ | Start a crawl (returns immediately; runs in background) |
| GET | `/api/projects/{id}/crawl/status` | ✅ | Poll crawl status + page count |
| GET | `/api/projects/{id}/pages` | ✅ | List discovered unique pages |

All error responses use a consistent `{"detail": "..."}` shape.

## Notes / known Phase-1 limitations

- The crawl job runs as a FastAPI `BackgroundTask` in the same process as
  the API. That's sufficient for Phase 1's scale; a dedicated task queue
  (Celery/RQ/arq) would be the natural upgrade if crawls need to survive an
  API restart or run on a separate worker.
- `is_same_site` treats any host that is a subdomain (in either direction)
  of the base URL's host as in-scope, which is a reasonable default for
  auditing a single site but is not full public-suffix-list-aware.
