# Relay

Relay is a multi-turn AI chat built with React, FastAPI, LiteLLM, and SQLite. Every reply shows where it came from, which model answered, its response time, and its input and output tokens.

## Live URLs

- **Source:** [Public GitHub repository](https://github.com/Tanishq0211/lyftr-ai-chatbot)
- **Frontend:** [Relay on Vercel](https://lyftr-ai-chatbot-omega.vercel.app)
- **API base:** [Railway backend](https://relay-api-production-96613d26.up.railway.app)
- **Health:** [GET /health](https://relay-api-production-96613d26.up.railway.app/health)
- **Local Docker:** [Frontend](http://localhost:3000) and [API health](http://localhost:8000/health).

### Deploy publicly

1. Create a Railway Dockerfile service using `backend` as the root and set its health check to `/health`. Attach a volume at `/data`, keep one replica, and use `DATABASE_URL=sqlite:////data/app.db`. The container listens on Railway's injected `PORT`. If the mounted volume is owned by root, set `RAILWAY_RUN_UID=0` in Railway to permit SQLite writes. [Railway volume documentation](https://docs.railway.com/volumes/reference)
2. Set `LLM_API_KEYS` to two distinct provider keys using Railway's service variables. Set `LLM_MODELS=gemini/gemini-3.5-flash-lite,groq/openai/gpt-oss-20b` for Gemini as primary and Groq as fallback. Keys and models must use the same order. Set `ENABLE_FAILURE_SIMULATION=true` for evaluation, then generate a public domain for the backend.
3. Import the GitHub repository into a personal Vercel Hobby workspace. Choose the Vite preset, set the root directory to `frontend`, and use `dist` as the output directory. Set `VITE_API_BASE_URL` to the Railway HTTPS origin before building. Add the exact production Vercel origin to Railway's `ALLOWED_ORIGINS` and apply the backend changes. [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)
4. Check `/health` and complete the verification steps below against the public URLs. Railway's Free plan includes one 0.5 GB volume and $1 of monthly usage. It sleeps when idle and pauses service if the allowance runs out. New eligible accounts can also receive trial credits. [Railway Free plan](https://docs.railway.com/pricing/free-plan)

## Run locally: with Docker and without

### With Docker

Copy `.env.example` to `.env` and replace both key placeholders. Configure `LLM_MODEL` for a shared model or `LLM_MODELS` for different models. For two Gemini keys, credentials from distinct Google Cloud projects allow independent project-level quota. Run:

```sh
make up
make down
```

On Windows without Make, the equivalent commands are `docker compose up --build --detach --wait` and `docker compose down`. The named `chat-data` volume survives `make down`. Never commit your `.env` file.

### Without Docker

Use Python 3.12, [uv](https://docs.astral.sh/uv/), and Node.js 22. Copy `.env.example` to `.env`, fill in the keys, and change `DATABASE_URL` to `sqlite:///./data/app.db` for a repository-local database. From two terminals in the repository root:

```sh
cd backend
uv run --no-project --env-file ../.env --python 3.12 --with-requirements requirements.txt \
  uvicorn app.main:create_app --factory --port 8000
```

```sh
cd frontend
npm ci
npm run dev
```

Open [localhost:5173](http://localhost:5173). Vite reads a frontend-local `.env` if you need to override `VITE_API_BASE_URL`, which otherwise defaults to `http://localhost:8000`.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEYS` | Backend-only comma-separated credentials. The first is `key_1`, the second `key_2`. |
| `LLM_MODEL` | LiteLLM model name applied to all keys when `LLM_MODELS` is unset. |
| `LLM_MODELS` | Optional comma-separated model names in key order. |
| `LLM_API_BASE` | Optional custom provider base URL. Leave blank for standard provider endpoints. |
| `DATABASE_URL` | SQLite file URL. Use `sqlite:////data/app.db` in Docker and Railway. |
| `ALLOWED_ORIGINS` | Comma-separated allowed frontend origins, including scheme and port if applicable. |
| `ENABLE_FAILURE_SIMULATION` | Set to `true` for the assignment's `X-Simulate-Failure` header. |
| `PORT` | Docker backend listen port. Railway sets this automatically. |
| `VITE_API_BASE_URL` | Public backend URL embedded in the frontend at build time. |

## Design decisions: key fallback, caching, SQLite session storage

- **Key fallback.** The gateway calls the model assigned to each key through LiteLLM in the order specified by `LLM_API_KEYS`. Each credential is attempted once. Rate limits, quota errors, upstream 5xx responses, authentication failures, connectivity failures, and timeouts advance the pool. Errors are reported with a JSON `detail` field. Only the alias `key_1`, `key_2`, and so on appears in successful response metadata. `/health` checks the database and key configuration without spending provider quota.
- **Cache.** LiteLLM's built-in in-memory cache holds up to 512 successful replies for up to one hour. A SHA-256 key covers the model that answered and the full ordered message list, including roles, the system prompt, history, and the new message. The gateway checks each configured model for a cached reply before calling a provider, so a previous fallback reply can hit the cache too. A hit uses the stored text and provider-reported usage with a null key alias and a fallback count of zero. Recognized failure simulations bypass the cache to exercise provider routing even on a repeat prompt.
- **SQLite.** A session holds its latest system prompt and an append-only history. The successful user message, assistant message, and prompt update commit together. Failed turns leave the database unchanged. Within the single configured backend worker, turns for the same session are serialized while network calls can overlap across sessions. History survives container restarts, while the in-memory cache starts cold. The history endpoint omits the system prompt.
- **Metrics.** Input and output tokens come from the provider's response for that turn. Latency is measured on the server from entry into the chat handler through response resolution, including time waiting for earlier turns and reading context.

## Verification: how to see failover, cache hits and per-message token usage

| Route | Success | Error cases |
| --- | --- | --- |
| `GET /health` | `200` with `status`, `keys_configured`, and `cache_enabled` | `503` if SQLite or the configured key pool is unavailable |
| `POST /chat` | `200` with `session_id`, `reply`, and `metadata` | `422` on invalid input, `503` when providers are unavailable |
| `GET /sessions/{session_id}/messages` | `200` with `session_id` and oldest-first `messages` | `404` with `detail: session not found` for an unknown session |

Metadata on each assistant turn includes `resolution_source`, `model`, `latency_ms`, `input_tokens`, `output_tokens`, `key_id`, and `fallback_attempts`. The key alias is null on a cache hit. The history route returns stored assistant metadata as well as each user message.

Set `BASE` to the target backend URL. The examples use POSIX shell syntax and `curl`.

```sh
BASE=http://localhost:8000
TAG=$(date +%s)
QUESTION="What is the capital of France? Run $TAG."

curl -fsS "$BASE/health"

curl -fsS "$BASE/chat" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"live-$TAG\",\"message\":\"$QUESTION\"}"

curl -fsS "$BASE/chat" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"cache-$TAG\",\"message\":\"$QUESTION\"}"

curl -fsS "$BASE/chat" -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=429' \
  -d "{\"session_id\":\"fallback-$TAG\",\"message\":\"$QUESTION\"}"

curl -fsS "$BASE/chat" -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=500' \
  -d "{\"session_id\":\"fallback-500-$TAG\",\"message\":\"$QUESTION\"}"

curl -sS -i "$BASE/chat" -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: *=429' \
  -d "{\"session_id\":\"unavailable-$TAG\",\"message\":\"$QUESTION\"}"

curl -fsS "$BASE/sessions/live-$TAG/messages"
curl -sS -i "$BASE/sessions/unavailable-$TAG/messages"
```

The first two completions should match, with `LIVE_INFERENCE` followed by `LLM_CACHE`. Compare token counts and latency. The simulated 429 should produce a live answer with `key_2` and `fallback_attempts: 1`. Simulating failure for all keys should return 503 and leave the new session absent from history. To check multi-turn context in the UI, ask the assistant to remember a word, then ask it what the word was. Use **New chat** and repeat a first message to see the cache hit in the UI.

Run the backend suite from `backend`. It exercises the real LiteLLM adapter against a deterministic local HTTP fixture and requires no provider credentials.

```sh
uv run --no-project --python 3.12 --with-requirements requirements-dev.txt python -m pytest -q
```

Run `python scripts/verify_live.py <backend-origin> --origin <frontend-origin>` from the repository root to verify the HTTP contract against real providers. It uses four successful inference calls. The output includes a session ID for checking persistence after a restart.

See [VERIFICATION.md](VERIFICATION.md) for recorded test results and the assignment checklist.

### Demo outline

Use [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for a timed recording guide, narration, and commands.

## Setup Used: your editor and AI tools

OpenAI Codex desktop, PowerShell, Python 3.12, uv, Node.js, and Docker Desktop.

## Bonus features (if any): what you added beyond the requirements and why

The optional system prompt persists with the active session. Clearing it and sending a message restores the default assistant instructions. **New chat** starts a fresh session without reloading, so a first-message cache hit is easy to demonstrate in the UI.
