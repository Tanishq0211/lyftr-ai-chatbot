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
| Frontend | Chromium verified desktop and mobile layouts, required selectors and nesting, keyboard and button sends, fresh sessions on reload, exact API metadata, cache, and readable 422/503 errors. It reported zero uncaught JavaScript errors and zero unexpected network failures. |
| Automated suite | 25 backend tests passed. The production Vite build passed. |
| Secrets and repository | The signed-out GitHub API returned 200. The Git index, reachable Git history, frontend build files, and local backend logs were scanned for the configured keys and common key patterns. No matches were found. |

## Public production results

The [Vercel production URL](https://lyftr-ai-chatbot-omega.vercel.app) and [Railway health endpoint](https://relay-api-production-96613d26.up.railway.app/health) both returned HTTP 200 without authentication. The backend returned the exact Vercel `Access-Control-Allow-Origin` header and allowed `X-Simulate-Failure` on a preflight request.

| Check | Observed result |
| --- | --- |
| Health | `status: ok`, `keys_configured: 2`, `cache_enabled: true`. |
| Live first turn | HTTP 200, Gemini `key_1`, `LIVE_INFERENCE`, 794 ms, 40 input and 1 output token. |
| Cross-session repeat | HTTP 200, `LLM_CACHE`, 0 ms at whole-millisecond precision, identical text and token counts, null key ID and zero fallback attempts. |
| Follow-up and history | Gemini recalled the codeword. History returned four entries with exact assistant metadata, and the repeat session held only its own two entries. |
| Simulated primary 429 | HTTP 200, real Groq reply, `key_2`, one fallback attempt, 367 ms. |
| Simulated primary 500 | HTTP 200, real Groq reply, `key_2`, one fallback attempt, 218 ms. |
| Error cases | Invalid input returned 422. Both complete failure simulations returned 503. History remained unchanged, and the failed session returned 404. |
| Production browser | Chromium at 1,440 px and 390 px verified the required selectors, exact API metadata, session reset, context, cache, and readable 422/503 errors. Zero uncaught JavaScript errors or unexpected network failures. |
| Service restart | Railway logs showed a new application startup. The public API returned the identical four-message SQLite history and assistant metadata after the restart, with both keys still loaded. |
| Secret audit | The production JavaScript bundle contained the public Railway origin. The bundle, 13 captured browser response bodies, and Railway runtime logs had no configured provider key matches. |
| Hosting | Vercel Hobby and Railway's no-payment trial. Railway reported a ready 500 MB volume mounted at `/data`. |

## Submission checklist

| Requirement | Status |
| --- | --- |
| React chat, session control, loading, keyboard and responsive layouts | Verified locally |
| Exact metadata fields and frontend selectors | Verified locally |
| FastAPI contract and JSON 422, 404 and 503 responses | Verified locally |
| Gemini primary, Groq fallback, request-scoped failure testing | Verified locally |
| Model-and-context cache and per-request usage | Verified locally |
| SQLite history, transaction integrity and persistent mount | Verified locally and after a Railway service restart |
| Multi-stage Docker images, `make up` and `make down` | Verified locally |
| Public GitHub repository and setup instructions | Published and verified |
| Public Railway API, Vercel frontend and cross-origin production tests | Public endpoints and CORS verified |
| Vercel GitHub auto-deploy link | The production build was uploaded from committed source with the Vercel CLI. The GitHub login connection requires account-owner approval. |
| Narrated public demo video | Recording commands and narration prepared in [DEMO_SCRIPT.md](DEMO_SCRIPT.md) |
