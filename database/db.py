"""Gestion SQLite pour logs et statistiques."""
import json
import os
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Iterable

from database.models import Config

# Par défaut, on pointe vers /data pour profiter d'un volume persistant sur Koyeb
# (configurable via DATABASE_PATH si besoin).
DB_PATH = Path(os.getenv('DATABASE_PATH', '/data/bot.db'))
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
                date DATE,
                guild_id TEXT,
                members_total INTEGER,
                members_joined INTEGER,
                members_left INTEGER,
                messages_sent INTEGER,
                commands_used INTEGER,
                UNIQUE(date, guild_id)
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


def record_daily_stats(
    date_value: date,
    guild_id: str,
    members_total: int,
    messages_sent: int = 0,
    commands_used: int = 0,
    members_joined: int = 0,
    members_left: int = 0,
) -> None:
    """Insert or increment daily stats for a guild on a given date."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_stats(date, guild_id, members_total, members_joined, members_left, messages_sent, commands_used)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, guild_id) DO UPDATE SET
                members_total=excluded.members_total,
                members_joined=COALESCE(daily_stats.members_joined, 0) + excluded.members_joined,
                members_left=COALESCE(daily_stats.members_left, 0) + excluded.members_left,
                messages_sent=COALESCE(daily_stats.messages_sent, 0) + excluded.messages_sent,
                commands_used=COALESCE(daily_stats.commands_used, 0) + excluded.commands_used
            """,
            (
                date_value.isoformat(),
                guild_id,
                members_total,
                members_joined,
                members_left,
                messages_sent,
                commands_used,
            ),
        )


def get_chart_data(days: int = 7) -> dict[str, list[dict[str, str | int]]]:
    cutoff = date.today() - timedelta(days=days - 1)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT date, SUM(messages_sent) as messages, SUM(members_joined) as joined, SUM(members_left) as left
            FROM daily_stats
            WHERE date >= ?
            GROUP BY date
            ORDER BY date ASC
            """,
            (cutoff.isoformat(),),
        ).fetchall()
    def _format(row_date: str) -> str:
        return datetime.fromisoformat(row_date).strftime('%d/%m')

    return {
        'messages': [{'label': _format(row['date']), 'value': row['messages'] or 0} for row in rows],
        'members': [
            {
                'label': _format(row['date']),
                'value': max((row['joined'] or 0) - (row['left'] or 0), 0),
            }
            for row in rows
        ],
    }


def get_top_channels(limit: int = 5, days: int = 7) -> list[dict[str, str | int]]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT channel_id, COUNT(*) as message_count
            FROM logs
            WHERE type = 'message' AND timestamp >= ? AND channel_id IS NOT NULL
            GROUP BY channel_id
            ORDER BY message_count DESC
            LIMIT ?
            """,
            (cutoff.isoformat(), limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_top_members(limit: int = 10, days: int = 7) -> list[dict[str, str | int]]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, COALESCE(MAX(user_name), '') as username, COUNT(*) as count
            FROM logs
            WHERE type = 'message' AND timestamp >= ? AND user_id IS NOT NULL
            GROUP BY user_id
            ORDER BY count DESC
            LIMIT ?
            """,
            (cutoff.isoformat(), limit),
        ).fetchall()
    total = sum(row['count'] for row in rows) or 1
    return [
        {
            'user_id': row['user_id'],
            'username': row['username'] or row['user_id'],
            'count': row['count'],
            'percentage': round((row['count'] / total) * 100, 2),
        }
        for row in rows
    ]


def get_top_members_between(start: datetime, end: datetime, limit: int = 10) -> list[dict[str, str | int]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, COALESCE(MAX(user_name), '') as username, COUNT(*) as count
            FROM logs
            WHERE type = 'message' AND timestamp BETWEEN ? AND ? AND user_id IS NOT NULL
            GROUP BY user_id
            ORDER BY count DESC
            LIMIT ?
            """,
            (start.isoformat(), end.isoformat(), limit),
        ).fetchall()
    total = sum(row['count'] for row in rows) or 1
    return [
        {
            'user_id': row['user_id'],
            'username': row['username'] or row['user_id'],
            'count': row['count'],
            'percentage': round((row['count'] / total) * 100, 2),
        }
        for row in rows
    ]


def get_overview() -> dict[str, Any]:
    with get_connection() as conn:
        messages_total = conn.execute('SELECT COALESCE(SUM(messages_sent),0) as total FROM daily_stats').fetchone()['total']
        members_rows = conn.execute(
            'SELECT guild_id, members_total FROM daily_stats WHERE id IN (SELECT MAX(id) FROM daily_stats GROUP BY guild_id)'
        ).fetchall()
        alerts = conn.execute('SELECT COUNT(*) as total FROM logs WHERE level IN ("warning","error")').fetchone()['total']
        timeline = conn.execute('SELECT timestamp, type, message FROM logs ORDER BY timestamp DESC LIMIT 10').fetchall()
        today = date.today().isoformat()
        today_row = conn.execute(
            'SELECT COALESCE(SUM(messages_sent),0) as messages, COALESCE(SUM(members_joined),0) as joined, COALESCE(SUM(members_left),0) as left FROM daily_stats WHERE date = ?',
            (today,),
        ).fetchone()
    return {
        'members_total': sum(row['members_total'] for row in members_rows),
        'messages_total': messages_total,
        'alerts': alerts,
        'alerts_pending': alerts,
        'messages_today': today_row['messages'] if today_row else 0,
        'members_today': (today_row['joined'] - today_row['left']) if today_row else 0,
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


def get_activity_summary(start: datetime, end: datetime) -> dict[str, int]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) as messages, COUNT(DISTINCT user_id) as active_members
            FROM logs
            WHERE type = 'message' AND timestamp BETWEEN ? AND ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchone()
    return {'messages': row['messages'] or 0, 'active_members': row['active_members'] or 0}


def get_member_growth(start_date: date, end_date: date) -> list[dict[str, int | str]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT date, SUM(members_joined) as joined, SUM(members_left) as left
            FROM daily_stats
            WHERE date BETWEEN ? AND ?
            GROUP BY date
            ORDER BY date ASC
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()

    def _format(row_date: str) -> str:
        return datetime.fromisoformat(row_date).strftime('%d/%m')

    return [
        {
            'label': _format(row['date']),
            'joined': row['joined'] or 0,
            'left': row['left'] or 0,
            'net': max((row['joined'] or 0) - (row['left'] or 0), 0),
        }
        for row in rows
    ]


def get_messages_timeseries(start: datetime, end: datetime) -> list[dict[str, int | str]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DATE(timestamp) as bucket, COUNT(*) as messages
            FROM logs
            WHERE type = 'message' AND timestamp BETWEEN ? AND ?
            GROUP BY bucket
            ORDER BY bucket ASC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    return [
        {
            'label': datetime.fromisoformat(row['bucket']).strftime('%d/%m'),
            'value': row['messages'] or 0,
        }
        for row in rows
    ]


def get_top_channels_between(start: datetime, end: datetime, limit: int = 10) -> list[dict[str, str | int]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT channel_id, COUNT(*) as message_count
            FROM logs
            WHERE type = 'message' AND timestamp BETWEEN ? AND ? AND channel_id IS NOT NULL
            GROUP BY channel_id
            ORDER BY message_count DESC
            LIMIT ?
            """,
            (start.isoformat(), end.isoformat(), limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_heatmap_activity(start: datetime, end: datetime) -> list[dict[str, int | str]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT STRFTIME('%w', timestamp) as weekday, STRFTIME('%H', timestamp) as hour, COUNT(*) as count
            FROM logs
            WHERE type = 'message' AND timestamp BETWEEN ? AND ?
            GROUP BY weekday, hour
            ORDER BY weekday, hour
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    return [
        {
            'weekday': int(row['weekday']),
            'hour': int(row['hour']),
            'count': row['count'] or 0,
        }
        for row in rows
    ]
