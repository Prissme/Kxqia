"""Gestion des rôles de niveau XP."""
from __future__ import annotations

import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)

# Paliers : niveau → nom du rôle
LEVEL_ROLES: dict[int, str] = {
    1: "Niveau 1",
    5: "Niveau 5",
    10: "Niveau 10",
    15: "Niveau 15",
    20: "Niveau 20",
    30: "Niveau 30",
    50: "Niveau 50",
}

# Ordre croissant des paliers
LEVEL_THRESHOLDS: list[int] = sorted(LEVEL_ROLES.keys())


def _get_role_for_level(level: int) -> Optional[str]:
    """Retourne le nom du rôle correspondant au palier atteint ou None."""
    earned: Optional[str] = None
    for threshold in LEVEL_THRESHOLDS:
        if level >= threshold:
            earned = LEVEL_ROLES[threshold]
    return earned


async def ensure_level_roles_exist(guild: discord.Guild) -> dict[int, discord.Role]:
    """Crée les rôles de niveau s'ils n'existent pas et retourne un mapping niveau→rôle."""
    existing = {role.name: role for role in guild.roles}
    level_role_map: dict[int, discord.Role] = {}

    for threshold, role_name in LEVEL_ROLES.items():
        if role_name in existing:
            level_role_map[threshold] = existing[role_name]
        else:
            try:
                new_role = await guild.create_role(
                    name=role_name,
                    reason="Création automatique des rôles de niveau XP",
                    mentionable=False,
                    hoist=False,
                )
                level_role_map[threshold] = new_role
                logger.info("Rôle de niveau créé : %s", role_name)
            except discord.Forbidden:
                logger.warning("Permission manquante pour créer le rôle %s", role_name)
            except discord.HTTPException:
                logger.exception("Erreur lors de la création du rôle %s", role_name)

    return level_role_map


def _highest_earned_threshold(level: int) -> Optional[int]:
    """Retourne le palier le plus élevé atteint pour un niveau donné."""
    earned: Optional[int] = None
    for threshold in LEVEL_THRESHOLDS:
        if level >= threshold:
            earned = threshold
    return earned


async def sync_level_roles(
    member: discord.Member,
    new_level: int,
    old_level: int,
) -> Optional[discord.Role]:
    """
    Met à jour les rôles de niveau du membre :
    - Retire les rôles des paliers non atteints ou dépassés (on garde uniquement le palier actuel)
    - Ajoute le rôle du palier actuel si nécessaire
    Retourne le rôle nouvellement attribué si un level-up a déclenché un changement, sinon None.
    """
    guild = member.guild
    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        logger.warning("Permission Manage Roles manquante pour synchroniser les rôles de niveau.")
        return None

    # Construire le mapping des rôles existants
    role_map: dict[int, discord.Role] = {}
    for threshold, role_name in LEVEL_ROLES.items():
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            # Tenter de créer le rôle manquant à la volée
            try:
                role = await guild.create_role(
                    name=role_name,
                    reason="Création automatique rôle niveau XP",
                )
                logger.info("Rôle créé à la volée : %s", role_name)
            except (discord.Forbidden, discord.HTTPException):
                logger.warning("Impossible de créer le rôle %s", role_name)
                continue
        role_map[threshold] = role

    new_threshold = _highest_earned_threshold(new_level)
    old_threshold = _highest_earned_threshold(old_level)

    if new_threshold == old_threshold:
        # Aucun changement de palier
        return None

    newly_granted: Optional[discord.Role] = None

    # Retirer tous les rôles de palier inférieurs ou égaux au précédent (on remplace)
    roles_to_remove = [
        r for t, r in role_map.items()
        if t != new_threshold and r in member.roles
    ]
    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason="Mise à jour rôle niveau XP")
        except discord.Forbidden:
            logger.warning("Impossible de retirer les anciens rôles de niveau pour %s", member)
        except discord.HTTPException:
            logger.exception("Erreur lors du retrait des rôles de niveau pour %s", member)

    # Attribuer le nouveau rôle de palier
    if new_threshold is not None and new_threshold in role_map:
        new_role = role_map[new_threshold]
        if new_role not in member.roles:
            try:
                await member.add_roles(new_role, reason=f"Niveau {new_level} atteint")
                newly_granted = new_role
                logger.info("Rôle %s attribué à %s (niveau %s)", new_role.name, member, new_level)
            except discord.Forbidden:
                logger.warning("Impossible d'attribuer le rôle %s à %s", new_role.name, member)
            except discord.HTTPException:
                logger.exception("Erreur lors de l'attribution du rôle de niveau pour %s", member)

    return newly_granted
