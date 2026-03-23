---
name: intent-expansion
description: Rules for expanding vague user descriptions into structured feature context using domain conventions and project stack. Load as the first step of context enrichment before any internal scanning.
alwaysApply: false
triggers: [context enrichment, vague intent, new feature request]
---

# intent-expansion Skill

Rules for expanding a vague user description into a rich feature context before writing any issue content.

## Step 1: Identify the domain

Map the user's words to one or more domains:

| User says | Domain |
|-----------|--------|
| login, signup, token, session, password | `auth` |
| create, read, update, delete, list, CRUD | `crud` |
| search, filter, find, query | `search` |
| upload, file, image, attachment | `upload` |
| email, push, SMS, notify | `notification` |
| payment, stripe, billing, invoice | `payment` |
| analytics, event, tracking, metrics | `analytics` |
| export, download, CSV, PDF | `export` |
| webhook, callback, event sink | `webhook` |
| background job, queue, worker, async | `async-job` |

## Step 2: Apply domain conventions

For each identified domain, apply these conventional patterns as a starting point:

### `auth`
- JWT with 24h access token + 7-day refresh token
- bcrypt for password hashing (cost factor 12)
- Logout = blacklist token (not stateless invalidation)
- Routes: `POST /auth/login`, `POST /auth/register`, `POST /auth/refresh`, `POST /auth/logout`

### `crud`
- Input validation at the route layer
- Pagination: `limit` / `offset` (or `page` / `page_size`)
- Soft delete: `deleted_at` timestamp instead of hard delete
- Timestamps: `created_at`, `updated_at` on every model

### `search`
- Full-text or `ILIKE` depending on database support
- Pagination on all search results
- Relevance scoring if multiple fields searched
- Index on all searched columns

### `upload`
- Max file size validation (reject early, before processing)
- MIME type allowlist check
- Storage path convention: `<entity>/<id>/<filename>` or object-store key
- Async processing for files > 1MB

### `export`
- Async job with progress tracking for large datasets
- Download URL with expiry (presigned URL or token-gated endpoint)
- Format options: CSV, XLSX, JSON depending on user need

### `notification`
- Deduplication key to prevent double-sends
- User preference check before sending
- Retry with exponential backoff on transient failures

### `async-job`
- Status polling endpoint or webhook callback
- Idempotency key on job creation
- Dead-letter handling for repeated failures

## Step 3: Filter by project stack

From `project_summary.md`, extract the tech stack. Remove patterns incompatible with the stack:
- If no Redis: remove token blacklist, use short-lived tokens instead
- If not FastAPI: remove FastAPI-specific patterns
- If SQLite: remove PostgreSQL full-text search, use `LIKE` instead
- If no background worker: remove async job patterns, use synchronous alternatives

## Step 4: Filter by design principles

From `project_summary.md` Design Principles section:
- Apply the project's security model (authentication strategy, secret storage)
- Apply the architecture constraints (layering rules, no direct DB in routes, etc.)
- Apply the test policy (coverage threshold, integration test requirements)

## Step 5: Output the expanded intent struct

```json
{
  "original": "<user's raw description>",
  "expanded": "<full feature description with specifics>",
  "conventional_patterns": ["<pattern 1>", "<pattern 2>", "..."],
  "stack_filtered": ["<stack-specific pattern>", "..."],
  "design_constraints": ["<constraint from design principles>", "..."]
}
```

**Example:**
```json
{
  "original": "make auth",
  "expanded": "JWT auth with 24h access + 7-day refresh tokens, bcrypt passwords (cost 12), POST /api/v1/auth/* routes",
  "conventional_patterns": ["24h expiry", "refresh token rotation", "bcrypt cost 12", "token blacklist on logout"],
  "stack_filtered": ["FastAPI OAuth2PasswordBearer", "python-jose for JWT", "passlib[bcrypt]"],
  "design_constraints": ["layered: no direct DB in routes", "all routes under /api/v1/", "test coverage ≥ 80%"]
}
```

Use this struct as the input to the internal scanner (to find relevant existing code) and to the workflow writer (to produce rich issue content).
