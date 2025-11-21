"""Modèles simples pour typer les réponses API."""
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

    @classmethod
    def from_mapping(cls, mapping: Optional[dict[str, Any]] = None) -> "Config":
        mapping = mapping or {}
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
        )

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()
