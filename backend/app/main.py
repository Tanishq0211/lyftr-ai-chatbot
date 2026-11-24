import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints, field_validator

from .config import Settings
from .gateway import Gateway, ProvidersUnavailable
from .storage import Storage

logger = logging.getLogger(__name__)
DEFAULT_PROMPT = 'You are a helpful assistant. Be clear and concise.'


class ChatRequest(BaseModel):
    session_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    system_prompt: str | None = None

    @field_validator('session_id')
    @classmethod
    def require_nonblank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('session_id cannot be blank')
        return value


def create_app():
    settings = Settings.from_env()
    storage = Storage(settings.database)
    gateway = Gateway(settings)
    # Keep turn ordering per session in a single worker with a bounded lock pool.
    turn_locks = [asyncio.Lock() for _ in range(256)]

    @asynccontextmanager
    async def lifespan(_app):
        await run_in_threadpool(storage.initialize)
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        details = [{field: issue[field] for field in ('loc', 'msg', 'type')} for issue in error.errors()]
        return JSONResponse(status_code=422, content={'detail': details})

    @app.middleware('http')
    async def json_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as error:
            logger.error('Request could not be completed (%s)', type(error).__name__)
            return JSONResponse(status_code=500, content={'detail': 'internal server error'})

    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.origins), allow_methods=['GET', 'POST'],
        allow_headers=['Content-Type', 'X-Simulate-Failure'],
    )

    @app.get('/health')
    def health():
        try:
            storage.check()
        except (OSError, sqlite3.Error):
            raise HTTPException(503, 'database unavailable') from None
        if not gateway.ready:
            raise HTTPException(503, 'provider key pool is not configured')
        return {'status': 'ok', 'keys_configured': len(settings.keys), 'cache_enabled': True}

    @app.post('/chat')
    async def chat_turn(body: ChatRequest, x_simulate_failure: Annotated[str | None, Header()] = None):
        started = perf_counter()
        lock = turn_locks[hash(body.session_id) % len(turn_locks)]
        async with lock:
            saved_prompt, previous = await run_in_threadpool(storage.read, body.session_id)
            prompt = saved_prompt or DEFAULT_PROMPT
            if body.system_prompt is not None:
                prompt = body.system_prompt.strip() or DEFAULT_PROMPT
            messages = [{'role': 'system', 'content': prompt}]
            messages.extend({'role': item['role'], 'content': item['content']} for item in previous)
            messages.append({'role': 'user', 'content': body.message})
            try:
                answer = await gateway.answer(messages, x_simulate_failure)
            except ProvidersUnavailable:
                raise HTTPException(503, 'all providers unavailable') from None

            metadata = {
                'resolution_source': 'LLM_CACHE' if answer.key_id is None else 'LIVE_INFERENCE',
                'model': answer.model,
                'latency_ms': int((perf_counter() - started) * 1000),
                'input_tokens': answer.input_tokens,
                'output_tokens': answer.output_tokens,
                'key_id': answer.key_id,
                'fallback_attempts': answer.fallback_attempts,
            }
            await run_in_threadpool(storage.append_turn, body.session_id, prompt, body.message, answer.reply, metadata)
        return {'session_id': body.session_id, 'reply': answer.reply, 'metadata': metadata}

    @app.get('/sessions/{session_id:path}/messages')
    def history(session_id: str):
        _, messages = storage.read(session_id)
        if not messages:
            raise HTTPException(404, 'session not found')
        return {'session_id': session_id, 'messages': messages}

    return app
