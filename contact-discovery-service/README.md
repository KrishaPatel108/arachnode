# Contact Discovery Service

> ⚖️ **Ethical use policy** — This service queries only publicly available data sources (Clearbit Autocomplete, GitHub public APIs, LinkedIn public directory, and SMTP handshakes). It is designed exclusively for **professional outreach in an engineering placement context** — i.e., to reach out to recruiters or engineering managers at companies where a job has been found. It must not be used for spam, bulk unsolicited email, harvesting contact data for resale, or any purpose that violates the terms of service of the queried platforms. SMTP verification uses a non-sending probe (RCPT TO without DATA) and is capped at **5 attempts per domain per hour** to avoid IP blacklisting.

---

## Architecture

```
POST /discover
     │
     ▼
[1] Domain inference        company name  →  domain (Clearbit + direct probe)
     │
     ▼
[2] Email pattern detection  domain  →  pattern (GitHub commit emails)
     │
     ▼  (concurrent)
[3] Name discovery          GitHub org members  +  LinkedIn public dir
     │
     ▼
[4] Email construction      name × pattern  →  email string
     │
     ▼
[5] SMTP verification       email  →  verified | unverified | invalid
     │
     ▼
    PostgreSQL contacts table
```

---

## Project layout

```
contact-discovery-service/
├── main.py          # FastAPI app — endpoints
├── discovery.py     # Full pipeline (stages 1–5)
├── verifier.py      # SMTP email verifier + rate limiter
├── storage.py       # asyncpg pool, schema, CRUD
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | asyncpg DSN (shared with aggregator service) |
| `GITHUB_TOKEN` | — | Optional PAT — raises GitHub rate limit 60→5000 req/hr |
| `REDIS_HOST` | `localhost` | Not used directly, available for future use |
| `REDIS_PORT` | `6379` | — |

---

## Quick start

### Docker

```bash
cd contact-discovery-service
docker build -t contact-discovery .
docker run \
  -e DATABASE_URL="postgresql://jobuser:jobpass@host.docker.internal:5432/jobsdb" \
  -e GITHUB_TOKEN="ghp_..." \
  -p 8002:8000 \
  contact-discovery
```

### Local dev

```bash
cd contact-discovery-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

export DATABASE_URL="postgresql://jobuser:jobpass@localhost:5432/jobsdb"
export GITHUB_TOKEN="ghp_..."   # optional

uvicorn main:app --reload --port 8002
```

---

## API reference

Interactive docs: <http://localhost:8002/docs>

### `GET /health`

```bash
curl http://localhost:8002/health
```
```json
{"status": "ok"}
```

---

### `POST /discover` — trigger contact discovery

Returns immediately; all pipeline stages run in the background.

```bash
# Basic usage — discover contacts at Razorpay linked to a specific job
curl -X POST http://localhost:8002/discover \
     -H "Content-Type: application/json" \
     -d '{
       "company": "Razorpay",
       "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
       "roles": ["Engineering Manager", "Recruiter"]
     }'
```
```json
{
  "triggered": true,
  "company": "Razorpay",
  "roles": ["Engineering Manager", "Recruiter"],
  "message": "Discovery running in background. Poll GET /contacts?company=... for results."
}
```

If you already know the domain (faster):
```bash
curl -X POST http://localhost:8002/discover \
     -H "Content-Type: application/json" \
     -d '{"company": "Razorpay", "domain": "razorpay.com", "roles": ["Recruiter"]}'
```

---

### `GET /contacts` — list by company

```bash
# Poll after triggering discovery
curl "http://localhost:8002/contacts?company=Razorpay"
```
```json
[
  {
    "id": "...",
    "job_id": "3fa85f64-...",
    "company": "Razorpay",
    "domain": "razorpay.com",
    "name": "Alice Smith",
    "email": "alice.smith@razorpay.com",
    "role": "Engineering Manager",
    "source": "github",
    "verified": "verified",
    "created_at": "2026-03-19T06:00:00+00:00"
  }
]
```

---

### `GET /contacts/{job_id}` — list by job UUID

```bash
curl http://localhost:8002/contacts/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

---

### `DELETE /contacts/{id}` — remove a contact

```bash
curl -X DELETE http://localhost:8002/contacts/a1b2c3d4-...
# Returns 204 No Content on success
```

---

## Pipeline details

### Email pattern detection

Mines GitHub commit emails for the inferred domain.  Voting on the most common local-part structure determines the pattern:

| Pattern | Template string |
|---|---|
| `alice.smith@acme.com` | `{first}.{last}@{domain}` |
| `asmith@acme.com` | `{fi}{last}@{domain}` |
| `alices@acme.com` | `{first}{li}@{domain}` |
| `alice@acme.com` | `{first}@{domain}` |

Falls back to `{first}.{last}@{domain}` if no GitHub commits are found.

### SMTP verification

| Result | Meaning |
|---|---|
| `verified` | MX server returned SMTP 250 (mailbox likely exists) |
| `unverified` | MX unreachable, 4xx response, or rate-limit hit |
| `invalid` | MX server returned 550/551 (mailbox does not exist) |

> ⚠️ Large providers (Gmail, Outlook) always return 250 regardless of validity. Treat `verified` as a best-effort signal.

**Rate limit:** 5 verifications per domain per hour (in-memory; restarts reset the counter).

### LinkedIn selector notes (last verified March 2026)

| Selector | Element |
|---|---|
| `li.result-card, div.base-search-card` | Job/person card |
| `span.actor-name, span.name` | Name text |
| `h3.base-search-card__title` | Name fallback |
| `p.subline-level-1` | Role / subtitle |

Update these in `discovery.py → _linkedin_public_names()` when LinkedIn changes its markup. The scraper detects `/authwall` redirects and exits gracefully.

---

## Database schema

```sql
CREATE TABLE contacts (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id     UUID        REFERENCES jobs(id) ON DELETE SET NULL,
  company    TEXT        NOT NULL,
  domain     TEXT,
  name       TEXT,
  email      TEXT,
  role       TEXT,
  source     TEXT,
  verified   TEXT        NOT NULL DEFAULT 'unverified',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (company, email)
);
```
