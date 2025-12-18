"""Supabase-based persistence layer."""
import json
import logging
from datetime import datetime, date, timedelta
from typing import Any, Iterable, Optional

from database.supabase_client import get_supabase, test_connection
from database.models import Config

logger = logging.getLogger(__name__)


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
    client = _ensure_client()
    if not client:
        return
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
    try:
        client.table("logs").insert(payload).execute()
    except Exception as exc:
        logger.error("Erreur log_event: %s", exc)


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
    client = _ensure_client()
    if not client:
        return

    try:
        existing_resp = (
            client.table("daily_stats")
            .select("*")
            .eq("date", date_value.isoformat())
            .eq("guild_id", guild_id)
            .limit(1)
            .execute()
        )
        existing = existing_resp.data[0] if existing_resp.data else {}
        payload = {
            "date": date_value.isoformat(),
            "guild_id": guild_id,
            "members_total": members_total,
            "members_joined": (existing.get("members_joined") or 0) + members_joined,
            "members_left": (existing.get("members_left") or 0) + members_left,
            "messages_sent": (existing.get("messages_sent") or 0) + messages_sent,
            "commands_used": (existing.get("commands_used") or 0) + commands_used,
        }
        client.table("daily_stats").upsert(payload, on_conflict="date,guild_id").execute()
    except Exception as exc:
        logger.error("Erreur record_daily_stats: %s", exc)


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


# SECTION 5 - VOTES

def add_vote_ban(guild_id: str, target_user_id: str, voter_user_id: str, reason: str) -> bool:
    client = _ensure_client()
    if not client:
        return False
    payload = {
        "guild_id": guild_id,
        "target_user_id": target_user_id,
        "voter_user_id": voter_user_id,
        "reason": reason,
    }
    try:
        client.table("vote_bans").insert(payload).execute()
        return True
    except Exception as exc:
        logger.error("Erreur add_vote_ban: %s", exc)
        return False


def get_vote_bans(guild_id: str, target_user_id: str, days: int = 7) -> list[dict[str, Any]]:
    client = _ensure_client()
    if not client:
        return []
    cutoff = datetime.utcnow() - timedelta(days=days)
    try:
        rows = (
            client.table("vote_bans")
            .select("guild_id,target_user_id,voter_user_id,reason,created_at")
            .eq("guild_id", guild_id)
            .eq("target_user_id", target_user_id)
            .gte("created_at", cutoff.isoformat())
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
        return rows
    except Exception as exc:
        logger.error("Erreur get_vote_bans: %s", exc)
        return []


def get_user_daily_votes(guild_id: str, voter_id: str) -> int:
    client = _ensure_client()
    if not client:
        return 0
    try:
        today = date.today().isoformat()
        resp = (
            client.table("vote_bans")
            .select("target_user_id")
            .eq("guild_id", guild_id)
            .eq("voter_user_id", voter_id)
            .gte("created_at", today)
            .execute()
        )
        distinct_targets = {row.get("target_user_id") for row in (resp.data or []) if row.get("target_user_id")}
        return len(distinct_targets)
    except Exception as exc:
        logger.error("Erreur get_user_daily_votes: %s", exc)
        return 0


def clear_vote_bans(guild_id: str, target_user_id: str) -> None:
    client = _ensure_client()
    if not client:
        return
    try:
        client.table("vote_bans").delete().eq("guild_id", guild_id).eq("target_user_id", target_user_id).execute()
    except Exception as exc:
        logger.error("Erreur clear_vote_bans: %s", exc)


def get_last_voteban_sanction(guild_id: str, target_user_id: str) -> Optional[datetime]:
    client = _ensure_client()
    if not client:
        return None
    try:
        resp = (
            client.table("moderation_actions")
            .select("timestamp,action_type,details,guild_id")
            .in_("action_type", ["voteban", "votemute"])
            .execute()
        )
        matches = []
        for row in resp.data or []:
            details = row.get("details") or {}
            target_id = details.get("target_id") if isinstance(details, dict) else None
            if target_id != target_user_id:
                continue
            if row.get("guild_id") not in (None, guild_id):
                continue
            ts = row.get("timestamp")
            if ts:
                matches.append(ts)
        if not matches:
            return None
        return datetime.fromisoformat(sorted(matches, reverse=True)[0])
    except Exception as exc:
        logger.error("Erreur get_last_voteban_sanction: %s", exc)
        return None


def upsert_staff_vote(guild_id: str, target_user_id: str, voter_user_id: str) -> None:
    client = _ensure_client()
    if not client:
        return
    try:
        client.table("staff_votes").upsert(
            {
                "guild_id": guild_id,
                "target_user_id": target_user_id,
                "voter_user_id": voter_user_id,
            },
            on_conflict="guild_id,voter_user_id",
        ).execute()
    except Exception as exc:
        logger.error("Erreur upsert_staff_vote: %s", exc)


def get_staff_vote_for_user(guild_id: str, voter_user_id: str) -> Optional[str]:
    client = _ensure_client()
    if not client:
        return None
    try:
        resp = (
            client.table("staff_votes")
            .select("target_user_id")
            .eq("guild_id", guild_id)
            .eq("voter_user_id", voter_user_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0].get("target_user_id")
        return None
    except Exception as exc:
        logger.error("Erreur get_staff_vote_for_user: %s", exc)
        return None


def get_staff_vote_totals(guild_id: str) -> list[dict[str, Any]]:
    client = _ensure_client()
    if not client:
        return []
    try:
        resp = (
            client.table("staff_votes")
            .select("target_user_id")
            .eq("guild_id", guild_id)
            .execute()
        )
        counts: dict[str, int] = {}
        for row in resp.data or []:
            target = row.get("target_user_id")
            if target:
                counts[target] = counts.get(target, 0) + 1
        sorted_counts = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return [{"target_user_id": target, "total": total} for target, total in sorted_counts]
    except Exception as exc:
        logger.error("Erreur get_staff_vote_totals: %s", exc)
        return []


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


# SECTION 7 - CLEANUP

def cleanup_old_votes(days: int = 30) -> None:
    client = _ensure_client()
    if not client:
        return
    cutoff = datetime.utcnow() - timedelta(days=days)
    try:
        client.table("vote_bans").delete().lt("created_at", cutoff.isoformat()).execute()
    except Exception as exc:
        logger.error("Erreur cleanup_old_votes: %s", exc)


# SECTION 8 - EXPORT

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
