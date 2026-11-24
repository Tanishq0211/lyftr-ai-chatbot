import hashlib
import json
import logging
import os
from dataclasses import dataclass, replace

from .config import Settings

os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')

import litellm
from litellm.caching.in_memory_cache import InMemoryCache

litellm.suppress_debug_info = True
logger = logging.getLogger(__name__)
SIMULATED_STATUSES = {'429', '500', '502', '503'}


class ProvidersUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Answer:
    reply: str
    model: str
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int


def retryable(error: Exception) -> bool:
    status = getattr(error, 'status_code', None)
    if status in (401, 402, 403, 408, 429) or isinstance(status, int) and status >= 500:
        return True
    if isinstance(error, (litellm.APIConnectionError, litellm.Timeout)):
        return True
    # Some providers send quota exhaustion as a 400 or use a provider-specific code.
    description = str(error).lower()
    return any(marker in description for marker in ('quota', 'resource_exhausted', 'insufficient credits'))


class Gateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys = {f'key_{index}': key for index, key in enumerate(settings.keys, start=1)}
        models = settings.models * len(self.keys) if len(settings.models) == 1 else settings.models
        self.models = dict(zip(self.keys, models)) if len(models) == len(self.keys) else {}
        self.cache = InMemoryCache(max_size_in_memory=512, default_ttl=3600)

    @property
    def ready(self) -> bool:
        return len(set(self.keys.values())) >= 2 and bool(self.models)

    def simulation(self, header: str | None) -> dict[str, int]:
        failures = {}
        if self.settings.enable_simulation and header:
            for entry in header.split(','):
                key, _, status = (part.strip() for part in entry.partition('='))
                if (key == '*' or key in self.keys) and status in SIMULATED_STATUSES:
                    failures[key] = int(status)
        return failures

    async def answer(self, messages: list[dict[str, str]], header: str | None) -> Answer:
        if not self.ready:
            raise ProvidersUnavailable

        failures = self.simulation(header)
        request_keys = {}
        if not failures:
            for model in dict.fromkeys(self.models.values()):
                request_key = hashlib.sha256(json.dumps([model, messages], sort_keys=True).encode()).hexdigest()
                hit = self.cache.get_cache(request_key)
                if hit is not None:
                    return hit
                request_keys[model] = request_key

        for attempts, (key_id, api_key) in enumerate(self.keys.items()):
            simulated_status = failures.get(key_id, failures.get('*'))
            if simulated_status:
                logger.info('Simulated provider failure for %s (HTTP %s)', key_id, simulated_status)
                continue
            model = self.models[key_id]
            try:
                response = await litellm.acompletion(
                    model=model, messages=messages, api_key=api_key, api_base=self.settings.api_base,
                    caching=False, num_retries=0, max_retries=0, timeout=20,
                )
            except Exception as error:
                logger.warning('Provider call failed for %s (%s)', key_id, type(error).__name__)
                if retryable(error):
                    continue
                raise ProvidersUnavailable from None

            reply = response.choices[0].message.content if response.choices else None
            usage = getattr(response, 'usage', None)
            if not isinstance(reply, str) or not reply.strip() or usage is None:
                logger.warning('Provider returned an incomplete response for %s', key_id)
                continue
            answer = Answer(reply, model, usage.prompt_tokens, usage.completion_tokens, key_id, attempts)
            if not isinstance(answer.input_tokens, int) or not isinstance(answer.output_tokens, int):
                logger.warning('Provider omitted token usage for %s', key_id)
                continue
            if not failures:
                self.cache.set_cache(request_keys[model], replace(answer, key_id=None, fallback_attempts=0))
            return answer

        raise ProvidersUnavailable
