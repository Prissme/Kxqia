"""Supabase-based persistence layer with in-memory batching."""
import asyncio
import json
import logging
import os
import threading
from collections import defaultdict, deque
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

from database.supabase_client import get_supabase, test_connection
from database.models import Config

logger = logging.getLogger(__name__)


class BatchLogger:
    """Accumulate logs in memory and flush in bulk to Supabase."""

    def __init__(self, batch_size: int = 100) -> None:
        self.batch_size = batch_size
        self.queue: deque[dict[str, Any]] = deque()
        self._lock = asyncio.Lock()
        self.total_enqueued = 0
        self.total_flushed = 0
        self.failed_flushes = 0

    async def log(self, payload: dict[str, Any]) -> None:
        """Queue a log payload and trigger flush if needed."""

        async with self._lock:
            self.queue.append(payload)
            self.total_enqueued += 1
            if len(self.queue) >= self.batch_size:
                await self._flush_locked()

    def log_nowait(self, payload: dict[str, Any]) -> None:
        """Non-blocking enqueue from sync or async contexts."""

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.log(payload))
        except RuntimeError:
            asyncio.run(self.log(payload))

    async def flush(self) -> int:
        """Flush queued logs as a bulk insert."""

        async with self._lock:
            return await self._flush_locked()

    async def _flush_locked(self) -> int:
        if not self.queue:
            return 0
        batch = list(self.queue)
        self.queue.clear()
        try:
            inserted = bulk_insert_logs(batch)
            self.total_flushed += inserted
            return inserted
        except Exception as exc:  # pragma: no cover - defensive
            self.failed_flushes += 1
            logger.error("Erreur lors du flush des logs: %s", exc)
            # ré-insère les logs pour éviter la perte de données
            self.queue.extendleft(reversed(batch))
            return 0


class StatsCache:
    """In-memory aggregator for daily stats before batch upsert."""

    def __init__(self) -> None:
        self.cache: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.members_total: dict[tuple[str, str], int] = {}
        self._lock = asyncio.Lock()
        self.flush_count = 0

    def increment(
        self,
        *,
        date_value: date,
        guild_id: str,
        members_total: int,
        messages_sent: int = 0,
        commands_used: int = 0,
        members_joined: int = 0,
        members_left: int = 0,
    ) -> None:
        key = (date_value.isoformat(), guild_id)
        self.members_total[key] = members_total
        bucket = self.cache[key]
        bucket["messages_sent"] += messages_sent
        bucket["commands_used"] += commands_used
        bucket["members_joined"] += members_joined
        bucket["members_left"] += members_left

    async def flush(self) -> int:
        async with self._lock:
            if not self.cache:
                return 0
            payload = []
            for (date_str, guild_id), counters in self.cache.items():
                payload.append(
                    {
                        "date": date_str,
                        "guild_id": guild_id,
                        "members_total": self.members_total.get((date_str, guild_id), 0),
                        "members_joined": counters.get("members_joined", 0),
                        "members_left": counters.get("members_left", 0),
                        "messages_sent": counters.get("messages_sent", 0),
                        "commands_used": counters.get("commands_used", 0),
                    }
                )

            try:
                client = _ensure_client()
                if not client:
                    return 0
                client.table("daily_stats").upsert(payload, on_conflict="date,guild_id").execute()
                self.flush_count += 1
                return len(payload)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Erreur lors du flush des stats: %s", exc)
                return 0


BATCH_SIZE = int(os.getenv("BATCH_SIZE", "200"))
batch_logger = BatchLogger(batch_size=BATCH_SIZE)
stats_cache = StatsCache()


def init_db() -> None:
    """Initialize connectivity to Supabase."""
    if not test_connection():
        logger.warning("Supabase connection could not be verified at startup")


def _ensure_client():
    client = get_supabase()
    if not client:
        logger.warning("Supabase indisponible")
    return client


# SECTION 1 - LOGS

def log_event(event_type: str, level: str, message: str, **metadata: Any) -> None:
    payload = {
        "type": event_type,
        "level": level,
        "message": message,
        "user_id": metadata.get("user_id"),
        "user_name": metadata.get("user_name"),
        "channel_id": metadata.get("channel_id"),
        "guild_id": metadata.get("guild_id"),
        "metadata": metadata or {},
    }
    batch_logger.log_nowait(payload)


def get_logs(filters: dict[str, Any]) -> dict[str, Any]:
    client = _ensure_client()
    if not client:
        return {"logs": [], "stats": {}}

    query = client.table("logs").select("timestamp,type,level,message,user_name")
    if filters.get("type") and filters["type"] != "all":
        query = query.eq("type", filters["type"])
    if filters.get("search"):
        query = query.ilike("message", f"%{filters['search']}%")
    if filters.get("start"):
        query = query.gte("timestamp", filters["start"])
    if filters.get("end"):
        query = query.lte("timestamp", filters["end"])

    try:
        rows = query.order("timestamp", desc=True).limit(100).execute().data or []
        stats = {
            "total": _count_logs(client),
            "errors": _count_logs(client, level="error"),
            "warnings": _count_logs(client, level="warning"),
            "moderation": _count_logs(client, type_filter="moderation"),
            "analytics": _count_logs(client, type_filter="analytics"),
        }
        return {"logs": rows, "stats": stats}
    except Exception as exc:
        logger.error("Erreur get_logs: %s", exc)
        return {"logs": [], "stats": {}}


def _count_logs(client, level: Optional[str] = None, type_filter: Optional[str] = None) -> int:
    query = client.table("logs").select("id", count="exact")
    if level:
        query = query.eq("level", level)
    if type_filter:
        query = query.eq("type", type_filter)
    try:
        resp = query.execute()
        return resp.count or 0
    except Exception as exc:
        logger.error("Erreur _count_logs: %s", exc)
        return 0


def bulk_insert_logs(payloads: list[dict[str, Any]]) -> int:
    """Insert a batch of logs in a single Supabase call."""

    if not payloads:
        return 0
    client = _ensure_client()
    if not client:
        return 0
    response = client.table("logs").insert(payloads).execute()
    return len(response.data or payloads)


# SECTION 2 - MODERATION

def add_moderation_action(
    action_type: str,
    channel_id: str,
    channel_name: str,
    user_id: str,
    user_name: str,
    reason: str,
    details: dict[str, Any],
) -> None:
    client = _ensure_client()
    if not client:
        return

    payload = {
        "action_type": action_type,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "user_id": user_id,
        "user_name": user_name,
        "reason": reason,
        "details": details,
    }
    try:
        client.table("moderation_actions").insert(payload).execute()
    except Exception as exc:
        logger.error("Erreur add_moderation_action: %s", exc)


def get_moderation_history(filters: dict[str, Any]) -> dict[str, Any]:
    client = _ensure_client()
    if not client:
        return {"actions": []}

    query = client.table("moderation_actions").select("*")
    if filters.get("type") and filters["type"] != "all":
        query = query.eq("action_type", filters["type"])
    if filters.get("start"):
        query = query.gte("timestamp", filters["start"])
    if filters.get("end"):
        query = query.lte("timestamp", filters["end"])

    try:
        actions = query.order("timestamp", desc=True).limit(200).execute().data or []
        return {"actions": actions}
    except Exception as exc:
        logger.error("Erreur get_moderation_history: %s", exc)
        return {"actions": []}


# SECTION 3 - STATS

def record_daily_stats(
    date_value: date,
    guild_id: str,
    members_total: int,
    messages_sent: int = 0,
    commands_used: int = 0,
    members_joined: int = 0,
    members_left: int = 0,
) -> None:
    stats_cache.increment(
        date_value=date_value,
        guild_id=guild_id,
        members_total=members_total,
        messages_sent=messages_sent,
        commands_used=commands_used,
        members_joined=members_joined,
        members_left=members_left,
    )


def get_chart_data(days: int = 7) -> dict[str, list[dict[str, str | int]]]:
    client = _ensure_client()
    if not client:
        return {"messages": [], "members": []}

    cutoff = date.today() - timedelta(days=days - 1)
    try:
        rows = (
            client.table("daily_stats")
            .select("date,messages_sent,members_joined,members_left")
            .gte("date", cutoff.isoformat())
            .order("date")
            .execute()
            .data
            or []
        )

        def _format(label: str) -> str:
            return datetime.fromisoformat(label).strftime("%d/%m")

        return {
            "messages": [{"label": _format(row["date"]), "value": row.get("messages_sent", 0) or 0} for row in rows],
            "members": [
                {
                    "label": _format(row["date"]),
                    "value": max((row.get("members_joined", 0) or 0) - (row.get("members_left", 0) or 0), 0),
                }
                for row in rows
            ],
        }
    except Exception as exc:
        logger.error("Erreur get_chart_data: %s", exc)
        return {"messages": [], "members": []}


def get_overview() -> dict[str, Any]:
    client = _ensure_client()
    if not client:
        return {}

    try:
        stats_resp = client.table("daily_stats").select("*").order("date", desc=True).execute()
        stats_rows = stats_resp.data or []
        messages_total = sum(row.get("messages_sent") or 0 for row in stats_rows)
        latest_per_guild = {}
        for row in stats_rows:
            if row.get("guild_id") not in latest_per_guild:
                latest_per_guild[row.get("guild_id")] = row
        members_total = sum(row.get("members_total") or 0 for row in latest_per_guild.values())

        alerts = _count_logs(client, level="warning") + _count_logs(client, level="error")
        timeline = (
            client.table("logs")
            .select("timestamp,type,message")
            .order("timestamp", desc=True)
            .limit(10)
            .execute()
            .data
            or []
        )
        today = date.today().isoformat()
        today_rows = (
            client.table("daily_stats")
            .select("messages_sent,members_joined,members_left")
            .eq("date", today)
            .execute()
            .data
            or []
        )
        messages_today = sum(row.get("messages_sent") or 0 for row in today_rows)
        members_today = sum((row.get("members_joined") or 0) - (row.get("members_left") or 0) for row in today_rows)

        return {
            "members_total": members_total,
            "messages_total": messages_total,
            "alerts": alerts,
            "alerts_pending": alerts,
            "messages_today": messages_today,
            "members_today": members_today,
            "timeline": timeline,
        }
    except Exception as exc:
        logger.error("Erreur get_overview: %s", exc)
        return {}


def get_top_channels(limit: int = 5, days: int = 7) -> list[dict[str, str | int]]:
    client = _ensure_client()
    if not client:
        return []
    cutoff = datetime.utcnow() - timedelta(days=days)
    try:
        rows = (
            client.table("logs")
            .select("channel_id,timestamp")
            .eq("type", "message")
            .gte("timestamp", cutoff.isoformat())
            .execute()
            .data
            or []
        )
        counts: dict[str, int] = {}
        for row in rows:
            channel = row.get("channel_id")
            if channel:
                counts[channel] = counts.get(channel, 0) + 1
        sorted_counts = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [{"channel_id": cid, "message_count": total} for cid, total in sorted_counts]
    except Exception as exc:
        logger.error("Erreur get_top_channels: %s", exc)
        return []


def get_top_members(limit: int = 10, days: int = 7) -> list[dict[str, str | int]]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    return get_top_members_between(cutoff, datetime.utcnow(), limit)


def get_top_members_between(start: datetime, end: datetime, limit: int = 10) -> list[dict[str, str | int]]:
    client = _ensure_client()
    if not client:
        return []
    try:
        rows = (
            client.table("logs")
            .select("user_id,user_name,timestamp")
            .eq("type", "message")
            .gte("timestamp", start.isoformat())
            .lte("timestamp", end.isoformat())
            .execute()
            .data
            or []
        )
        counts: dict[str, dict[str, Any]] = {}
        for row in rows:
            user_id = row.get("user_id")
            if not user_id:
                continue
            entry = counts.setdefault(user_id, {"count": 0, "username": row.get("user_name") or user_id})
            entry["count"] += 1
            if row.get("user_name"):
                entry["username"] = row["user_name"]
        sorted_counts = sorted(counts.items(), key=lambda item: item[1]["count"], reverse=True)[:limit]
        total = sum(item[1]["count"] for item in sorted_counts) or 1
        return [
            {
                "user_id": user_id,
                "username": data["username"],
                "count": data["count"],
                "percentage": round((data["count"] / total) * 100, 2),
            }
            for user_id, data in sorted_counts
        ]
    except Exception as exc:
        logger.error("Erreur get_top_members_between: %s", exc)
        return []


def get_activity_summary(start: datetime, end: datetime) -> dict[str, int]:
    client = _ensure_client()
    if not client:
        return {"messages": 0, "active_members": 0}

    try:
        rows = (
            client.table("logs")
            .select("user_id,timestamp")
            .eq("type", "message")
            .gte("timestamp", start.isoformat())
            .lte("timestamp", end.isoformat())
            .execute()
            .data
            or []
        )
        messages = len(rows)
        active_members = len({row.get("user_id") for row in rows if row.get("user_id")})
        return {"messages": messages, "active_members": active_members}
    except Exception as exc:
        logger.error("Erreur get_activity_summary: %s", exc)
        return {"messages": 0, "active_members": 0}


def get_member_growth(start_date: date, end_date: date) -> list[dict[str, int | str]]:
    client = _ensure_client()
    if not client:
        return []
    try:
        rows = (
            client.table("daily_stats")
            .select("date,members_joined,members_left")
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .order("date")
            .execute()
            .data
            or []
        )

        def _format(label: str) -> str:
            return datetime.fromisoformat(label).strftime("%d/%m")

        return [
            {
                "label": _format(row["date"]),
                "joined": row.get("members_joined", 0) or 0,
                "left": row.get("members_left", 0) or 0,
                "net": max((row.get("members_joined", 0) or 0) - (row.get("members_left", 0) or 0), 0),
            }
            for row in rows
        ]
    except Exception as exc:
        logger.error("Erreur get_member_growth: %s", exc)
        return []


def get_messages_timeseries(start: datetime, end: datetime) -> list[dict[str, int | str]]:
    client = _ensure_client()
    if not client:
        return []

    try:
        rows = (
            client.table("logs")
            .select("timestamp")
            .eq("type", "message")
            .gte("timestamp", start.isoformat())
            .lte("timestamp", end.isoformat())
            .order("timestamp")
            .execute()
            .data
            or []
        )
        buckets: dict[str, int] = {}
        for row in rows:
            bucket = row.get("timestamp")
            if bucket:
                date_key = bucket.split("T", 1)[0]
                buckets[date_key] = buckets.get(date_key, 0) + 1
        return [
            {"label": datetime.fromisoformat(day).strftime("%d/%m"), "value": count}
            for day, count in sorted(buckets.items())
        ]
    except Exception as exc:
        logger.error("Erreur get_messages_timeseries: %s", exc)
        return []


def get_top_channels_between(start: datetime, end: datetime, limit: int = 10) -> list[dict[str, str | int]]:
    client = _ensure_client()
    if not client:
        return []
    try:
        rows = (
            client.table("logs")
            .select("channel_id,timestamp")
            .eq("type", "message")
            .gte("timestamp", start.isoformat())
            .lte("timestamp", end.isoformat())
            .execute()
            .data
            or []
        )
        counts: dict[str, int] = {}
        for row in rows:
            channel = row.get("channel_id")
            if channel:
                counts[channel] = counts.get(channel, 0) + 1
        sorted_counts = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [{"channel_id": cid, "message_count": total} for cid, total in sorted_counts]
    except Exception as exc:
        logger.error("Erreur get_top_channels_between: %s", exc)
        return []


def get_heatmap_activity(start: datetime, end: datetime) -> list[dict[str, int | str]]:
    client = _ensure_client()
    if not client:
        return []
    try:
        rows = (
            client.table("logs")
            .select("timestamp")
            .eq("type", "message")
            .gte("timestamp", start.isoformat())
            .lte("timestamp", end.isoformat())
            .execute()
            .data
            or []
        )
        heatmap: dict[tuple[int, int], int] = {}
        for row in rows:
            ts = row.get("timestamp")
            if not ts:
                continue
            dt = datetime.fromisoformat(ts)
            key = (dt.weekday(), dt.hour)
            heatmap[key] = heatmap.get(key, 0) + 1
        return [
            {"weekday": k[0], "hour": k[1], "count": v}
            for k, v in sorted(heatmap.items())
        ]
    except Exception as exc:
        logger.error("Erreur get_heatmap_activity: %s", exc)
        return []


# SECTION 4 - CONFIG

def load_config() -> Config:
    client = _ensure_client()
    if not client:
        return Config()
    try:
        rows = client.table("config").select("key,value").execute().data or []
        mapping = {}
        for row in rows:
            value = row.get("value")
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except Exception:
                    pass
            mapping[row.get("key")] = value
        return Config.from_mapping(mapping)
    except Exception as exc:
        logger.error("Erreur load_config: %s", exc)
        return Config()


def save_config(config: Config) -> None:
    client = _ensure_client()
    if not client:
        return
    payload = []
    for key, value in config.to_dict().items():
        payload.append({"key": key, "value": value})
    try:
        client.table("config").upsert(payload, on_conflict="key").execute()
    except Exception as exc:
        logger.error("Erreur save_config: %s", exc)


async def flush_all() -> None:
    """Flush batched logs and stats for a graceful shutdown."""

    await asyncio.gather(batch_logger.flush(), stats_cache.flush())


def get_trust_levels() -> dict[str, str]:
    config = load_config()
    return config.to_dict().get("trust_levels", {}) or {}


def set_trust_level(user_id: str, level: str) -> None:
    config = load_config()
    data = config.to_dict()
    data.setdefault("trust_levels", {})[user_id] = level
    save_config(Config.from_mapping(data))


def remove_trust_level(user_id: str) -> None:
    config = load_config()
    data = config.to_dict()
    if "trust_levels" in data and user_id in data["trust_levels"]:
        del data["trust_levels"][user_id]
        save_config(Config.from_mapping(data))


# SECTION 5 - CREDITS
_LOCAL_CREDITS_PATH = Path(__file__).with_name("local_credits.json")
_LOCAL_CREDITS_LOCK = threading.Lock()


def _load_local_credits() -> dict[str, Any]:
    if not _LOCAL_CREDITS_PATH.exists():
        return {"credits": {}, "history": {}}
    try:
        with _LOCAL_CREDITS_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Erreur lecture credits locaux: %s", exc)
        return {"credits": {}, "history": {}}
    data.setdefault("credits", {})
    data.setdefault("history", {})
    return data


def _save_local_credits(data: dict[str, Any]) -> None:
    try:
        with _LOCAL_CREDITS_PATH.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.error("Erreur sauvegarde credits locaux: %s", exc)


def _get_local_credits(guild_id: str, user_id: str) -> int:
    with _LOCAL_CREDITS_LOCK:
        data = _load_local_credits()
        return int(data.get("credits", {}).get(guild_id, {}).get(user_id, 0))


def _set_local_credits(guild_id: str, user_id: str, credits: int) -> int:
    with _LOCAL_CREDITS_LOCK:
        data = _load_local_credits()
        data.setdefault("credits", {}).setdefault(guild_id, {})[user_id] = int(credits)
        _save_local_credits(data)
    return int(credits)


def _append_local_credit_history(
    *,
    guild_id: str,
    user_id: str,
    entry: dict[str, Any],
) -> None:
    with _LOCAL_CREDITS_LOCK:
        data = _load_local_credits()
        history = data.setdefault("history", {}).setdefault(guild_id, {}).setdefault(user_id, [])
        history.append(entry)
        _save_local_credits(data)


def _get_local_credit_history(guild_id: str, user_id: str, limit: int) -> list[dict[str, Any]]:
    with _LOCAL_CREDITS_LOCK:
        data = _load_local_credits()
        history = data.get("history", {}).get(guild_id, {}).get(user_id, [])
        return list(reversed(history))[:limit]

def get_user_credits(guild_id: str, user_id: str) -> int:
    client = _ensure_client()
    if not client:
        return _get_local_credits(guild_id, user_id)
    try:
        resp = (
            client.table("user_credits")
            .select("credits")
            .eq("guild_id", guild_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            return int(resp.data[0].get("credits") or 0)
        return 0
    except Exception as exc:
        logger.error("Erreur get_user_credits: %s", exc)
        return _get_local_credits(guild_id, user_id)


def set_user_credits(guild_id: str, user_id: str, credits: int) -> int:
    client = _ensure_client()
    if not client:
        return _set_local_credits(guild_id, user_id, credits)
    payload = {
        "guild_id": guild_id,
        "user_id": user_id,
        "credits": int(credits),
    }
    try:
        client.table("user_credits").upsert(payload, on_conflict="guild_id,user_id").execute()
    except Exception as exc:
        logger.error("Erreur set_user_credits: %s", exc)
        return _set_local_credits(guild_id, user_id, credits)
    return int(credits)


def increment_user_credits(guild_id: str, user_id: str, delta: int) -> int:
    current = get_user_credits(guild_id, user_id)
    next_value = max(0, current + int(delta))
    return set_user_credits(guild_id, user_id, next_value)


def record_credit_change(
    *,
    guild_id: str,
    user_id: str,
    user_name: str,
    delta: int,
    total: int,
    reason: str,
    actor_id: str,
    actor_name: str,
) -> None:
    payload = {
        "type": "credit",
        "level": "info",
        "message": f"Crédits {delta:+d} (total {total})",
        "user_id": user_id,
        "user_name": user_name,
        "guild_id": guild_id,
        "metadata": {
            "delta": int(delta),
            "total": int(total),
            "reason": reason,
            "actor_id": actor_id,
            "actor_name": actor_name,
        },
    }
    client = _ensure_client()
    if not client:
        _append_local_credit_history(
            guild_id=guild_id,
            user_id=user_id,
            entry={
                "timestamp": datetime.utcnow().isoformat(),
                **payload["metadata"],
                "user_name": user_name,
            },
        )
        return
    try:
        client.table("logs").insert(payload).execute()
    except Exception as exc:
        logger.error("Erreur record_credit_change: %s", exc)
        _append_local_credit_history(
            guild_id=guild_id,
            user_id=user_id,
            entry={
                "timestamp": datetime.utcnow().isoformat(),
                **payload["metadata"],
                "user_name": user_name,
            },
        )


def get_credit_history(guild_id: str, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    client = _ensure_client()
    if not client:
        return _get_local_credit_history(guild_id, user_id, limit)
    try:
        resp = (
            client.table("logs")
            .select("timestamp,metadata")
            .eq("type", "credit")
            .eq("guild_id", guild_id)
            .eq("user_id", user_id)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        results = []
        for row in resp.data or []:
            metadata = row.get("metadata") or {}
            results.append(
                {
                    "timestamp": row.get("timestamp"),
                    "delta": metadata.get("delta"),
                    "total": metadata.get("total"),
                    "reason": metadata.get("reason"),
                    "actor_id": metadata.get("actor_id"),
                    "actor_name": metadata.get("actor_name"),
                }
            )
        return results
    except Exception as exc:
        logger.error("Erreur get_credit_history: %s", exc)
        return _get_local_credit_history(guild_id, user_id, limit)


def get_top_credits(guild_id: str, user_ids: Iterable[str], limit: int = 10) -> list[dict[str, Any]]:
    ids = [str(user_id) for user_id in user_ids if user_id]
    if not ids:
        return []
    client = _ensure_client()
    if not client:
        with _LOCAL_CREDITS_LOCK:
            data = _load_local_credits()
        credits_map = data.get("credits", {}).get(guild_id, {})
        results = [
            {"user_id": user_id, "credits": int(credits_map.get(user_id, 0))}
            for user_id in ids
        ]
        results.sort(key=lambda entry: entry["credits"], reverse=True)
        return results[:limit]
    try:
        resp = (
            client.table("user_credits")
            .select("user_id,credits")
            .eq("guild_id", guild_id)
            .in_("user_id", ids)
            .order("credits", desc=True)
            .limit(limit)
            .execute()
        )
        return [
            {"user_id": row.get("user_id"), "credits": int(row.get("credits") or 0)}
            for row in resp.data or []
        ]
    except Exception as exc:
        logger.error("Erreur get_top_credits: %s", exc)
        with _LOCAL_CREDITS_LOCK:
            data = _load_local_credits()
        credits_map = data.get("credits", {}).get(guild_id, {})
        results = [
            {"user_id": user_id, "credits": int(credits_map.get(user_id, 0))}
            for user_id in ids
        ]
        results.sort(key=lambda entry: entry["credits"], reverse=True)
        return results[:limit]


# SECTION 6 - MESSAGES

def count_user_messages(user_id: str, guild_id: Optional[str] = None) -> int:
    client = _ensure_client()
    if not client:
        return 0
    try:
        query = (
            client.table("logs")
            .select("id", count="exact")
            .eq("type", "message")
            .eq("user_id", user_id)
        )
        if guild_id:
            query = query.eq("guild_id", guild_id)
        resp = query.execute()
        return resp.count or 0
    except Exception as exc:
        logger.error("Erreur count_user_messages: %s", exc)
        return 0


# SECTION 7 - EXPORT

def export_table(table: str) -> Iterable[dict]:
    client = _ensure_client()
    if not client:
        return []
    try:
        resp = client.table(table).select("*").execute()
        return resp.data or []
    except Exception as exc:
        logger.error("Erreur export_table: %s", exc)
        return []
