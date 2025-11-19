import os
import datetime
from collections import Counter
from typing import Optional, Iterable

import discord
from discord import app_commands
from discord.ext import commands

# Configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
tree_synced = False


@bot.event
async def on_ready():
    global tree_synced
    print(f'{bot.user} est connecté!')

    if not tree_synced:
        await bot.tree.sync()
        tree_synced = True


@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(
        title='Commandes du Bot',
        description=(
            '**Modération:**\n'
            '`/purge` - Nettoyer et verrouiller un salon\n'
            '`/unpurge` - Rouvrir un salon verrouillé\n\n'
            '**Analytics:**\n'
            '`/stats_last_3_months` - Auteurs uniques sur les 3 derniers mois\n'
            '`/stats_messages` - Classement par nombre de messages sur une période\n\n'
            '**Utilitaires:**\n'
            '`!ping` - Vérifier la latence du bot'
        ),
        color=0x5865F2
    )
    await ctx.send(embed=embed)


@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')


# ERROR HANDLING
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f'Error: {error}')


def _iter_message_channels(guild: discord.Guild) -> Iterable[discord.abc.Messageable]:
    """Retourne les salons et fils textuels où le bot peut lire l'historique."""
    seen_ids = set()

    for channel in guild.text_channels:
        if channel.id in seen_ids:
            continue
        seen_ids.add(channel.id)
        yield channel
        for thread in channel.threads:
            if thread.id in seen_ids:
                continue
            seen_ids.add(thread.id)
            yield thread

    for thread in guild.threads:
        if thread.id in seen_ids:
            continue
        seen_ids.add(thread.id)
        yield thread


async def collect_message_stats(guild: discord.Guild, cutoff: datetime.datetime) -> tuple[int, Counter]:
    """Collecte les statistiques de messages depuis une date donnée."""
    authors = set()
    counter: Counter[int] = Counter()

    for channel in _iter_message_channels(guild):
        permissions = channel.permissions_for(guild.me)
        if not (permissions.view_channel and permissions.read_message_history):
            continue

        async for message in channel.history(limit=None, after=cutoff, oldest_first=True):
            if message.author.bot:
                continue
            authors.add(message.author.id)
            counter[message.author.id] += 1

    return len(authors), counter


# MODERATION COMMANDS
@bot.tree.command(name='purge', description='Nettoie les messages et verrouille le salon pour les membres')
@app_commands.describe(
    amount='Nombre de messages à supprimer (1-1000)',
    reason='Raison affichée dans le journal'
)
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000] = 100, reason: Optional[str] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message('Permissions insuffisantes pour utiliser cette commande.', ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=True)

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send('Cette commande ne peut être utilisée que dans un salon textuel.', ephemeral=True)
        return

    log_reason = reason or f'Purge demandée par {interaction.user} '
    deleted = await channel.purge(limit=amount, reason=log_reason)

    overwrite = channel.overwrites_for(interaction.guild.default_role)
    if overwrite is None:
        overwrite = discord.PermissionOverwrite()
    overwrite.send_messages = False
    overwrite.add_reactions = True
    overwrite.create_public_threads = False
    overwrite.create_private_threads = False
    overwrite.send_messages_in_threads = False

    await channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
        reason='Salon verrouillé après purge'
    )

    info_embed = discord.Embed(
        title='🔒 Salon verrouillé',
        description=(
            "Ce salon vient d'être purgé et est désormais verrouillé pour les membres.\n"
            "Seuls les administrateurs peuvent y écrire."
        ),
        color=0xffa500
    )
    info_embed.add_field(name='Messages supprimés', value=str(len(deleted)), inline=True)
    if reason:
        info_embed.add_field(name='Raison', value=reason, inline=False)
    info_embed.set_footer(text=f'Action effectuée par {interaction.user.display_name}')

    await channel.send(embed=info_embed)
    await interaction.followup.send(f'Purge terminée : {len(deleted)} messages supprimés.', ephemeral=True)


@bot.tree.command(name='unpurge', description='Rouvre un salon précédemment verrouillé')
@app_commands.describe(reason='Raison affichée dans le journal')
async def unpurge(interaction: discord.Interaction, reason: Optional[str] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message('Permissions insuffisantes pour utiliser cette commande.', ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=True)

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send('Cette commande ne peut être utilisée que dans un salon textuel.', ephemeral=True)
        return

    overwrite = channel.overwrites_for(interaction.guild.default_role)
    if overwrite is None:
        overwrite = discord.PermissionOverwrite()

    overwrite.send_messages = True
    overwrite.add_reactions = True
    overwrite.create_public_threads = True
    overwrite.create_private_threads = True
    overwrite.send_messages_in_threads = True

    await channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
        reason=reason or 'Salon rouvert après unpurge'
    )

    info_embed = discord.Embed(
        title='🔓 Salon rouvert',
        description='Les membres peuvent à nouveau envoyer des messages et créer des fils.',
        color=0x57F287
    )
    if reason:
        info_embed.add_field(name='Raison', value=reason, inline=False)
    info_embed.set_footer(text=f'Action effectuée par {interaction.user.display_name}')

    await channel.send(embed=info_embed)
    await interaction.followup.send('Le salon est à nouveau disponible pour les membres.', ephemeral=True)


@bot.tree.command(name='stats_last_3_months', description='Compte les auteurs uniques ayant parlé durant les 3 derniers mois (historique inclus)')
async def stats_last_3_months(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    cutoff = discord.utils.utcnow() - datetime.timedelta(days=90)
    unique_authors, _ = await collect_message_stats(interaction.guild, cutoff)
    await interaction.followup.send(
        f"Auteurs uniques sur les 3 derniers mois : {unique_authors} (inclut les messages antérieurs au lancement du bot)",
        ephemeral=True,
    )


@bot.tree.command(name='stats_messages', description='Classement des membres ayant envoyé au moins N messages sur une période donnée (historique inclus)')
@app_commands.describe(
    min_messages='Nombre minimal de messages',
    window_days='Fenêtre de temps en jours'
)
async def stats_messages(
    interaction: discord.Interaction,
    min_messages: app_commands.Range[int, 1, 1000],
    window_days: app_commands.Range[int, 1, 365]
):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    cutoff = discord.utils.utcnow() - datetime.timedelta(days=window_days)
    _, counter = await collect_message_stats(interaction.guild, cutoff)

    filtered = [(author_id, count) for author_id, count in counter.most_common() if count >= min_messages]
    if not filtered:
        await interaction.followup.send('Personne ne correspond à ces critères sur la période demandée.', ephemeral=True)
        return

    lines = []
    for position, (author_id, count) in enumerate(filtered, start=1):
        lines.append(f"{position}. <@{author_id}> — {count} messages")

    await interaction.followup.send(
        "Classement des membres (historique inclus) :\n" + "\n".join(lines),
        ephemeral=True,
    )


# START BOT
if __name__ == '__main__':
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print('ERREUR: Token Discord non trouvé!')
        print("Ajoutez votre token dans les variables d'environnement: DISCORD_TOKEN=votre_token")
    else:
        bot.run(TOKEN)
