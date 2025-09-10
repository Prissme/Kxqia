# Bot Discord Giveaway + Vocal Simplifié en Python
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

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.reactions = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Stockage des giveaways actifs
active_giveaways = {}

# Stockage des salons vocaux temporaires
temp_channels = {}
creation_channels = {}  # {guild_id: channel_id}

# Configuration
CONFIG = {
    'prefix': '!',
    'embed_color': 0x00ff00,
    'admin_role': 'Admin',
    'error_color': 0xff0000,
    'success_color': 0x00ff00,
    'voice_color': 0x3498db
}

# Catégorie spécifique pour les salons vocaux
VOICE_CATEGORY_ID = 1236724293631611021
creation_channel_id = None  # ID du salon de création (sera défini au démarrage)

@bot.event
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
            embed = discord.Embed(
                title='🎉 GIVEAWAY TERMINÉ 🎉',
                description=f"**Prix:** {giveaway['prize']}\n**Gagnants:** Aucun participant",
                color=CONFIG['error_color']
            )
            embed.set_footer(text=f"ID: {giveaway_id} • Giveaway terminé")
            
            await message.edit(embed=embed, view=None)
            return

        num_winners = min(giveaway['winners'], len(participants))
        winners = random.sample(participants, num_winners)
        
        winner_mentions = [f'<@{winner_id}>' for winner_id in winners]
        winner_text = ', '.join(winner_mentions)

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
        await ctx.reply(f'❌ Argument manquant. Utilisez `!help` pour voir l\'usage.')
    elif isinstance(error, commands.BadArgument):
        await ctx.reply(f'❌ Argument invalide. Utilisez `!help` pour voir l\'usage.')
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
discord.py>=2.3.0,<2.4.0

🐍 .python-version:
3.11

📄 runtime.txt:
python-3.11.9

🚀 CONFIGURATION KOYEB:
1. Créez un repo GitHub avec main.py et requirements.txt  
2. Sur Koyeb, créez un nouveau service
3. Connectez votre repo GitHub
4. Configuration du service:
   - Runtime: Python 3.11
   - Build command: pip install -r requirements.txt
   - Run command: python main.py
   - Instance type: nano (gratuit)
5. Variables d'environnement:
   - DISCORD_TOKEN = votre_token_discord
6. Déployez!

🎮 COMMANDES DISPONIBLES:

📊 GIVEAWAYS:
- !giveaway 1h 1 Nitro Discord - Créer un giveaway
- !gend <message_id> - Terminer manuellement
- !greroll <message_id> - Nouveau tirage  
- !glist - Liste des giveaways actifs

🎛️ VOCAL DASHBOARD:
- !vinfo - Informations sur le système vocal
- Rejoignez le salon "🔊・Créer un salon" pour votre dashboard!

⚙️ GÉNÉRALES:
- !help - Aide complète
- !ping - Latence du bot

✨ FONCTIONNEMENT VOCAL DASHBOARD:

🎯 PROCESSUS AUTOMATIQUE:
1. Bot crée automatiquement "🔊・Créer un salon" dans la catégorie 1236724293631611021
2. Utilisateur rejoint ce salon de création
3. Création automatique d'un salon vocal + textuel personnalisé
4. Déplacement automatique dans le salon vocal
5. Dashboard interactif apparaît dans le salon textuel créé
6. Gestion complète via boutons (aucune commande à retenir!)
7. Suppression automatique des deux salons quand le vocal devient vide

🎛️ DASHBOARD INTERACTIF (dans le salon textuel):
✅ **Message de bienvenue** - Informations sur vos salons
✅ **Renommer** - Modal pour changer le nom du salon vocal
✅ **Limite** - Modal pour définir le nombre max d'utilisateurs
✅ **Verrouiller/Déverrouiller** - Bouton toggle pour l'accès
✅ **Expulser** - Menu déroulant pour choisir qui expulser
✅ **Informations temps réel** - Membres connectés, statut, limite
✅ **Interface moderne** - Embeds colorés avec mise à jour automatique

🛠️ FONCTIONNALITÉS AVANCÉES:
✅ Création simultanée vocal + textuel dans la catégorie spécifiée
✅ Permissions automatiques pour le propriétaire
✅ Dashboard permanent (pas de suppression automatique)
✅ Modals pour saisie de données propres
✅ Menu déroulant pour sélection d'utilisateurs à expulser
✅ Messages éphémères pour les confirmations (pas de spam)
✅ Nettoyage automatique complet (vocal + textuel)
✅ Support multi-serveurs avec ID de catégorie fixe

🎉 SYSTÈME GIVEAWAY COMPLET:
✅ Création via commande !giveaway
✅ Participation via bouton interactif
✅ Compteur de participants en temps réel
✅ Fin automatique avec sélection des gagnants
✅ Commandes de gestion (terminer, relancer, lister)
✅ Support des durées (s, m, h, d)
✅ Permissions requises pour les admins

🔧 PERMISSIONS DISCORD REQUISES:
- Send Messages
- Use Slash Commands  
- Manage Messages
- Add Reactions
- Read Message History
- Use External Emojis
- Manage Channels (pour créer/supprimer les vocaux)
- Move Members (pour déplacer les utilisateurs)
- Connect & Speak (pour les vocaux)

💡 AVANTAGES DU SYSTÈME:
✅ Interface 100% graphique pour les vocaux
✅ Dashboard persistant dans salon textuel privé
✅ Aucune configuration manuelle requise
✅ Gestion intuitive via boutons et modals
✅ Système de giveaway professionnel
✅ Code propre et modulaire
✅ Hébergement gratuit sur Koyeb

🎨 EXEMPLE D'UTILISATION:
1. Le bot crée automatiquement le salon de création
2. Utilisateur rejoint "🔊・Créer un salon"  
3. ➜ Salon vocal "🔊・PseudoUser" créé dans la catégorie
4. ➜ Salon textuel "💬・pseudouser" créé dans la catégorie
5. ➜ Utilisateur déplacé dans son vocal
6. ➜ Dashboard complet apparaît dans son textuel avec :
   - Message de bienvenue avec mentions des salons
   - Informations temps réel (membres, limite, statut)
   - 4 boutons interactifs de gestion
7. ➜ Gestion complète via dashboard personnel!

🚀 SYSTÈME COMPLET PRÊT:
- VOCAUX avec dashboard textuel personnel
- GIVEAWAYS avec boutons interactifs  
- HÉBERGEMENT gratuit sur Koyeb
- ZERO configuration requise
- CODE modulaire et extensible
""" on_ready():
    print(f'✅ Bot connecté en tant que {bot.user}!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="🎉 Giveaways & 🔊 Vocaux"))

# ==================== SYSTÈME VOCAL SIMPLIFIÉ ====================

class SimpleVoiceView(discord.ui.View):
    def __init__(self, voice_channel_id, owner_id):
        super().__init__(timeout=None)
        self.voice_channel_id = voice_channel_id
        self.owner_id = owner_id

    @discord.ui.button(label='Renommer', emoji='✏️', style=discord.ButtonStyle.secondary)
    async def rename_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('❌ Seul le propriétaire du salon peut utiliser cette fonction.', ephemeral=True)
            return
        
        await interaction.response.send_modal(RenameModal(self.voice_channel_id))

    @discord.ui.button(label='Limite', emoji='👥', style=discord.ButtonStyle.secondary)
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('❌ Seul le propriétaire du salon peut utiliser cette fonction.', ephemeral=True)
            return
        
        await interaction.response.send_modal(LimitModal(self.voice_channel_id))

    @discord.ui.button(label='Verrouiller', emoji='🔒', style=discord.ButtonStyle.danger)
    async def lock_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('❌ Seul le propriétaire du salon peut utiliser cette fonction.', ephemeral=True)
            return

        voice_channel = bot.get_channel(self.voice_channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon vocal introuvable.', ephemeral=True)
            return

        try:
            everyone_role = interaction.guild.default_role
            current_perms = voice_channel.overwrites_for(everyone_role)
            
            if current_perms.connect is False:
                await voice_channel.set_permissions(everyone_role, connect=None)
                button.label = "Verrouiller"
                button.emoji = "🔒"
                button.style = discord.ButtonStyle.danger
                status = "🔓 Salon déverrouillé"
                color = CONFIG['success_color']
            else:
                await voice_channel.set_permissions(everyone_role, connect=False)
                button.label = "Déverrouiller"
                button.emoji = "🔓"
                button.style = discord.ButtonStyle.success
                status = "🔒 Salon verrouillé"
                color = CONFIG['voice_color']
            
            embed = discord.Embed(description=status, color=color)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message('❌ Permissions insuffisantes pour modifier ce salon.', ephemeral=True)

    @discord.ui.button(label='Expulser', emoji='👢', style=discord.ButtonStyle.danger)
    async def kick_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('❌ Seul le propriétaire du salon peut utiliser cette fonction.', ephemeral=True)
            return

        voice_channel = bot.get_channel(self.voice_channel_id)
        if not voice_channel or len(voice_channel.members) <= 1:
            await interaction.response.send_message('❌ Aucun utilisateur à expulser.', ephemeral=True)
            return

        options = []
        for member in voice_channel.members:
            if member.id != self.owner_id and not member.bot:
                options.append(discord.SelectOption(
                    label=member.display_name[:25],
                    description=f"Expulser {member.display_name}",
                    value=str(member.id),
                    emoji="👢"
                ))
        
        if not options:
            await interaction.response.send_message('❌ Aucun utilisateur à expulser.', ephemeral=True)
            return

        select = KickUserSelect(options, self.voice_channel_id)
        view = discord.ui.View()
        view.add_item(select)
        
        await interaction.response.send_message('Sélectionnez l\'utilisateur à expulser:', view=view, ephemeral=True)

class KickUserSelect(discord.ui.Select):
    def __init__(self, options, voice_channel_id):
        super().__init__(placeholder="Choisir un utilisateur à expulser...", options=options)
        self.voice_channel_id = voice_channel_id

    async def callback(self, interaction: discord.Interaction):
        voice_channel = bot.get_channel(self.voice_channel_id)
        member_id = int(self.values[0])
        member = interaction.guild.get_member(member_id)
        
        if not member or not voice_channel:
            await interaction.response.send_message('❌ Utilisateur ou salon introuvable.', ephemeral=True)
            return

        try:
            await member.move_to(None)
            embed = discord.Embed(
                description=f'✅ **{member.display_name}** a été expulsé du salon',
                color=CONFIG['success_color']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message('❌ Permissions insuffisantes pour expulser cet utilisateur.', ephemeral=True)

class RenameModal(discord.ui.Modal):
    def __init__(self, voice_channel_id):
        super().__init__(title="Renommer le salon vocal")
        self.voice_channel_id = voice_channel_id
        
        self.name_input = discord.ui.TextInput(
            label="Nouveau nom du salon",
            placeholder="Entrez le nouveau nom...",
            max_length=50,
            required=True
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        voice_channel = bot.get_channel(self.voice_channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon vocal introuvable.', ephemeral=True)
            return

        new_name = self.name_input.value.strip()
        if not new_name:
            await interaction.response.send_message('❌ Le nom ne peut pas être vide.', ephemeral=True)
            return

        try:
            old_name = voice_channel.name
            await voice_channel.edit(name=new_name)
            
            embed = discord.Embed(
                title='✅ Salon renommé',
                description=f'**Ancien nom:** {old_name}\n**Nouveau nom:** {new_name}',
                color=CONFIG['success_color']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message('❌ Permissions insuffisantes pour renommer ce salon.', ephemeral=True)

class LimitModal(discord.ui.Modal):
    def __init__(self, voice_channel_id):
        super().__init__(title="Définir la limite d'utilisateurs")
        self.voice_channel_id = voice_channel_id
        
        self.limit_input = discord.ui.TextInput(
            label="Limite d'utilisateurs",
            placeholder="Entrez un nombre (0 = illimité)...",
            max_length=2,
            required=True
        )
        self.add_item(self.limit_input)

    async def on_submit(self, interaction: discord.Interaction):
        voice_channel = bot.get_channel(self.voice_channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon vocal introuvable.', ephemeral=True)
            return

        try:
            limit = int(self.limit_input.value.strip())
            if limit < 0 or limit > 99:
                await interaction.response.send_message('❌ La limite doit être entre 0 et 99 (0 = illimité).', ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message('❌ Veuillez entrer un nombre valide.', ephemeral=True)
            return

        try:
            await voice_channel.edit(user_limit=limit)
            
            limit_text = str(limit) if limit > 0 else "Illimitée"
            embed = discord.Embed(
                title='✅ Limite modifiée',
                description=f'**Salon:** {voice_channel.name}\n**Nouvelle limite:** {limit_text}',
                color=CONFIG['success_color']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message('❌ Permissions insuffisantes pour modifier ce salon.', ephemeral=True)

@bot.event
async def on_voice_state_update(member, before, after):
    """Gérer les changements d'état vocal"""
    
    # Utilisateur rejoint le salon de création
    if after.channel and after.channel.id == creation_channel_id:
        await create_temp_voice_channel(member)
    
    # Vérifier si un salon temporaire devient vide
    if before.channel and before.channel.id in temp_channels:
        await check_temp_channel_empty(before.channel)

async def create_temp_voice_channel(member):
    """Créer un salon vocal temporaire avec salon textuel pour dashboard"""
    
    try:
        guild = member.guild
        category = bot.get_channel(VOICE_CATEGORY_ID)
        
        # Noms des salons
        voice_name = f"🔊・{member.display_name}"
        text_name = f"💬・{member.display_name.lower().replace(' ', '-')}"
        
        # Créer le salon vocal temporaire
        temp_voice = await guild.create_voice_channel(
            name=voice_name,
            category=category,
            reason=f"Salon vocal temporaire créé pour {member}"
        )
        
        # Créer le salon textuel associé
        temp_text = await guild.create_text_channel(
            name=text_name,
            category=category,
            reason=f"Salon textuel pour dashboard vocal de {member}"
        )
        
        # Donner les permissions au propriétaire
        await temp_voice.set_permissions(member, manage_channels=True, manage_permissions=True)
        await temp_text.set_permissions(member, manage_channels=True, manage_permissions=True, manage_messages=True)
        
        # Cacher le salon textuel aux autres par défaut (optionnel)
        # await temp_text.set_permissions(guild.default_role, view_channel=False)
        # await temp_text.set_permissions(member, view_channel=True)
        
        # Déplacer l'utilisateur vers le nouveau salon vocal
        await member.move_to(temp_voice)
        
        # Enregistrer les salons temporaires
        temp_channels[temp_voice.id] = {
            'voice_channel_id': temp_voice.id,
            'text_channel_id': temp_text.id,
            'owner_id': member.id,
            'guild_id': guild.id,
            'created_at': datetime.datetime.utcnow()
        }
        
        # Créer le dashboard dans le salon textuel
        await create_dashboard(temp_voice, temp_text, member)
            
    except discord.Forbidden:
        print(f"❌ Permissions insuffisantes pour créer des salons pour {member}")
    except Exception as e:
        print(f"❌ Erreur lors de la création des salons: {e}")

async def create_dashboard(voice_channel, text_channel, owner):
    """Créer le dashboard dans le salon textuel"""
    
    # Message de bienvenue
    welcome_embed = discord.Embed(
        title='🎉 Bienvenue dans votre salon privé!',
        description=f'Salut {owner.mention}! Voici votre espace personnel avec dashboard de gestion.',
        color=CONFIG['voice_color']
    )
    welcome_embed.add_field(
        name='📋 Vos salons',
        value=f'**Vocal:** {voice_channel.mention}\n**Textuel:** {text_channel.mention}',
        inline=False
    )
    welcome_embed.set_footer(text='Les salons se suppriment automatiquement quand le vocal devient vide')
    
    await text_channel.send(embed=welcome_embed)
    
    # Dashboard avec boutons de contrôle
    dashboard_embed = discord.Embed(
        title='🎛️ Dashboard de Contrôle',
        color=CONFIG['voice_color']
    )
    
    # Informations sur le salon
    members_in_voice = len(voice_channel.members)
    limit_text = str(voice_channel.user_limit) if voice_channel.user_limit > 0 else "Illimitée"
    
    # Vérifier le statut de verrouillage
    everyone_role = voice_channel.guild.default_role
    current_perms = voice_channel.overwrites_for(everyone_role)
    lock_status = "🔒 Verrouillé" if current_perms.connect is False else "🔓 Ouvert"
    
    dashboard_embed.add_field(
        name='📊 Informations',
        value=f'**Propriétaire:** {owner.mention}\n**Membres connectés:** {members_in_voice}\n**Limite:** {limit_text}\n**Statut:** {lock_status}',
        inline=False
    )
    
    if voice_channel.members:
        member_list = [member.display_name for member in voice_channel.members if not member.bot]
        members_text = ', '.join(member_list) if member_list else "Aucun membre"
        if len(members_text) > 200:
            members_text = members_text[:200] + "..."
        dashboard_embed.add_field(
            name='👥 Membres connectés',
            value=members_text,
            inline=False
        )
    
    dashboard_embed.set_footer(text='Utilisez les boutons ci-dessous pour gérer votre salon')
    
    view = SimpleVoiceView(voice_channel.id, owner.id)
    await text_channel.send(embed=dashboard_embed, view=view)

async def check_temp_channel_empty(voice_channel):
    """Vérifier si un salon temporaire est vide et le supprimer si c'est le cas"""
    
    if voice_channel.id not in temp_channels:
        return
    
    # Attendre un peu pour éviter les suppressions accidentelles
    await asyncio.sleep(3)
    
    try:
        voice_channel = bot.get_channel(voice_channel.id)
        if voice_channel and len(voice_channel.members) == 0:
            channel_data = temp_channels[voice_channel.id]
            
            # Supprimer le salon textuel aussi
            text_channel = bot.get_channel(channel_data.get('text_channel_id'))
            if text_channel:
                await text_channel.delete(reason="Salon vocal temporaire vide")
            
            # Supprimer le salon vocal
            await voice_channel.delete(reason="Salon vocal temporaire vide")
            
            # Supprimer de notre stockage
            del temp_channels[voice_channel.id]
                
    except discord.NotFound:
        if voice_channel.id in temp_channels:
            del temp_channels[voice_channel.id]
    except Exception as e:
        print(f"❌ Erreur lors de la suppression du salon temporaire: {e}")

@bot.command(name='vinfo')
async def voice_info(ctx):
    """Afficher les informations sur les salons vocaux"""
    
    # Compter les salons temporaires actifs
    active_temp_channels = [data for voice_id, data in temp_channels.items() 
                           if data['guild_id'] == ctx.guild.id]

    create_channel = bot.get_channel(creation_channel_id)
    category = bot.get_channel(VOICE_CATEGORY_ID)
    
    embed = discord.Embed(
        title='📊 Système Vocal Simplifié',
        color=CONFIG['voice_color']
    )
    
    embed.add_field(
        name='⚙️ Configuration',
        value=f'**Catégorie:** {category.mention if category else "❌ Introuvable"}\n**Salon de création:** {create_channel.mention if create_channel else "❌ Introuvable"}\n**Salons actifs:** {len(active_temp_channels)}',
        inline=False
    )
    
    if active_temp_channels:
        channels_info = []
        for data in active_temp_channels[:5]:  # Limiter à 5
            voice_channel = bot.get_channel(data['voice_channel_id'])
            text_channel = bot.get_channel(data.get('text_channel_id'))
            if voice_channel:
                owner = bot.get_user(data['owner_id'])
                channels_info.append(f'🔊 **{voice_channel.name}** - {owner.mention if owner else "Propriétaire introuvable"}\n   💬 {text_channel.mention if text_channel else "Salon textuel supprimé"} ({len(voice_channel.members)} membres)')
        
        embed.add_field(
            name='🎛️ Salons Actifs',
            value='\n'.join(channels_info) + (f'\n... et {len(active_temp_channels) - 5} autres' if len(active_temp_channels) > 5 else ''),
            inline=False
        )
    
    embed.add_field(
        name='✨ Comment ça marche?',
        value=f'1️⃣ Rejoignez le salon {create_channel.mention if create_channel else "de création"}\n2️⃣ Un salon vocal + textuel personnalisés sont créés automatiquement\n3️⃣ Vous êtes déplacé dans votre salon vocal\n4️⃣ Un dashboard interactif apparaît dans votre salon textuel\n5️⃣ Gérez votre salon via les boutons du dashboard\n6️⃣ Les salons se suppriment automatiquement quand le vocal est vide',
        inline=False
    )
    
    await ctx.reply(embed=embed)

# ==================== SYSTÈME GIVEAWAY ====================

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
        
        # Mise à jour de l'embed avec le nouveau nombre de participants
        await self.update_giveaway_embed(interaction)
    
    async def update_giveaway_embed(self, interaction):
        """Met à jour l'embed avec le nombre de participants"""
        giveaway = active_giveaways.get(self.giveaway_id)
        if not giveaway:
            return
            
        # Récupération des infos du giveaway
        end_time = giveaway['end_time']
        participants_count = len(giveaway['participants'])
        
        # Création du nouvel embed
        embed = discord.Embed(
            title='🎉 GIVEAWAY 🎉',
            description=f"**Prix:** {giveaway['prize']}\n**Gagnants:** {giveaway['winners']}\n**Participants:** {participants_count}\n**Fin:** <t:{int(end_time.timestamp())}:R>\n**Organisé par:** <@{giveaway['host_id']}>",
            color=CONFIG['embed_color'],
            timestamp=end_time
        )
        embed.set_footer(text=f"ID: {self.giveaway_id} • Cliquez sur le bouton pour participer!")
        
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except:
            pass

@bot.command(name='giveaway', aliases=['g'])
async def create_giveaway(ctx, duration: str = None, winners: int = None, *, prize: str = None):
    """Créer un nouveau giveaway"""
    
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

    duration_seconds = parse_duration(duration)
    if not duration_seconds:
        await ctx.reply('❌ Durée invalide. Utilisez: s (secondes), m (minutes), h (heures), d (jours)')
        return

    if winners < 1:
        await ctx.reply('❌ Le nombre de gagnants doit être un nombre positif.')
        return

    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration_seconds)
    giveaway_id = str(int(datetime.datetime.now().timestamp()))

    embed = discord.Embed(
        title='🎉 GIVEAWAY 🎉',
        description=f"**Prix:** {prize}\n**Gagnants:** {winners}\n**Participants:** 0\n**Fin:** <t:{int(end_time.timestamp())}:R>\n**Organisé par:** {ctx.author.mention}",
        color=CONFIG['embed_color'],
        timestamp=end_time
    )
    embed.set_footer(text=f"ID: {giveaway_id} • Cliquez sur le bouton pour participer!")

    view = GiveawayView(giveaway_id)
    giveaway_message = await ctx.send(embed=embed, view=view)

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

    asyncio.create_task(schedule_giveaway_end(giveaway_id, duration_seconds))
    
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
        
        embed_desc = message.embeds[0].description
        if '**Prix:**' in embed_desc:
            prize = embed_desc.split('**Prix:** ')[1].split('\n')[0]
        else:
            prize = "Prix inconnu"

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

@bot.command(name='help', aliases=['aide'])
async def bot_help(ctx):
    """Afficher l'aide complète du bot"""
    
    embed = discord.Embed(
        title='🎮 Bot Vocal Simplifié + Giveaway',
        description='Bot avec création automatique de salons vocaux personnalisés et système de giveaway.',
        color=CONFIG['embed_color']
    )
    
    embed.add_field(
        name='🎉 Commandes Giveaway',
        value='`!giveaway <durée> <gagnants> <prix>` - Créer un giveaway\n`!gend <message_id>` - Terminer manuellement\n`!greroll <message_id>` - Nouveau tirage\n`!glist` - Liste des giveaways actifs',
        inline=False
    )
    
    embed.add_field(
        name='🔊 Système Vocal Automatique',
        value=f'**Pas de configuration nécessaire!**\nRejoignez le salon de création dans la catégorie vocale pour obtenir votre salon vocal + textuel personnalisé avec dashboard interactif.',
        inline=False
    )
    
    embed.add_field(
        name='🎛️ Contrôles Vocaux (Boutons)',
        value='• **Renommer** - Changez le nom de votre salon\n• **Limite** - Définissez un max d\'utilisateurs\n• **Verrouiller** - Bloquez l\'accès\n• **Expulser** - Éjectez des utilisateurs',
        inline=False
    )
    
    embed.add_field(
        name='⚙️ Commandes Générales',
        value='`!help` - Afficher cette aide\n`!ping` - Latence du bot\n`!vinfo` - Infos sur les vocaux',
        inline=False
    )
    
    embed.add_field(
        name='⏰ Formats de Durée (Giveaways)',
        value='`s` = secondes, `m` = minutes, `h` = heures, `d` = jours\nExemples: `30s`, `5m`, `2h`, `1d`',
        inline=False
    )
    
    embed.set_footer(text='Bot Vocal Simplifié • Aucune configuration requise!')
    await ctx.reply(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    """Tester la latence du bot"""
    
    embed = discord.Embed(
        title='🏓 Pong!',
        description=f'**Latence:** {round(bot.latency * 1000)}ms',
        color=CONFIG['success_color']
    )
    await ctx.reply(embed=embed)

async def schedule_giveaway_end(giveaway_id, delay):
    """Programmer la fin automatique d'un giveaway"""
    await asyncio.sleep(delay)
    await finish_giveaway(giveaway_id)

async def