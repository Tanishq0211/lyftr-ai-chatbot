import json
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def provider():
    calls = []
    failures = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            key = self.headers['Authorization'].removeprefix('Bearer ')
            messages = payload['messages']
            calls.append((key, messages))
            status, code = failures.get(key, (200, None))
            if status == 200:
                time.sleep(0.04)
                text = ' | '.join(message['content'] for message in messages if message['role'] == 'user')
                body = {
                    'id': 'completion-fixture', 'object': 'chat.completion',
                    'created': 1, 'model': payload['model'],
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text},
                                 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 10 + len(messages), 'completion_tokens': 4, 'total_tokens': 14 + len(messages)},
                }
            else:
                body = {'error': {'message': code, 'code': code, 'type': code}}
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', calls, failures
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


@pytest.fixture
def configured(provider, monkeypatch, tmp_path):
    url, calls, failures = provider
    monkeypatch.setenv('LLM_API_BASE', url)
    monkeypatch.setenv('LLM_API_KEYS', 'test-first,test-second')
    monkeypatch.setenv('LLM_MODEL', 'openai/gpt-4o-mini')
    monkeypatch.delenv('LLM_MODELS', raising=False)
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{(tmp_path / "app.db").as_posix()}')
    monkeypatch.setenv('ENABLE_FAILURE_SIMULATION', 'true')
    monkeypatch.setenv('ALLOWED_ORIGINS', 'https://frontend.example')
    return calls, failures


@pytest.fixture
def client(configured):
    with TestClient(create_app()) as client:
        yield client


def chat(client, session, message, simulation=None, **fields):
    headers = {'X-Simulate-Failure': simulation} if simulation else {}
    return client.post('/chat', headers=headers, json={'session_id': session, 'message': message, **fields})


def test_health_and_cors(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'keys_configured': 2, 'cache_enabled': True}
    preflight = client.options('/chat', headers={
        'Origin': 'https://frontend.example', 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type,x-simulate-failure',
    })
    assert preflight.headers['access-control-allow-origin'] == 'https://frontend.example'
    assert client.get('/docs').status_code == 404


def test_cache_reuses_reply_and_usage_across_sessions(client, configured):
    calls, _ = configured
    first = chat(client, 'one', '  Apples  ').json()
    second = chat(client, 'two', 'Apples').json()
    fresh = chat(client, 'three', 'Pears!').json()
    assert first['reply'] == second['reply'] == 'Apples'
    live = first['metadata']
    hit = second['metadata']
    assert live['resolution_source'] == fresh['metadata']['resolution_source'] == 'LIVE_INFERENCE'
    assert live['key_id'] == 'key_1'
    assert hit == {**live, 'resolution_source': 'LLM_CACHE', 'key_id': None, 'latency_ms': hit['latency_ms']}
    assert isinstance(hit['latency_ms'], int) and hit['latency_ms'] < live['latency_ms']
    assert live['input_tokens'] == fresh['metadata']['input_tokens'] == 12
    assert live['output_tokens'] == 4
    assert live['model'] == 'openai/gpt-4o-mini'
    assert len(calls) == 2
    assert client.get('/sessions/two/messages').json()['messages'][1]['metadata'] == hit


def test_context_prompt_and_history_persist_after_restart(client, configured):
    calls, _ = configured
    first = chat(client, 'existing', 'Remember Daffodil.', system_prompt='Be brief.').json()
    follow_up = chat(client, 'existing', 'What was the word?').json()
    isolated = chat(client, 'fresh', 'What was the word?').json()
    changed_prompt = chat(client, 'custom', 'Remember Daffodil.', system_prompt='Use French.').json()
    assert follow_up['reply'] == 'Remember Daffodil. | What was the word?'
    assert isolated['reply'] == 'What was the word?'
    assert changed_prompt['metadata']['resolution_source'] == 'LIVE_INFERENCE'
    assert follow_up['metadata']['input_tokens'] == 14
    assert calls[1][1] == [
        {'role': 'system', 'content': 'Be brief.'},
        {'role': 'user', 'content': 'Remember Daffodil.'},
        {'role': 'assistant', 'content': first['reply']},
        {'role': 'user', 'content': 'What was the word?'},
    ]
    with TestClient(create_app()) as restarted:
        response = restarted.get('/sessions/existing/messages')
    assert response.status_code == 200
    assert response.json() == {'session_id': 'existing', 'messages': [
        {'role': 'user', 'content': 'Remember Daffodil.'},
        {'role': 'assistant', 'content': first['reply'], 'metadata': first['metadata']},
        {'role': 'user', 'content': 'What was the word?'},
        {'role': 'assistant', 'content': follow_up['reply'], 'metadata': follow_up['metadata']},
    ]}


@pytest.mark.parametrize('status', [429, 500, 502, 503])
def test_simulated_failover_bypasses_warm_cache_for_one_request(client, configured, status):
    calls, _ = configured
    assert chat(client, 'warm', 'A repeatable question').status_code == 200
    fallback = chat(client, 'fallback', 'A repeatable question', f'key_1={status}').json()['metadata']
    assert fallback['resolution_source'] == 'LIVE_INFERENCE'
    assert fallback['key_id'] == 'key_2'
    assert fallback['fallback_attempts'] == 1
    assert chat(client, 'normal', 'A different question').json()['metadata']['key_id'] == 'key_1'
    assert [key for key, _ in calls] == ['test-first', 'test-second', 'test-first']


@pytest.mark.parametrize(('status', 'code'), [(429, 'rate_limit_exceeded'), (403, 'insufficient_quota'), (503, 'overloaded')])
def test_provider_failover_follows_actual_http_errors(client, configured, status, code):
    calls, failures = configured
    failures['test-first'] = status, code
    answer = chat(client, 'failover', 'Actual upstream failover')
    assert answer.status_code == 200
    assert answer.json()['metadata']['key_id'] == 'key_2'
    assert answer.json()['metadata']['fallback_attempts'] == 1
    assert [key for key, _ in calls] == ['test-first', 'test-second']


def test_cache_tracks_the_model_used_by_the_fallback(configured, monkeypatch):
    calls, failures = configured
    failures['test-first'] = 429, 'rate_limit_exceeded'
    monkeypatch.setenv('LLM_MODELS', 'openai/gpt-4o-mini,openai/gpt-4.1-mini')
    with TestClient(create_app()) as client:
        live = chat(client, 'first', 'Cross-model routing').json()
        hit = chat(client, 'second', 'Cross-model routing').json()
        del failures['test-first']
        fresh = chat(client, 'new', 'Different prompt').json()
    assert live['metadata']['model'] == hit['metadata']['model'] == 'openai/gpt-4.1-mini'
    assert live['metadata']['key_id'] == 'key_2'
    assert hit['metadata']['resolution_source'] == 'LLM_CACHE'
    assert fresh['metadata']['model'] == 'openai/gpt-4o-mini'
    assert [key for key, _ in calls] == ['test-first', 'test-second', 'test-first']


def test_session_ids_with_encoded_slashes_can_be_read(client):
    assert chat(client, 'segment/child', 'A message').status_code == 200
    response = client.get('/sessions/segment%2Fchild/messages')
    assert response.status_code == 200
    assert response.json()['session_id'] == 'segment/child'


@pytest.mark.parametrize('simulation', ['*=429', 'key_1=429,key_2=500'])
def test_exhausted_keys_leave_history_untouched(client, configured, simulation):
    calls, _ = configured
    assert chat(client, 'existing', 'Successful first turn.').status_code == 200
    before = client.get('/sessions/existing/messages').json()
    response = chat(client, 'existing', 'Unsuccessful second turn.', simulation)
    assert response.status_code == 503
    assert response.json() == {'detail': 'all providers unavailable'}
    assert client.get('/sessions/existing/messages').json() == before
    assert chat(client, 'new', 'Successful first turn.', simulation).status_code == 503
    assert client.get('/sessions/new/messages').json() == {'detail': 'session not found'}
    assert len(calls) == 1


def test_simulation_can_be_disabled(configured, monkeypatch):
    monkeypatch.setenv('ENABLE_FAILURE_SIMULATION', 'false')
    with TestClient(create_app()) as client:
        answer = chat(client, 'normal', 'Question', '*=429')
    assert answer.json()['metadata']['key_id'] == 'key_1'


@pytest.mark.parametrize('body', [
    '{}', '{this is malformed', '{"session_id":"s"}', '{"message":"Hi"}',
    '{"session_id":"","message":"Hi"}', '{"session_id":"s","message":"   "}',
    r'{"session_id":"s","message":"\ud800"}',
    json.dumps({'session_id': 'x' * 129, 'message': 'Hi'}),
    json.dumps({'session_id': 's', 'message': 'x' * 4001}),
])
def test_validation_errors_do_not_write_history(client, body):
    response = client.post('/chat', content=body, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert 'detail' in response.json()
    assert client.get('/sessions/s/messages').status_code == 404


def test_concurrent_turns_use_the_previous_committed_turn(client, configured):
    calls, _ = configured
    with ThreadPoolExecutor(2) as executor:
        responses = list(executor.map(lambda text: chat(client, 'shared', text), ['First', 'Second']))
    assert [response.status_code for response in responses] == [200, 200]
    assert [len(messages) for _, messages in calls] == [2, 4]
    assert calls[1][1][1] == calls[0][1][1]
    assert len(client.get('/sessions/shared/messages').json()['messages']) == 4
