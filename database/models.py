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
    raid: dict[str, Any] = None
    nuke: dict[str, Any] = None

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
        raid = mapping.get('raid') or cls.default_raid()
        nuke = mapping.get('nuke') or cls.default_nuke()
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
            raid=_normalize_raid(raid),
            nuke=_normalize_nuke(nuke),
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.__dict__)

    @staticmethod
    def default_raid() -> dict[str, Any]:
        return {
            'joinThreshold': 10,
            'accountAgeDays': 7,
            'lockdownOnRaid': True,
            'kickYoungAccounts': False,
            'quarantineRoleId': '',
        }

    @staticmethod
    def default_nuke() -> dict[str, Any]:
        return {
            'timeWindow': 30,
            'channelDeleteLimit': 3,
            'roleDeleteLimit': 5,
            'banLimit': 10,
            'webhookCreateLimit': 3,
            'punitiveAction': 'strip',
            'allowOwner': True,
        }


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


def _normalize_raid(data: Any) -> dict[str, Any]:
    default = Config.default_raid()
    if not isinstance(data, dict):
        return default
    def _to_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
    return {
        'joinThreshold': max(2, _to_int(data.get('joinThreshold'), default['joinThreshold'])),
        'accountAgeDays': max(1, _to_int(data.get('accountAgeDays'), default['accountAgeDays'])),
        'lockdownOnRaid': bool(data.get('lockdownOnRaid', default['lockdownOnRaid'])),
        'kickYoungAccounts': bool(data.get('kickYoungAccounts', default['kickYoungAccounts'])),
        'quarantineRoleId': str(data.get('quarantineRoleId', default['quarantineRoleId']) or ''),
    }


def _normalize_nuke(data: Any) -> dict[str, Any]:
    default = Config.default_nuke()
    if not isinstance(data, dict):
        return default
    def _to_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
    punitive_action = str(data.get('punitiveAction', default['punitiveAction'])).lower()
    if punitive_action not in {'strip', 'ban'}:
        punitive_action = default['punitiveAction']
    return {
        'timeWindow': max(5, _to_int(data.get('timeWindow'), default['timeWindow'])),
        'channelDeleteLimit': max(1, _to_int(data.get('channelDeleteLimit'), default['channelDeleteLimit'])),
        'roleDeleteLimit': max(1, _to_int(data.get('roleDeleteLimit'), default['roleDeleteLimit'])),
        'banLimit': max(1, _to_int(data.get('banLimit'), default['banLimit'])),
        'webhookCreateLimit': max(1, _to_int(data.get('webhookCreateLimit'), default['webhookCreateLimit'])),
        'punitiveAction': punitive_action,
        'allowOwner': bool(data.get('allowOwner', default['allowOwner'])),
    }
