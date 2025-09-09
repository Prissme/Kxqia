# Bot Discord Giveaway en Python
# Requirements: discord.py, asyncio
# Installation: pip install discord.py

# Fix pour Python 3.13+ - Module audioop manquant
import sys
if sys.version_info >= (3, 13):
    import warnings
    warnings.filterwarnings("ignore", message=".*audioop.*")
    
    # Mock du module audioop pour éviter l'erreur
    import types
    audioop = types.ModuleType('audioop')
    sys.modules['audioop'] = audioop

import discord
from discord.ext import commands, tasks
import asyncio
import random
import datetime
import re
import os

# Configuration du bot (sans voice pour éviter audioop)
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.reactions = True

# Désactiver les intents voice pour éviter les problèmes audioop
intents.voice_states = False

bot = commands.Bot(command_prefix='!', intents=intents)

# Stockage des giveaways actifs
active_giveaways = {}

# Configuration
CONFIG = {
    'prefix': '!',
    'embed_color': 0x00ff00,
    'admin_role': 'Admin',
    'error_color': 0xff0000,
    'success_color': 0x00ff00
}

@bot.event
async def on_ready():
    print(f'✅ Bot connecté en tant que {bot.user}!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="🎉 Giveaways en cours"))

class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label='Participer 🎉', style=discord.ButtonStyle.primary, custom_id='join_giveaway')
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = active_giveaways.get(self.giveaway_id)
        
        if not giveaway or giveaway.get('ended', False):
            await interaction.response.send_message('❌ Ce giveaway n\'est plus actif.', ephemeral=True)
            return

        user_id = interaction.user.id
        
        if user_id in giveaway['participants']:
            giveaway['participants'].remove(user_id)
            await interaction.response.send_message('❌ Vous avez quitté le giveaway!', ephemeral=True)
        else:
            giveaway['participants'].add(user_id)
            await interaction.response.send_message('✅ Vous participez maintenant au giveaway! Bonne chance!', ephemeral=True)

@bot.command(name='giveaway', aliases=['g'])
async def create_giveaway(ctx, duration: str = None, winners: int = None, *, prize: str = None):
    """Créer un nouveau giveaway"""
    
    # Vérification des permissions
    if not ctx.author.guild_permissions.manage_messages and not any(role.name == CONFIG['admin_role'] for role in ctx.author.roles):
        await ctx.reply('❌ Vous n\'avez pas la permission d\'utiliser cette commande.')
        return

    if not all([duration, winners, prize]):
        embed = discord.Embed(
            title="❌ Usage incorrect",
            description="Usage: `!giveaway <durée> <nombre_gagnants> <prix>`\nExemple: `!giveaway 1h 1 Nitro Discord`",
            color=CONFIG['error_color']
        )
        await ctx.reply(embed=embed)
        return

    # Parsing de la durée
    duration_seconds = parse_duration(duration)
    if not duration_seconds:
        await ctx.reply('❌ Durée invalide. Utilisez: s (secondes), m (minutes), h (heures), d (jours)')
        return

    if winners < 1:
        await ctx.reply('❌ Le nombre de gagnants doit être un nombre positif.')
        return

    # Calcul du temps de fin
    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration_seconds)
    giveaway_id = str(int(datetime.datetime.now().timestamp()))

    # Création de l'embed
    embed = discord.Embed(
        title='🎉 GIVEAWAY 🎉',
        description=f"**Prix:** {prize}\n**Gagnants:** {winners}\n**Fin:** <t:{int(end_time.timestamp())}:R>\n**Organisé par:** {ctx.author.mention}",
        color=CONFIG['embed_color'],
        timestamp=end_time
    )
    embed.set_footer(text=f"ID: {giveaway_id} • Réagissez avec 🎉 pour participer!")

    # Envoi du message avec bouton
    view = GiveawayView(giveaway_id)
    giveaway_message = await ctx.send(embed=embed, view=view)
    await giveaway_message.add_reaction('🎉')

    # Stockage du giveaway
    active_giveaways[giveaway_id] = {
        'message_id': giveaway_message.id,
        'channel_id': ctx.channel.id,
        'guild_id': ctx.guild.id,
        'prize': prize,
        'winners': winners,
        'end_time': end_time,
        'host_id': ctx.author.id,
        'participants': set(),
        'ended': False
    }

    # Programmer la fin du giveaway
    asyncio.create_task(schedule_giveaway_end(giveaway_id, duration_seconds))
    
    # Supprimer le message de commande
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name='gend', aliases=['gfinish'])
async def end_giveaway_command(ctx, message_id: int = None):
    """Terminer un giveaway manuellement"""
    
    if not ctx.author.guild_permissions.manage_messages and not any(role.name == CONFIG['admin_role'] for role in ctx.author.roles):
        await ctx.reply('❌ Vous n\'avez pas la permission d\'utiliser cette commande.')
        return

    if not message_id:
        await ctx.reply('❌ Usage: `!gend <message_id>`')
        return

    # Trouver le giveaway
    giveaway_id = None
    for gid, giveaway in active_giveaways.items():
        if giveaway['message_id'] == message_id:
            giveaway_id = gid
            break

    if not giveaway_id:
        await ctx.reply('❌ Giveaway non trouvé ou déjà terminé.')
        return

    await finish_giveaway(giveaway_id)
    await ctx.reply('✅ Giveaway terminé manuellement!')

@bot.command(name='greroll')
async def reroll_giveaway(ctx, message_id: int = None):
    """Refaire le tirage d'un giveaway terminé"""
    
    if not ctx.author.guild_permissions.manage_messages and not any(role.name == CONFIG['admin_role'] for role in ctx.author.roles):
        await ctx.reply('❌ Vous n\'avez pas la permission d\'utiliser cette commande.')
        return

    if not message_id:
        await ctx.reply('❌ Usage: `!greroll <message_id>`')
        return

    try:
        message = await ctx.channel.fetch_message(message_id)
        
        if not message.embeds or 'GIVEAWAY TERMINÉ' not in message.embeds[0].title:
            await ctx.reply('❌ Ce message n\'est pas un giveaway terminé.')
            return

        # Récupérer les participants via les réactions
        reaction = None
        for r in message.reactions:
            if str(r.emoji) == '🎉':
                reaction = r
                break

        if not reaction:
            await ctx.reply('❌ Aucune réaction trouvée sur ce giveaway.')
            return

        participants = []
        async for user in reaction.users():
            if not user.bot:
                participants.append(user)

        if not participants:
            await ctx.reply('❌ Aucun participant trouvé.')
            return

        winner = random.choice(participants)
        prize = message.embeds[0].description.split('**Prix:** ')[1].split('\n')[0]

        await ctx.send(f'🎊 Nouveau tirage! Le gagnant est {winner.mention} pour: **{prize}**!')

    except discord.NotFound:
        await ctx.reply('❌ Message non trouvé.')
    except Exception as e:
        await ctx.reply('❌ Erreur lors du nouveau tirage.')

@bot.command(name='glist')
async def list_giveaways(ctx):
    """Lister tous les giveaways actifs"""
    
    guild_giveaways = [g for g in active_giveaways.values() 
                      if not g.get('ended', False) and g['guild_id'] == ctx.guild.id]

    if not guild_giveaways:
        await ctx.reply('📝 Aucun giveaway actif dans ce serveur.')
        return

    embed = discord.Embed(
        title='📝 Giveaways Actifs',
        color=CONFIG['embed_color'],
        timestamp=datetime.datetime.utcnow()
    )

    for i, giveaway in enumerate(guild_giveaways, 1):
        embed.add_field(
            name=f"{i}. {giveaway['prize']}",
            value=f"**Canal:** <#{giveaway['channel_id']}>\n**Fin:** <t:{int(giveaway['end_time'].timestamp())}:R>\n**Participants:** {len(giveaway['participants'])}",
            inline=True
        )

    await ctx.reply(embed=embed)

@bot.command(name='ghelp')
async def giveaway_help(ctx):
    """Afficher l'aide pour les commandes giveaway"""
    
    embed = discord.Embed(
        title='🎮 Commandes du Bot Giveaway',
        description='Voici toutes les commandes disponibles:',
        color=CONFIG['embed_color']
    )
    
    commands_info = [
        ('`!giveaway <durée> <gagnants> <prix>`', 'Créer un nouveau giveaway\nExemple: `!giveaway 1h 1 Nitro Discord`'),
        ('`!gend <message_id>`', 'Terminer un giveaway manuellement'),
        ('`!greroll <message_id>`', 'Refaire le tirage d\'un giveaway terminé'),
        ('`!glist`', 'Afficher tous les giveaways actifs'),
        ('`!ghelp`', 'Afficher cette aide')
    ]
    
    for cmd, desc in commands_info:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name='Formats de durée acceptés:',
        value='`s` = secondes, `m` = minutes, `h` = heures, `d` = jours\nExemple: `30s`, `5m`, `2h`, `1d`',
        inline=False
    )
    
    embed.set_footer(text='Bot Giveaway • Créé avec ❤️')
    await ctx.reply(embed=embed)

async def schedule_giveaway_end(giveaway_id, delay):
    """Programmer la fin automatique d'un giveaway"""
    await asyncio.sleep(delay)
    await finish_giveaway(giveaway_id)

async def finish_giveaway(giveaway_id):
    """Terminer un giveaway et sélectionner les gagnants"""
    giveaway = active_giveaways.get(giveaway_id)
    if not giveaway or giveaway.get('ended', False):
        return

    giveaway['ended'] = True

    try:
        channel = bot.get_channel(giveaway['channel_id'])
        message = await channel.fetch_message(giveaway['message_id'])

        participants = list(giveaway['participants'])
        
        if not participants:
            # Aucun participant
            embed = discord.Embed(
                title='🎉 GIVEAWAY TERMINÉ 🎉',
                description=f"**Prix:** {giveaway['prize']}\n**Gagnants:** Aucun participant",
                color=CONFIG['error_color']
            )
            embed.set_footer(text=f"ID: {giveaway_id} • Giveaway terminé")
            
            await message.edit(embed=embed, view=None)
            return

        # Sélection des gagnants
        num_winners = min(giveaway['winners'], len(participants))
        winners = random.sample(participants, num_winners)
        
        winner_mentions = [f'<@{winner_id}>' for winner_id in winners]
        winner_text = ', '.join(winner_mentions)

        # Embed de fin
        embed = discord.Embed(
            title='🎉 GIVEAWAY TERMINÉ 🎉',
            description=f"**Prix:** {giveaway['prize']}\n**Gagnant(s):** {winner_text}\n**Participants:** {len(participants)}",
            color=CONFIG['success_color']
        )
        embed.set_footer(text=f"ID: {giveaway_id} • Giveaway terminé")

        await message.edit(embed=embed, view=None)
        await channel.send(f'🎊 Félicitations {winner_text}! Vous avez gagné: **{giveaway["prize"]}**!')

    except Exception as e:
        print(f'Erreur lors de la fin du giveaway: {e}')

    # Supprimer du stockage
    if giveaway_id in active_giveaways:
        del active_giveaways[giveaway_id]

def parse_duration(duration_str):
    """Parser une durée en secondes"""
    pattern = r'^(\d+)([smhd])$'
    match = re.match(pattern, duration_str.lower())
    
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }
    
    return value * multipliers.get(unit, 0)

@bot.event
async def on_command_error(ctx, error):
    """Gestion des erreurs de commandes"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f'❌ Argument manquant. Utilisez `!ghelp` pour voir l\'usage.')
    elif isinstance(error, commands.BadArgument):
        await ctx.reply(f'❌ Argument invalide. Utilisez `!ghelp` pour voir l\'usage.')
    else:
        print(f'Erreur: {error}')

# Récupération du token depuis les variables d'environnement
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print('❌ Erreur: Variable DISCORD_TOKEN non définie!')
    print('Sur Koyeb, ajoutez la variable d\'environnement:')
    print('DISCORD_TOKEN = votre_token_discord')
    exit(1)

# Démarrage du bot
if __name__ == '__main__':
    bot.run(TOKEN)

"""
📁 FICHIERS REQUIS POUR KOYEB:

1. main.py (ce fichier)
2. requirements.txt (voir ci-dessous)

📋 requirements.txt:
discord.py==2.3.2

🚀 CONFIGURATION KOYEB:
1. Créez un repo GitHub avec main.py et requirements.txt  
2. Sur Koyeb, créez un nouveau service
3. Connectez votre repo GitHub
4. Configuration du service:
   - Runtime: Python 3.9+
   - Build command: pip install -r requirements.txt
   - Run command: python main.py
   - Instance type: nano (gratuit)
5. Variables d'environnement:
   - DISCORD_TOKEN = votre_token_discord
6. Déployez!

🎮 COMMANDES DISPONIBLES:
- !giveaway 1h 1 Nitro Discord - Créer un giveaway
- !gend <message_id> - Terminer manuellement
- !greroll <message_id> - Nouveau tirage  
- !glist - Liste des giveaways actifs
- !ghelp - Afficher l'aide

✨ FONCTIONNALITÉS:
✅ Giveaways automatiques avec timer
✅ Boutons interactifs Discord
✅ Système de permissions
✅ Sélection aléatoire des gagnants
✅ Reroll des giveaways terminés
✅ Interface moderne avec embeds
✅ Gestion d'erreurs complète
✅ Support multi-serveurs
✅ Compatible Koyeb 24/7

🔧 PERMISSIONS DISCORD REQUISES:
- Send Messages
- Use Slash Commands  
- Manage Messages
- Add Reactions
- Read Message History
- Use External Emojis
"""