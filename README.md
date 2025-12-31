# Pastebin Lite

A lightweight pastebin service built with FastAPI that supports text paste sharing with optional time-based expiry (TTL) and view count limits.

## Features
- Create text pastes and receive shareable URLs
- Optional TTL (time-to-live) expiry in seconds
- Optional view count limits
- Deterministic time testing support via TEST_MODE
- Automatic paste cleanup when constraints are met

## Local Setup

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd pastebin-lite
   ```

2. **Create virtual environment and install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Create `.env` file with your Redis credentials:**
   ```env
   UPSTASH_REDIS_REST_URL=your_upstash_redis_url
   UPSTASH_REDIS_REST_TOKEN=your_upstash_redis_token
   TEST_MODE=1
   ```

4. **Run the application:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

5. **Access the application:**
   - Web UI: `http://localhost:8000`
   - API docs: `http://localhost:8000/docs`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/healthz` | Health check (returns JSON with Redis status) |
| POST | `/api/pastes` | Create a new paste (returns id and url) |
| GET | `/api/pastes/:id` | Fetch paste via API (increments view count) |
| GET | `/p/:id` | View paste as HTML page |

### Example: Create Paste
```bash
curl -X POST http://localhost:8000/api/pastes \
  -H "Content-Type: application/json" \
  -d '{"content":"Hello World", "ttl_seconds":3600, "max_views":5}'
```

Response:
```json
{
  "id": "abc123xyz",
  "url": "http://localhost:8000/p/abc123xyz"
}
```

### Example: Fetch Paste
```bash
curl http://localhost:8000/api/pastes/abc123xyz
```

Response:
```json
{
  "content": "Hello World",
  "remaining_views": 4,
  "expires_at": "2025-12-31T14:30:00.000Z"
}
```

## Persistence Layer

**Upstash Redis** (serverless Redis) was chosen as the persistence layer for the following reasons:

1. **HTTP-based REST API**: Works seamlessly in serverless environments without TCP connection pooling issues
2. **Native TTL support**: Redis EXPIRE command provides automatic cleanup of expired pastes
3. **Atomic operations**: Ensures thread-safe view count increments using JSON serialization
4. **Serverless-compatible**: No persistent connections required, ideal for platforms like Render/Vercel
5. **Free tier available**: Generous limits for development and small-scale production use
6. **Global replication**: Low-latency access from edge locations

The application stores each paste as a JSON string in Redis with the key format `paste:{id}`, containing:
- `content`: The paste text
- `created_at`: Timestamp in milliseconds
- `ttl_seconds`: Optional expiry duration
- `max_views`: Optional view limit
- `view_count`: Current number of API fetches

## Design Decisions

### 1. Upstash Redis over Traditional Redis
Traditional Redis requires persistent TCP connections, which don't work well in serverless environments where each request may spawn a new process. Upstash's HTTP-based API solves this completely.

### 2. Atomic View Count Handling
Each API fetch (`GET /api/pastes/:id`) increments the `view_count` before returning data. The HTML route (`GET /p/:id`) only reads the paste without incrementing, as per specification.

### 3. TEST_MODE Support for Deterministic Testing
When `TEST_MODE=1` environment variable is set, the application honors the `x-test-now-ms` request header for time-based expiry calculations. This allows automated tests to verify TTL behavior without waiting for real time to pass.

### 4. Combined Constraint Logic
When both `ttl_seconds` and `max_views` are specified, the paste becomes unavailable as soon as **either** constraint is triggered (whichever happens first). This is validated on every fetch request.

### 5. XSS Prevention
Paste content is rendered inside HTML `<pre>` tags, which automatically escapes special characters and prevents script execution.

### 6. Error Handling Consistency
All unavailable states (missing paste, expired, view limit exceeded) return HTTP 404 with JSON error messages, ensuring consistent behavior for automated tests.

### 7. ID Generation
Using Python's `secrets.token_urlsafe()` for cryptographically secure, URL-safe paste IDs that are collision-resistant.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `UPSTASH_REDIS_REST_URL` | Yes | Your Upstash Redis REST endpoint URL |
| `UPSTASH_REDIS_REST_TOKEN` | Yes | Your Upstash Redis REST API token |
| `TEST_MODE` | No | Set to `1` to enable deterministic time testing |

## Testing

The application passes all automated test requirements:

- ✅ Health check returns 200 with valid JSON
- ✅ Paste creation returns valid id and url
- ✅ View limits enforced correctly (API increments, HTML doesn't)
- ✅ TTL expiry works with deterministic time headers
- ✅ Combined constraints (first trigger wins)
- ✅ All error cases return 404 with JSON
- ✅ No hardcoded localhost URLs in code
- ✅ No secrets committed to repository

### Manual Testing Examples

**Test max_views:**
```bash
# Create paste with 2 view limit
curl -X POST http://localhost:8000/api/pastes \
  -H "Content-Type: application/json" \
  -d '{"content":"Test", "max_views":2}'

# First fetch: remaining_views=1
curl http://localhost:8000/api/pastes/{id}

# Second fetch: remaining_views=0
curl http://localhost:8000/api/pastes/{id}

# Third fetch: 404 (limit exceeded)
curl http://localhost:8000/api/pastes/{id}
```

**Test TTL with deterministic time:**
```bash
# Create paste with 60 second TTL
curl -X POST http://localhost:8000/api/pastes \
  -H "Content-Type: application/json" \
  -d '{"content":"Test", "ttl_seconds":60}'

# Fetch before expiry (30 seconds in) - returns 200
curl http://localhost:8000/api/pastes/{id} \
  -H "x-test-now-ms: <timestamp_plus_30000>"

# Fetch after expiry (70 seconds in) - returns 404
curl http://localhost:8000/api/pastes/{id} \
  -H "x-test-now-ms: <timestamp_plus_70000>"
```

## Deployment

The application is deployed on Render with the following configuration:

**Build Command:**
```bash
pip install -r requirements.txt
```

**Start Command:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Environment Variables:**
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `TEST_MODE=1`

## Tech Stack Summary

- **Backend Framework**: FastAPI (Python 3.12)
- **Database**: Upstash Redis (serverless)
- **Template Engine**: Jinja2
- **Deployment**: Render
- **ID Generation**: secrets.token_urlsafe()

## Project Structure

```
pastebin-lite/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI routes and logic
│   ├── redis_client.py      # Upstash Redis connection
│   └── templates/
│       └── view_paste.html  # HTML template for paste viewing
├── .env                      # Environment variables (not committed)
├── .gitignore
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## License

MIT
