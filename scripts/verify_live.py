"""Verify a deployment using its public HTTP API and real model providers."""

import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def verify(base: str, origin: str | None):
    def request(path, body=None, *, status=200, headers=None, method=None):
        data = None if body is None else json.dumps(body).encode()
        request_headers = {'Content-Type': 'application/json', **(headers or {})}
        if origin:
            request_headers.setdefault('Origin', origin)
        call = Request(base.rstrip('/') + path, data=data, headers=request_headers, method=method)
        try:
            response = urlopen(call, timeout=90)
        except HTTPError as error:
            response = error
        with response:
            assert response.status == status, f'{path}: expected HTTP {status}, got {response.status}'
            if origin:
                assert response.headers.get('Access-Control-Allow-Origin') == origin, f'{path}: unexpected CORS header'
            return response.read() if method == 'OPTIONS' else json.load(response)

    tag = uuid4().hex[:12]
    ongoing = f'verify-live-{tag}'
    cached = f'verify-cache-{tag}'
    failed = f'verify-failed-{tag}'
    question = f'Remember the codeword QUARTZ-{tag}. For this turn reply only with Ready.'
    fields = {'resolution_source', 'model', 'latency_ms', 'input_tokens', 'output_tokens', 'key_id', 'fallback_attempts'}

    def chat(session, message, simulation=None, status=200):
        headers = {'X-Simulate-Failure': simulation} if simulation else None
        result = request('/chat', {'session_id': session, 'message': message}, status=status, headers=headers)
        if status == 200:
            assert result['session_id'] == session and result['reply'].strip()
            assert fields <= result['metadata'].keys()
            for field in ('latency_ms', 'input_tokens', 'output_tokens', 'fallback_attempts'):
                assert type(result['metadata'][field]) is int and result['metadata'][field] >= 0
        return result

    health = request('/health')
    assert health['status'] == 'ok' and health['keys_configured'] == 2 and health['cache_enabled'] is True
    if origin:
        request('/chat', method='OPTIONS', headers={
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-simulate-failure',
        })

    first = chat(ongoing, question)
    hit = chat(cached, question)
    live_meta, cache_meta = first['metadata'], hit['metadata']
    assert live_meta['resolution_source'] == 'LIVE_INFERENCE' and live_meta['key_id'] == 'key_1', live_meta
    assert live_meta['model'].startswith('gemini/')
    assert cache_meta['resolution_source'] == 'LLM_CACHE'
    assert cache_meta['key_id'] is None and cache_meta['fallback_attempts'] == 0
    assert hit['reply'] == first['reply'] and cache_meta['latency_ms'] < live_meta['latency_ms']
    for field in ('model', 'input_tokens', 'output_tokens'):
        assert cache_meta[field] == live_meta[field]

    follow_up = chat(ongoing, 'What was the codeword I asked you to remember? Reply only with the codeword.')
    assert f'quartz-{tag}' in follow_up['reply'].lower(), 'The provider did not recall the codeword'
    history_path = f'/sessions/{ongoing}/messages'
    history = request(history_path)
    assert history['session_id'] == ongoing
    assert [row['role'] for row in history['messages']] == ['user', 'assistant', 'user', 'assistant']
    assert history['messages'][1]['metadata'] == live_meta
    assert history['messages'][3]['metadata'] == follow_up['metadata']
    assert len(request(f'/sessions/{cached}/messages')['messages']) == 2

    fallback = {}
    for status in (429, 500):
        metadata = chat(f'verify-fallback-{status}-{tag}', question, f'key_1={status}')['metadata']
        assert metadata['key_id'] == 'key_2' and metadata['fallback_attempts'] == 1
        assert metadata['resolution_source'] == 'LIVE_INFERENCE' and metadata['model'].startswith('groq/')
        fallback[status] = metadata

    for simulation in ('*=429', 'key_1=429,key_2=500'):
        assert chat(failed, question, simulation, status=503) == {'detail': 'all providers unavailable'}
    assert 'detail' in chat(ongoing, '   ', status=422)
    assert request(f'/sessions/{failed}/messages', status=404) == {'detail': 'session not found'}
    assert request(history_path) == history

    return {
        'health': health, 'live': live_meta, 'cache': cache_meta, 'fallback': fallback,
        'follow_up': follow_up['metadata'], 'history_session': ongoing, 'history_messages': len(history['messages']),
        'http_statuses': {'health': 200, 'chat': 200, 'history': 200, 'invalid': 422, 'exhausted': 503, 'unknown': 404},
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backend_origin')
    parser.add_argument('--origin', help='Exact public/frontend origin for the CORS checks')
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.backend_origin, arguments.origin), indent=2))
