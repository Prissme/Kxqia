"""Supabase client singleton and helpers."""
import logging
import os
from typing import Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)

_supabase: Optional[Client] = None


def get_supabase() -> Optional[Client]:
    """Return a singleton Supabase client or ``None`` if unavailable."""
    global _supabase

    if _supabase:
        return _supabase

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        logger.error("Supabase credentials are missing (SUPABASE_URL / SUPABASE_KEY)")
        return None

    try:
        _supabase = create_client(url, key)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to initialize Supabase client: %s", exc)
        _supabase = None

    return _supabase


def test_connection() -> bool:
    """Attempt to reach Supabase by performing a lightweight query."""
    client = get_supabase()
    if not client:
        return False

    try:
        client.table("config").select("key").limit(1).execute()
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Supabase connectivity test failed: %s", exc)
        return False
