import discord
from database import db

TRUST_LEVELS = {
    'OWNER': 'OWNER',
    'TRUSTED_ADMIN': 'TRUSTED_ADMIN',
    'NORMAL_ADMIN': 'NORMAL_ADMIN',
    'DEFAULT_USER': 'DEFAULT_USER',
}


def get_trust_level(user_id: str, guild: discord.Guild) -> str:
    if guild and str(guild.owner_id) == str(user_id):
        return TRUST_LEVELS['OWNER']
    mapping = db.get_trust_levels()
    return mapping.get(str(user_id), TRUST_LEVELS['DEFAULT_USER'])


def is_trusted(user_id: str, guild: discord.Guild, allow_owner: bool = True) -> bool:
    if guild and str(guild.owner_id) == str(user_id):
        return allow_owner
    level = get_trust_level(user_id, guild)
    return level in {TRUST_LEVELS['OWNER'], TRUST_LEVELS['TRUSTED_ADMIN']}
