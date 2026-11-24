import os
from dataclasses import dataclass, field
from pathlib import Path


def csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(',') if item.strip())


@dataclass(frozen=True)
class Settings:
    database: Path
    keys: tuple[str, ...] = field(repr=False)
    models: tuple[str, ...]
    api_base: str | None
    origins: tuple[str, ...]
    enable_simulation: bool

    @classmethod
    def from_env(cls):
        url = os.getenv('DATABASE_URL', 'sqlite:///./data/app.db')
        location = url.removeprefix('sqlite:///')
        if location == url or location in ('', ':memory:'):
            raise ValueError('DATABASE_URL must point to a SQLite file via sqlite:///')
        return cls(
            database=Path(location),
            keys=csv(os.getenv('LLM_API_KEYS', '')),
            models=csv(os.getenv('LLM_MODELS', '')) or csv(os.getenv('LLM_MODEL', 'gemini/gemini-3.5-flash-lite')),
            api_base=os.getenv('LLM_API_BASE', '').strip() or None,
            origins=csv(os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:5173')),
            enable_simulation=os.getenv('ENABLE_FAILURE_SIMULATION', 'false').strip().lower() == 'true',
        )
