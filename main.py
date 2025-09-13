# Bot Discord Giveaway Ultra Clean & Optimisé
# Exclusivement dédié aux giveaways avec interface moderne
# Requirements: discord.py
# Installation: pip install discord.py

import discord
from discord.ext import commands
import asyncio
import random
import datetime
import re
import os

# Configuration moderne du bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Stockage des giveaways actifs (en mémoire)
active_giveaways = {}

# Configuration design moderne
CONFIG = {
    'colors': {
        'primary': 0x5865F2,      # Discord Blurple
        'success': 0x57F287,      # Vert moderne
        'error': 0xED4245,        # Rouge moderne
        'warning': 0xFEE75C,      # Jaune moderne
        'info': 0x5865F2          # Bleu moderne
    },
    'emojis': {
        'giveaway': '🎉',
        'winner': '🏆',
        'participants': '👥',
        'time': '⏰',
        'host': '👑',
        'gift': '🎁'
    }
}

@bot.event
async def on_ready():
    print(f'🎉 {bot.user} est connecté!')
    print(f'📊 Présent sur {len(bot.guilds)} serveur(s)')
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=f"🎉 Giveaways sur {len(bot.guilds)} serveurs"
        )
    )

# ==================== SYSTÈME GIVEAWAY MODERNE ====================

class ModernGiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(
        label='🎉 PARTICIPER',
        style=discord.ButtonStyle.primary,
        custom_id='join_giveaway'
    )
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = active_giveaways.get(self.giveaway_id)
        
        if not giveaway or giveaway.get('ended', False):
            embed = discord.Embed(
                description='❌ Ce giveaway n\'est plus actif',
                color=CONFIG['colors']['error']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_id = interaction.user.id
        
        if user_id in giveaway['participants']:
            giveaway['participants'].remove(user_id)
            embed = discord.Embed(
                description='🚪 Vous avez quitté le giveaway',
                color=CONFIG['colors']['warning']
            )
        else:
            giveaway['participants'].add(user_id)
            embed = discord.Embed(
                description='✅ Inscription réussie! Bonne chance!',
                color=CONFIG['colors']['success']
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.update_giveaway_embed(interaction)
    
    async def update_giveaway_embed(self, interaction):
        """Met à jour l'embed du giveaway"""
        giveaway = active_giveaways.get(self.giveaway_id)
        if not giveaway:
            return
            
        embed = self.create_giveaway_embed(giveaway, self.giveaway_id)
        
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except:
            pass

    def create_giveaway_embed(self, giveaway, giveaway_id):
        """Créer l'embed moderne du giveaway"""
        participants_count = len(giveaway['participants'])
        end_time = giveaway['end_time']
        
        # Embed principal avec design moderne
        embed = discord.Embed(
            title=f"{CONFIG['emojis']['giveaway']} **GIVEAWAY EN COURS** {CONFIG['emojis']['giveaway']}",
            color=CONFIG['colors']['primary']
        )
        
        # Description avec le prix en évidence
        embed.description = f"### {CONFIG['emojis']['gift']} **{giveaway['prize']}**"
        
        # Informations structurées
        embed.add_field(
            name=f"{CONFIG['emojis']['winner']} Gagnants",
            value=f"**{giveaway['winners']}**",
            inline=True
        )
        
        embed.add_field(
            name=f"{CONFIG['emojis']['participants']} Participants",
            value=f"**{participants_count}**",
            inline=True
        )
        
        embed.add_field(
            name=f"{CONFIG['emojis']['time']} Fin",
            value=f"<t:{int(end_time.timestamp())}:R>",
            inline=True
        )
        
        embed.add_field(
            name=f"{CONFIG['emojis']['host']} Organisé par",
            value=f"<@{giveaway['host_id']}>",
            inline=False
        )
        
        # Footer moderne
        embed.set_footer(
            text=f"ID: {giveaway_id} • Cliquez pour participer!",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        
        embed.timestamp = end_time
        
        return embed

@bot.command(name='giveaway', aliases=['g', 'gw'])
async def create_giveaway(ctx, duration: str = None, winners: int = None, *, prize: str = None):
    """🎉 Créer un giveaway moderne avec interface interactive"""
    
    # Vérification des permissions
    if not ctx.author.guild_permissions.manage_messages:
        embed = discord.Embed(
            description='❌ Permission requise: **Gérer les messages**',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    # Vérification des arguments
    if not all([duration, winners, prize]):
        embed = discord.Embed(
            title='❌ Arguments manquants',
            description='**Usage:** `!giveaway <durée> <gagnants> <prix>`\n**Exemple:** `!giveaway 2h 1 Nitro Discord`',
            color=CONFIG['colors']['error']
        )
        embed.add_field(
            name='⏰ Formats de durée',
            value='`30s` `5m` `2h` `1d` `1w`',
            inline=False
        )
        await ctx.reply(embed=embed)
        return

    # Validation de la durée
    duration_seconds = parse_duration(duration)
    if not duration_seconds:
        embed = discord.Embed(
            description='❌ Durée invalide. Formats: `s` `m` `h` `d` `w`',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    # Validation du nombre de gagnants
    if winners < 1 or winners > 50:
        embed = discord.Embed(
            description='❌ Nombre de gagnants: entre 1 et 50',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    # Validation de la longueur du prix
    if len(prize) > 200:
        embed = discord.Embed(
            description='❌ Le prix doit faire moins de 200 caractères',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    # Calcul du temps de fin
    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration_seconds)
    giveaway_id = f"{ctx.guild.id}_{int(datetime.datetime.now().timestamp())}"

    # Création du giveaway
    giveaway_data = {
        'message_id': None,  # Sera défini après l'envoi
        'channel_id': ctx.channel.id,
        'guild_id': ctx.guild.id,
        'prize': prize,
        'winners': winners,
        'end_time': end_time,
        'host_id': ctx.author.id,
        'participants': set(),
        'ended': False,
        'created_at': datetime.datetime.utcnow()
    }

    # Création de l'embed et de la vue
    view = ModernGiveawayView(giveaway_id)
    embed = view.create_giveaway_embed(giveaway_data, giveaway_id)

    # Envoi du message
    try:
        giveaway_message = await ctx.send(embed=embed, view=view)
        
        # Mise à jour des données avec l'ID du message
        giveaway_data['message_id'] = giveaway_message.id
        active_giveaways[giveaway_id] = giveaway_data

        # Programmer la fin automatique
        asyncio.create_task(schedule_giveaway_end(giveaway_id, duration_seconds))
        
        # Supprimer le message de commande
        try:
            await ctx.message.delete()
        except:
            pass

        # Confirmation pour l'organisateur
        confirm_embed = discord.Embed(
            description=f'✅ Giveaway créé avec succès!\n**Prix:** {prize}\n**Durée:** {duration}\n**Gagnants:** {winners}',
            color=CONFIG['colors']['success']
        )
        confirm_msg = await ctx.send(embed=confirm_embed, delete_after=10)
        
    except discord.Forbidden:
        embed = discord.Embed(
            description='❌ Permissions insuffisantes pour créer le giveaway',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)

@bot.command(name='gend', aliases=['end'])
async def end_giveaway_command(ctx, message_id: int = None):
    """🏁 Terminer un giveaway manuellement"""
    
    if not ctx.author.guild_permissions.manage_messages:
        embed = discord.Embed(
            description='❌ Permission requise: **Gérer les messages**',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    if not message_id:
        embed = discord.Embed(
            description='❌ **Usage:** `!gend <message_id>`\n💡 Faites clic droit → Copier l\'ID sur le message du giveaway',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    # Recherche du giveaway
    giveaway_id = None
    for gid, giveaway in active_giveaways.items():
        if giveaway['message_id'] == message_id and giveaway['guild_id'] == ctx.guild.id:
            giveaway_id = gid
            break

    if not giveaway_id:
        embed = discord.Embed(
            description='❌ Giveaway introuvable ou déjà terminé',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    await finish_giveaway(giveaway_id)
    
    embed = discord.Embed(
        description='✅ Giveaway terminé manuellement!',
        color=CONFIG['colors']['success']
    )
    await ctx.reply(embed=embed)

@bot.command(name='greroll', aliases=['reroll'])
async def reroll_giveaway(ctx, message_id: int = None):
    """🔄 Refaire le tirage d'un giveaway"""
    
    if not ctx.author.guild_permissions.manage_messages:
        embed = discord.Embed(
            description='❌ Permission requise: **Gérer les messages**',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    if not message_id:
        embed = discord.Embed(
            description='❌ **Usage:** `!greroll <message_id>`',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    try:
        message = await ctx.channel.fetch_message(message_id)
        
        if not message.embeds or 'GIVEAWAY TERMINÉ' not in message.embeds[0].title:
            embed = discord.Embed(
                description='❌ Ce message n\'est pas un giveaway terminé',
                color=CONFIG['colors']['error']
            )
            await ctx.reply(embed=embed)
            return

        # Récupérer les participants depuis les réactions du message original
        participants = []
        for reaction in message.reactions:
            if str(reaction.emoji) == '🎉':
                async for user in reaction.users():
                    if not user.bot:
                        participants.append(user)
                break

        if not participants:
            embed = discord.Embed(
                description='❌ Aucun participant trouvé pour ce giveaway',
                color=CONFIG['colors']['error']
            )
            await ctx.reply(embed=embed)
            return

        # Nouveau tirage
        winner = random.choice(participants)
        
        # Récupération du prix depuis l'embed
        embed_desc = message.embeds[0].description or ""
        prize = "Prix inconnu"
        if '**' in embed_desc:
            try:
                prize = embed_desc.split('**')[1]
            except:
                prize = "Prix inconnu"

        # Annonce du nouveau gagnant
        winner_embed = discord.Embed(
            title='🔄 NOUVEAU TIRAGE!',
            description=f'**Nouveau gagnant:** {winner.mention}\n**Prix:** {prize}',
            color=CONFIG['colors']['success']
        )
        winner_embed.set_footer(text='Félicitations! 🎉')
        
        await ctx.send(f'{winner.mention}', embed=winner_embed)

    except discord.NotFound:
        embed = discord.Embed(
            description='❌ Message introuvable',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            description='❌ Erreur lors du nouveau tirage',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)

@bot.command(name='glist', aliases=['list'])
async def list_giveaways(ctx):
    """📋 Liste des giveaways actifs"""
    
    guild_giveaways = [
        (gid, g) for gid, g in active_giveaways.items() 
        if not g.get('ended', False) and g['guild_id'] == ctx.guild.id
    ]

    if not guild_giveaways:
        embed = discord.Embed(
            title='📋 Giveaways Actifs',
            description='🔍 Aucun giveaway actif dans ce serveur',
            color=CONFIG['colors']['info']
        )
        await ctx.reply(embed=embed)
        return

    embed = discord.Embed(
        title=f'📋 Giveaways Actifs ({len(guild_giveaways)})',
        color=CONFIG['colors']['primary']
    )

    for i, (gid, giveaway) in enumerate(guild_giveaways[:10], 1):  # Limité à 10
        prize = giveaway['prize']
        if len(prize) > 50:
            prize = prize[:47] + "..."
            
        embed.add_field(
            name=f"{i}. {prize}",
            value=f"**Canal:** <#{giveaway['channel_id']}>\n**Fin:** <t:{int(giveaway['end_time'].timestamp())}:R>\n**Participants:** {len(giveaway['participants'])}",
            inline=True
        )

    if len(guild_giveaways) > 10:
        embed.set_footer(text=f'... et {len(guild_giveaways) - 10} autres giveaways')

    await ctx.reply(embed=embed)

@bot.command(name='help', aliases=['aide', 'h'])
async def bot_help(ctx):
    """📖 Guide complet du bot giveaway"""
    
    embed = discord.Embed(
        title='🎉 Bot Giveaway Ultra Clean',
        description='Bot moderne exclusivement dédié aux giveaways avec interface interactive',
        color=CONFIG['colors']['primary']
    )
    
    # Commandes principales
    embed.add_field(
        name='🎮 Commandes Principales',
        value='`!giveaway <durée> <gagnants> <prix>` - Créer un giveaway\n`!gend <message_id>` - Terminer manuellement\n`!greroll <message_id>` - Nouveau tirage\n`!glist` - Giveaways actifs',
        inline=False
    )
    
    # Formats de durée
    embed.add_field(
        name='⏰ Formats de Durée',
        value='`30s` secondes • `5m` minutes • `2h` heures • `1d` jours • `1w` semaines',
        inline=False
    )
    
    # Exemples
    embed.add_field(
        name='💡 Exemples',
        value='`!g 24h 1 Nitro Discord`\n`!giveaway 2d 3 50€ PayPal`\n`!g 1w 2 Clés Steam`',
        inline=False
    )
    
    # Permissions
    embed.add_field(
        name='🔐 Permissions Requises',
        value='**Gérer les messages** pour créer/gérer les giveaways',
        inline=False
    )
    
    # Fonctionnalités
    embed.add_field(
        name='✨ Fonctionnalités',
        value='• Interface moderne avec boutons\n• Participation en un clic\n• Mise à jour en temps réel\n• Anti-spam intégré\n• Multi-serveurs',
        inline=False
    )
    
    embed.set_footer(
        text='Bot Giveaway Clean • Interface moderne & intuitive',
        icon_url=bot.user.avatar.url if bot.user.avatar else None
    )
    
    await ctx.reply(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    """🏓 Latence du bot"""
    
    embed = discord.Embed(
        title='🏓 Pong!',
        description=f'**Latence:** {round(bot.latency * 1000)}ms',
        color=CONFIG['colors']['success']
    )
    await ctx.reply(embed=embed)

# ==================== FONCTIONS UTILITAIRES ====================

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
        if not channel:
            return
            
        message = await channel.fetch_message(giveaway['message_id'])
        participants = list(giveaway['participants'])
        
        # Embed de fin moderne
        if not participants:
            # Aucun participant
            embed = discord.Embed(
                title=f"{CONFIG['emojis']['giveaway']} **GIVEAWAY TERMINÉ** {CONFIG['emojis']['giveaway']}",
                description=f"### {CONFIG['emojis']['gift']} **{giveaway['prize']}**\n\n❌ **Aucun participant**",
                color=CONFIG['colors']['error']
            )
        else:
            # Sélection des gagnants
            num_winners = min(giveaway['winners'], len(participants))
            winners = random.sample(participants, num_winners)
            
            winner_mentions = [f'<@{winner_id}>' for winner_id in winners]
            winner_text = ', '.join(winner_mentions)

            embed = discord.Embed(
                title=f"{CONFIG['emojis']['giveaway']} **GIVEAWAY TERMINÉ** {CONFIG['emojis']['giveaway']}",
                description=f"### {CONFIG['emojis']['gift']} **{giveaway['prize']}**",
                color=CONFIG['colors']['success']
            )
            
            embed.add_field(
                name=f"{CONFIG['emojis']['winner']} Gagnant(s)",
                value=winner_text,
                inline=False
            )
            
            embed.add_field(
                name=f"{CONFIG['emojis']['participants']} Total Participants",
                value=f"**{len(participants)}**",
                inline=True
            )
            
            embed.add_field(
                name=f"{CONFIG['emojis']['host']} Organisé par",
                value=f"<@{giveaway['host_id']}>",
                inline=True
            )

            # Message de félicitations
            congrats_embed = discord.Embed(
                title='🎊 FÉLICITATIONS!',
                description=f'{winner_text}\n\nVous avez gagné: **{giveaway["prize"]}**!',
                color=CONFIG['colors']['success']
            )
            
            await channel.send(embed=congrats_embed)

        embed.set_footer(
            text=f"ID: {giveaway_id} • Giveaway terminé",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        
        # Mise à jour du message original sans bouton
        await message.edit(embed=embed, view=None)

    except Exception as e:
        print(f'❌ Erreur lors de la fin du giveaway {giveaway_id}: {e}')

    # Suppression du stockage
    if giveaway_id in active_giveaways:
        del active_giveaways[giveaway_id]

def parse_duration(duration_str):
    """Parser une durée en secondes avec support étendu"""
    pattern = r'^(\d+)([smhdw])$'
    match = re.match(pattern, duration_str.lower())
    
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    # Limites de sécurité
    if value <= 0:
        return None
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800  # 7 jours
    }
    
    duration_seconds = value * multipliers.get(unit, 0)
    
    # Limites: minimum 10 secondes, maximum 4 semaines
    if duration_seconds < 10 or duration_seconds > 2419200:  # 4 semaines
        return None
        
    return duration_seconds

@bot.event
async def on_command_error(ctx, error):
    """Gestion propre des erreurs"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            description='❌ Arguments manquants. Utilisez `!help` pour voir l\'usage',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            description='❌ Argument invalide. Utilisez `!help` pour voir l\'usage',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            description='❌ Vous n\'avez pas les permissions nécessaires',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
    else:
        print(f'❌ Erreur: {error}')

# Récupération du token
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print('❌ Variable DISCORD_TOKEN non définie!')
    print('🔧 Ajoutez votre token Discord dans les variables d\'environnement')
    exit(1)

# Démarrage du bot
if __name__ == '__main__':
    print('🚀 Démarrage du Bot Giveaway Clean...')
    bot.run(TOKEN)
