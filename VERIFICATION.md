# Assignment verification

## Local Docker and real-provider results

Verified on November 24, 2026. The containerized backend used real Gemini and Groq requests. The frontend container listened on port 3000, mapped to host port 3100 because another service on the verification machine already occupied host port 3000. The checked-in configuration defaults to host ports 3000 and 8000.

| Check | Observed result |
| --- | --- |
| Independent provider checks | Gemini 3.5 Flash-Lite and Groq GPT-OSS 20B both generated text through LiteLLM. |
| Health | HTTP 200, `status: ok`, `keys_configured: 2`, `cache_enabled: true`. |
| First turn | HTTP 200, `LIVE_INFERENCE`, Gemini `key_1`, 1,015 ms, 36 input and 2 output tokens. |
| Repeat in a new session | HTTP 200, `LLM_CACHE`, 1 ms, identical reply and 36 input and 2 output tokens, null key ID and zero fallback attempts. |
| Follow-up | HTTP 200. Gemini recalled the session codeword using 56 input and 12 output tokens. |
| Simulated primary 429 | HTTP 200, real Groq reply, `key_2`, one fallback attempt, 578 ms. |
| Simulated primary 500 | HTTP 200, real Groq reply, `key_2`, one fallback attempt, 594 ms. |
| Exhaustion | Both wildcard and mixed-status simulations returned HTTP 503 with the specified `detail`. The failed session remained absent. |
| Validation and history | Invalid input returned 422. Unknown history returned 404. The successful session had four chronological entries with stored assistant metadata. |
| SQLite persistence | The exact four-message history and metadata were retrieved after a backend restart and again after `make down` followed by `make up`. |
| Frontend | Chromium verified desktop and mobile layouts, required selectors and nesting, keyboard and button sends, fresh sessions on reload, exact API metadata, cache, readable 422/503 errors, and zero uncaught JavaScript errors. |
| Automated suite | 25 backend tests passed. The production Vite build passed. |
| Secrets and repository | The signed-out GitHub API returned 200. The Git index, reachable Git history, frontend build files, and local backend logs were scanned for the configured keys and common key patterns. No matches were found. |

## Submission checklist

| Requirement | Status |
| --- | --- |
| React chat, session control, loading, keyboard and responsive layouts | Verified locally |
| Exact metadata fields and frontend selectors | Verified locally |
| FastAPI contract and JSON 422, 404 and 503 responses | Verified locally |
| Gemini primary, Groq fallback, request-scoped failure testing | Verified locally |
| Model-and-context cache and per-request usage | Verified locally |
| SQLite history, transaction integrity and persistent mount | Verified locally |
| Multi-stage Docker images, `make up` and `make down` | Verified locally |
| Public GitHub repository and setup instructions | Published and verified |
| Public Railway API, Vercel frontend and cross-origin production tests | Pending account authorization |
| Narrated public demo video | Recording commands and narration prepared in [DEMO_SCRIPT.md](DEMO_SCRIPT.md) |
