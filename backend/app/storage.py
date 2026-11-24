import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class Storage:
    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection:
            connection.execute('PRAGMA journal_mode = WAL')
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    system_prompt TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session_id ON messages (session_id, id);
            ''')

    def check(self):
        with closing(self.connect()) as connection:
            connection.execute('SELECT 1 FROM messages LIMIT 1').fetchone()

    def read(self, session_id: str) -> tuple[str | None, list[dict]]:
        with closing(self.connect()) as connection:
            connection.execute('BEGIN')
            session = connection.execute('SELECT system_prompt FROM sessions WHERE id = ?', (session_id,)).fetchone()
            rows = connection.execute('''
                SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id
            ''', (session_id,)).fetchall()
        messages = []
        for row in rows:
            message = {'role': row['role'], 'content': row['content']}
            if row['metadata'] is not None:
                message['metadata'] = json.loads(row['metadata'])
            messages.append(message)
        return session['system_prompt'] if session else None, messages

    def append_turn(self, session_id: str, prompt: str, message: str, reply: str, metadata: dict):
        timestamp = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as connection, connection:
            connection.execute('''
                INSERT INTO sessions (id, system_prompt) VALUES (?, ?)
                ON CONFLICT (id) DO UPDATE SET system_prompt = excluded.system_prompt
            ''', (session_id, prompt))
            connection.executemany('''
                INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)
            ''', [
                (session_id, 'user', message, None, timestamp),
                (session_id, 'assistant', reply, json.dumps(metadata), timestamp),
            ])
