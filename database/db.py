"""Gestion SQLite pour logs et statistiques."""
import json
import os
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Any, Iterable

from database.models import Config

DB_PATH = Path(os.getenv('DATABASE_PATH', 'data/bot.db'))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                type TEXT,
                level TEXT,
                message TEXT,
                user_id TEXT,
                user_name TEXT,
                channel_id TEXT,
                guild_id TEXT,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS moderation_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                action_type TEXT,
                channel_id TEXT,
                channel_name TEXT,
                guild_id TEXT,
                user_id TEXT,
                user_name TEXT,
                reason TEXT,
                details TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                guild_id TEXT,
                members_total INTEGER,
                members_joined INTEGER,
                members_left INTEGER,
                messages_sent INTEGER,
                commands_used INTEGER
            );

            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_logs_type ON logs(type);
            CREATE INDEX IF NOT EXISTS idx_moderation_timestamp ON moderation_actions(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date DESC);
            """
        )


def log_event(event_type: str, level: str, message: str, **metadata: Any) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO logs (type, level, message, user_id, user_name, channel_id, guild_id, metadata)
            VALUES (:type, :level, :message, :user_id, :user_name, :channel_id, :guild_id, :metadata)
            """,
            {
                'type': event_type,
                'level': level,
                'message': message,
                'user_id': metadata.get('user_id'),
                'user_name': metadata.get('user_name'),
                'channel_id': metadata.get('channel_id'),
                'guild_id': metadata.get('guild_id'),
                'metadata': json.dumps(metadata, ensure_ascii=False),
            },
        )


def add_moderation_action(action_type: str, channel_id: str, channel_name: str, user_id: str, user_name: str, reason: str, details: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO moderation_actions (action_type, channel_id, channel_name, user_id, user_name, reason, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (action_type, channel_id, channel_name, user_id, user_name, reason, json.dumps(details, ensure_ascii=False)),
        )


def save_config(config: Config) -> None:
    with get_connection() as conn:
        for key, value in config.to_dict().items():
            conn.execute(
                """
                INSERT INTO config(key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, json.dumps(value) if isinstance(value, (dict, list)) else str(value)),
            )


def load_config() -> Config:
    with get_connection() as conn:
        rows = conn.execute('SELECT key, value FROM config').fetchall()
    mapping = {row['key']: _decode(row['value']) for row in rows}
    return Config.from_mapping(mapping)


def _decode(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def record_daily_stats(date_value: date, guild_id: str, members_total: int, messages_sent: int, commands_used: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_stats(date, guild_id, members_total, members_joined, members_left, messages_sent, commands_used)
            VALUES (?, ?, ?, 0, 0, ?, ?)
            ON CONFLICT(date) DO UPDATE SET members_total=excluded.members_total, messages_sent=excluded.messages_sent, commands_used=excluded.commands_used
            """,
            (date_value.isoformat(), guild_id, members_total, messages_sent, commands_used),
        )


def get_overview() -> dict[str, Any]:
    with get_connection() as conn:
        messages_total = conn.execute('SELECT COALESCE(SUM(messages_sent),0) as total FROM daily_stats').fetchone()['total']
        members_total = conn.execute('SELECT members_total FROM daily_stats ORDER BY date DESC LIMIT 1').fetchone()
        alerts = conn.execute('SELECT COUNT(*) as total FROM logs WHERE level IN ("warning","error")').fetchone()['total']
        timeline = conn.execute('SELECT timestamp, type, message FROM logs ORDER BY timestamp DESC LIMIT 10').fetchall()
    return {
        'members_total': members_total['members_total'] if members_total else 0,
        'messages_total': messages_total,
        'alerts': alerts,
        'alerts_pending': alerts,
        'timeline': [{'timestamp': row['timestamp'], 'message': row['message'], 'type': row['type']} for row in timeline],
    }


def get_logs(filters: dict[str, Any]) -> dict[str, Any]:
    params: list[Any] = []
    clauses: list[str] = []
    if filters.get('type') and filters['type'] != 'all':
        clauses.append('type = ?')
        params.append(filters['type'])
    if filters.get('search'):
        clauses.append('message LIKE ?')
        params.append(f"%{filters['search']}%")
    if filters.get('start'):
        clauses.append('timestamp >= ?')
        params.append(filters['start'])
    if filters.get('end'):
        clauses.append('timestamp <= ?')
        params.append(filters['end'])
    query = 'SELECT timestamp, type, level, message, user_name FROM logs'
    if clauses:
        query += ' WHERE ' + ' AND '.join(clauses)
    query += ' ORDER BY timestamp DESC LIMIT 100'
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        stats_row = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN level='error' THEN 1 ELSE 0 END) as errors,
                SUM(CASE WHEN level='warning' THEN 1 ELSE 0 END) as warnings,
                SUM(CASE WHEN type='moderation' THEN 1 ELSE 0 END) as moderation,
                SUM(CASE WHEN type='analytics' THEN 1 ELSE 0 END) as analytics
            FROM logs
            """
        ).fetchone()
    return {
        'logs': [dict(row) for row in rows],
        'stats': dict(stats_row) if stats_row else {},
    }


def get_moderation_history(filters: dict[str, Any]) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.get('type') and filters['type'] != 'all':
        clauses.append('action_type = ?')
        params.append(filters['type'])
    if filters.get('date'):
        clauses.append('DATE(timestamp) = ?')
        params.append(filters['date'])
    query = 'SELECT timestamp, action_type, channel_name, user_name, details FROM moderation_actions'
    if clauses:
        query += ' WHERE ' + ' AND '.join(clauses)
    query += ' ORDER BY timestamp DESC LIMIT 50'
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return {'actions': [dict(row) for row in rows]}


def export_table(table: str) -> Iterable[sqlite3.Row]:
    with get_connection() as conn:
        yield from conn.execute(f'SELECT * FROM {table}')
