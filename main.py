import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
import datetime
import re
import os
from typing import Optional

# Configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)
tree_synced = False

# Variables globales
active_giveaways = {}
temp_channels = {}
voice_config = {}

@bot.event
async def on_ready():
    global tree_synced
    print(f'{bot.user} est connecté!')

    if not cleanup_channels.is_running():
        cleanup_channels.start()

    if not tree_synced:
        await bot.tree.sync()
        tree_synced = True

# GIVEAWAY SYSTEM
class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label='Participer', style=discord.ButtonStyle.primary, emoji='🎉')
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = active_giveaways.get(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message('Giveaway introuvable', ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id in giveaway['participants']:
            giveaway['participants'].remove(user_id)
            message = 'Vous avez quitté le giveaway'
        else:
            giveaway['participants'].add(user_id)
            message = 'Participation enregistrée!'

        embed = discord.Embed(description=message, color=0x00ff00)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name='giveaway', aliases=['g'])
async def create_giveaway(ctx, duration=None, winners: int = 1, *, prize=None):
    if not ctx.author.guild_permissions.manage_messages:
        await ctx.send('Permissions insuffisantes')
        return

    if not duration or not prize:
        embed = discord.Embed(
            title='Usage',
            description='`!giveaway <durée> <gagnants> <prix>`\nExemple: `!giveaway 1h 1 Nitro Discord`',
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return

    # Parse duration
    duration_seconds = parse_duration(duration)
    if not duration_seconds:
        await ctx.send('Durée invalide. Utilisez: 30s, 5m, 2h, 1d')
        return

    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration_seconds)
    giveaway_id = f"{ctx.guild.id}_{int(datetime.datetime.now().timestamp())}"

    embed = discord.Embed(
        title='🎉 GIVEAWAY',
        description=f'**Prix:** {prize}\n**Gagnants:** {winners}\n**Fin:** <t:{int(end_time.timestamp())}:R>',
        color=0x5865F2
    )

    view = GiveawayView(giveaway_id)
    message = await ctx.send(embed=embed, view=view)

    active_giveaways[giveaway_id] = {
        'message_id': message.id,
        'channel_id': ctx.channel.id,
        'prize': prize,
        'winners': winners,
        'end_time': end_time,
        'participants': set(),
        'host_id': ctx.author.id
    }

    await asyncio.sleep(duration_seconds)
    await end_giveaway(giveaway_id)

async def end_giveaway(giveaway_id):
    giveaway = active_giveaways.get(giveaway_id)
    if not giveaway:
        return

    channel = bot.get_channel(giveaway['channel_id'])
    if not channel:
        return

    participants = list(giveaway['participants'])
    
    embed = discord.Embed(title='🎉 GIVEAWAY TERMINÉ', color=0x00ff00)
    embed.add_field(name='Prix', value=giveaway['prize'], inline=False)

    if participants:
        winners = random.sample(participants, min(giveaway['winners'], len(participants)))
        winner_mentions = [f'<@{w}>' for w in winners]
        embed.add_field(name='Gagnants', value='\n'.join(winner_mentions), inline=False)
        
        await channel.send(f"Félicitations {', '.join(winner_mentions)}!", embed=embed)
    else:
        embed.add_field(name='Gagnants', value='Aucun participant', inline=False)
        await channel.send(embed=embed)

    del active_giveaways[giveaway_id]

# VOICE SYSTEM
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    # Auto setup si nécessaire
    if member.guild.id not in voice_config:
        await setup_voice_system(member.guild)

    config = voice_config.get(member.guild.id)
    if not config:
        return

    # Création de salon
    if after.channel and after.channel.id == config.get('join_channel'):
        await create_temp_channel(member)

    # Nettoyage
    if before.channel and before.channel.id in temp_channels and len(before.channel.members) == 0:
        await delete_temp_channel(before.channel.id)

async def setup_voice_system(guild):
    try:
        category = discord.utils.get(guild.categories, name="Salons Vocaux")
        if not category:
            category = await guild.create_category("Salons Vocaux")

        join_channel = discord.utils.get(guild.voice_channels, name="➕ Créer un salon")
        if not join_channel:
            join_channel = await guild.create_voice_channel("➕ Créer un salon", category=category)

        voice_config[guild.id] = {
            'category': category.id,
            'join_channel': join_channel.id
        }
        print(f"Voice system setup for {guild.name}")
    except:
        pass

async def create_temp_channel(member):
    try:
        guild = member.guild
        config = voice_config[guild.id]
        category = bot.get_channel(config['category'])

        channel = await guild.create_voice_channel(
            f"Salon de {member.display_name}",
            category=category
        )

        await channel.set_permissions(member, manage_channels=True)
        await member.move_to(channel)

        temp_channels[channel.id] = {
            'owner': member.id,
            'created': datetime.datetime.utcnow()
        }

        print(f"Created temp channel for {member}")
    except Exception as e:
        print(f"Error creating temp channel: {e}")

async def delete_temp_channel(channel_id):
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.delete()
        if channel_id in temp_channels:
            del temp_channels[channel_id]
        print(f"Deleted temp channel {channel_id}")
    except Exception as e:
        print(f"Error deleting channel: {e}")

@tasks.loop(minutes=10)
async def cleanup_channels():
    channels_to_remove = []
    for channel_id, data in temp_channels.items():
        channel = bot.get_channel(channel_id)
        if not channel or len(channel.members) == 0:
            channels_to_remove.append(channel_id)

    for channel_id in channels_to_remove:
        await delete_temp_channel(channel_id)

@cleanup_channels.before_loop
async def before_cleanup():
    await bot.wait_until_ready()

# COMMANDS
@bot.command(name='vsetup')
async def setup_voice(ctx):
    if not ctx.author.guild_permissions.manage_channels:
        await ctx.send('Permissions insuffisantes')
        return
    
    await setup_voice_system(ctx.guild)
    await ctx.send('Système vocal configuré!')

@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(
        title='Commandes du Bot',
        description='**Giveaways:**\n`!giveaway <durée> <gagnants> <prix>`\n\n**Vocal:**\n`!vsetup` - Configuration\nRejoindre "➕ Créer un salon"\n\n**Modération:**\n`/purge` - Nettoyer et verrouiller un salon',
        color=0x5865F2
    )
    await ctx.send(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')

# UTILITY FUNCTIONS
def parse_duration(duration_str):
    pattern = r'^(\d+)([smhd])$'
    match = re.match(pattern, duration_str.lower())
    
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    return value * multipliers.get(unit, 0)

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
    overwrite.add_reactions = False

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

# START BOT
if __name__ == '__main__':
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print('ERREUR: Token Discord non trouvé!')
        print('Ajoutez votre token dans les variables d\'environnement: DISCORD_TOKEN=votre_token')
    else:
        bot.run(TOKEN)
