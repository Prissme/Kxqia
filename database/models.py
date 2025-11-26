"""Modèles simples pour typer les réponses API."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Config:
    prefix: str = '!'
    language: str = 'fr'
    timezone: str = 'Europe/Brussels'
    auto_refresh: bool = True
    notifications: bool = True
    page_size: int = 20
    log_level: str = 'INFO'
    retention_days: int = 30
    cleanup: bool = True
    slow_mode: dict[str, Any] = None
    trust_levels: dict[str, str] = None

    @staticmethod
    def default_slow_mode() -> dict[str, Any]:
        return {
            'enabled': True,
            'window_seconds': 60,
            'min_update_interval_seconds': 15,
            'tiers': [
                {'threshold': 60, 'seconds': 10},
                {'threshold': 30, 'seconds': 5},
                {'threshold': 15, 'seconds': 2},
            ],
        }

    @classmethod
    def from_mapping(cls, mapping: Optional[dict[str, Any]] = None) -> "Config":
        mapping = mapping or {}
        slow_mode = mapping.get('slow_mode') or mapping.get('slowMode') or cls.default_slow_mode()
        trust_levels = mapping.get('trust_levels', {}) or mapping.get('trustLevels', {})
        return cls(
            prefix=mapping.get('prefix', cls.prefix),
            language=mapping.get('language', cls.language),
            timezone=mapping.get('timezone', cls.timezone),
            auto_refresh=bool(mapping.get('auto_refresh', cls.auto_refresh)),
            notifications=bool(mapping.get('notifications', cls.notifications)),
            page_size=int(mapping.get('page_size', cls.page_size)),
            log_level=mapping.get('log_level', cls.log_level),
            retention_days=int(mapping.get('retention_days', cls.retention_days)),
            cleanup=bool(mapping.get('cleanup', cls.cleanup)),
            slow_mode=_normalize_slow_mode(slow_mode),
            trust_levels=trust_levels if isinstance(trust_levels, dict) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.__dict__)


def _normalize_slow_mode(data: Any) -> dict[str, Any]:
    """Validate and coerce the slow mode configuration."""

    default = Config.default_slow_mode()
    if not isinstance(data, dict):
        return default

    try:
        enabled = bool(data.get('enabled', default['enabled']))
        window_seconds = int(data.get('window_seconds', default['window_seconds']))
        min_update_interval_seconds = int(
            data.get('min_update_interval_seconds', default['min_update_interval_seconds'])
        )
    except (TypeError, ValueError):
        return default

    tiers = []
    for tier in data.get('tiers', []) or []:
        try:
            threshold = int(tier.get('threshold', 0))
            seconds = int(tier.get('seconds', 0))
        except (TypeError, ValueError):
            continue
        if threshold <= 0 or seconds < 0:
            continue
        tiers.append({'threshold': threshold, 'seconds': seconds})

    if not tiers:
        tiers = default['tiers']

    return {
        'enabled': enabled,
        'window_seconds': max(10, min(window_seconds, 600)),
        'min_update_interval_seconds': max(5, min(min_update_interval_seconds, 600)),
        'tiers': tiers,
    }
