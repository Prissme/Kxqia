import discord
from discord import app_commands
from discord.ext import commands
import os
from typing import Optional

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
        description='**Modération:**\n`/purge` - Nettoyer et verrouiller un salon\n`/unpurge` - Rouvrir un salon verrouillé\n\n**Utilitaires:**\n`!ping` - Vérifier la latence du bot',
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

# START BOT
if __name__ == '__main__':
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print('ERREUR: Token Discord non trouvé!')
        print('Ajoutez votre token dans les variables d\'environnement: DISCORD_TOKEN=votre_token')
    else:
        bot.run(TOKEN)
