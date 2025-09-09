# Bot Discord Giveaway + Vocal Dashboard en Python
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
import json

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.reactions = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Stockage des giveaways actifs
active_giveaways = {}

# Stockage des salons vocaux temporaires et leurs salons texte
temp_channels = {}
voice_config = {}

# Configuration
CONFIG = {
    'prefix': '!',
    'embed_color': 0x00ff00,
    'admin_role': 'Admin',
    'error_color': 0xff0000,
    'success_color': 0x00ff00,
    'voice_color': 0x3498db
}

@bot.event
async def on_ready():
    print(f'✅ Bot connecté en tant que {bot.user}!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="🎉 Giveaways & 🔊 Dashboard Vocal"))
    
    # Nettoyer les anciens salons vocaux temporaires au démarrage
    await cleanup_temp_channels()

# ==================== DASHBOARD VOCAL INTERACTIF ====================

class VoiceDashboardView(discord.ui.View):
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
                # Salon verrouillé, on déverrouille
                await voice_channel.set_permissions(everyone_role, connect=None)
                button.label = "Verrouiller"
                button.emoji = "🔒"
                button.style = discord.ButtonStyle.danger
                status = "🔓 Salon déverrouillé"
                color = CONFIG['success_color']
            else:
                # Salon déverrouillé, on verrouille
                await voice_channel.set_permissions(everyone_role, connect=False)
                button.label = "Déverrouiller"
                button.emoji = "🔓"
                button.style = discord.ButtonStyle.success
                status = "🔒 Salon verrouillé"
                color = CONFIG['voice_color']
            
            # Mettre à jour le message du dashboard
            await self.update_dashboard(interaction, voice_channel)
            
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

        # Créer un menu de sélection avec les membres du salon
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

    @discord.ui.button(label='Actualiser', emoji='🔄', style=discord.ButtonStyle.primary)
    async def refresh_dashboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = bot.get_channel(self.voice_channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon vocal introuvable.', ephemeral=True)
            return

        await self.update_dashboard(interaction, voice_channel)
        await interaction.response.send_message('✅ Dashboard actualisé!', ephemeral=True)

    async def update_dashboard(self, interaction, voice_channel):
        """Mettre à jour le message du dashboard"""
        try:
            # Vérifier le statut de verrouillage
            everyone_role = interaction.guild.default_role
            current_perms = voice_channel.overwrites_for(everyone_role)
            is_locked = current_perms.connect is False
            
            # Mettre à jour le bouton de verrouillage
            for item in self.children:
                if item.emoji and item.emoji.name in ['🔒', '🔓']:
                    if is_locked:
                        item.label = "Déverrouiller"
                        item.emoji = "🔓"
                        item.style = discord.ButtonStyle.success
                    else:
                        item.label = "Verrouiller"
                        item.emoji = "🔒"
                        item.style = discord.ButtonStyle.danger
                    break

            # Créer l'embed mis à jour
            embed = create_dashboard_embed(voice_channel, self.owner_id)
            
            await interaction.edit_original_response(embed=embed, view=self)
        except:
            pass

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
            
            # Mettre à jour le dashboard
            await update_dashboard_message(voice_channel)
            
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
            
            # Mettre à jour le dashboard
            await update_dashboard_message(voice_channel)
            
        except discord.Forbidden:
            await interaction.response.send_message('❌ Permissions insuffisantes pour modifier ce salon.', ephemeral=True)

def create_dashboard_embed(voice_channel, owner_id):
    """Créer l'embed du dashboard"""
    
    # Informations sur le salon
    member_list = [member.display_name for member in voice_channel.members if not member.bot]
    members_text = ', '.join(member_list) if member_list else "Aucun membre"
    
    # Limite d'utilisateurs
    limit_text = str(voice_channel.user_limit) if voice_channel.user_limit > 0 else "Illimitée"
    
    # Statut de verrouillage
    everyone_role = voice_channel.guild.default_role
    current_perms = voice_channel.overwrites_for(everyone_role)
    lock_status = "🔒 Verrouillé" if current_perms.connect is False else "🔓 Ouvert"
    
    embed = discord.Embed(
        title=f'🎛️ Dashboard - {voice_channel.name}',
        description=f'Gérez votre salon vocal avec les boutons ci-dessous',
        color=CONFIG['voice_color'],
        timestamp=datetime.datetime.utcnow()
    )
    
    embed.add_field(
        name='📊 Informations',
        value=f'**Propriétaire:** <@{owner_id}>\n**Membres connectés:** {len(voice_channel.members)}\n**Limite:** {limit_text}\n**Statut:** {lock_status}',
        inline=False
    )
    
    if member_list:
        # Limiter la liste des membres pour éviter les embeds trop longs
        if len(members_text) > 200:
            members_text = members_text[:200] + "..."
        embed.add_field(
            name='👥 Membres connectés',
            value=members_text,
            inline=False
        )
    
    embed.set_footer(text='Utilisez les boutons pour gérer votre salon • Dashboard Vocal')
    
    return embed

async def update_dashboard_message(voice_channel):
    """Mettre à jour le message du dashboard d'un salon"""
    
    channel_data = temp_channels.get(voice_channel.id)
    if not channel_data or not channel_data.get('text_channel_id'):
        return

    text_channel = bot.get_channel(channel_data['text_channel_id'])
    if not text_channel:
        return

    try:
        # Récupérer le message du dashboard
        dashboard_message = await text_channel.fetch_message(channel_data['dashboard_message_id'])
        
        # Créer l'embed mis à jour
        embed = create_dashboard_embed(voice_channel, channel_data['owner_id'])
        
        # Mettre à jour le message
        await dashboard_message.edit(embed=embed)
        
    except (discord.NotFound, KeyError):
        # Le message n'existe plus, on en crée un nouveau
        await create_dashboard_message(voice_channel, text_channel, channel_data['owner_id'])

async def create_dashboard_message(voice_channel, text_channel, owner_id):
    """Créer le message de dashboard dans le salon textuel"""
    
    embed = create_dashboard_embed(voice_channel, owner_id)
    view = VoiceDashboardView(voice_channel.id, owner_id)
    
    try:
        dashboard_message = await text_channel.send(embed=embed, view=view)
        
        # Sauvegarder l'ID du message
        if voice_channel.id in temp_channels:
            temp_channels[voice_channel.id]['dashboard_message_id'] = dashboard_message.id
        
        return dashboard_message
        
    except discord.Forbidden:
        print(f"❌ Impossible d'envoyer le dashboard dans {text_channel.name}")

# ==================== SYSTÈME VOCAL PERSONNALISÉ ====================

@bot.command(name='vsetup', aliases=['voice-setup'])
async def voice_setup(ctx, create_channel: discord.VoiceChannel = None, category: discord.CategoryChannel = None):
    """Configurer le salon de création de vocaux personnalisés"""
    
    if not ctx.author.guild_permissions.manage_channels:
        await ctx.reply('❌ Vous devez avoir la permission "Gérer les salons" pour utiliser cette commande.')
        return

    if not create_channel:
        embed = discord.Embed(
            title="❌ Usage incorrect",
            description="Usage: `!vsetup #salon-vocal [#catégorie]`\nExemple: `!vsetup #Créer-un-salon #Salons-Temporaires`",
            color=CONFIG['error_color']
        )
        await ctx.reply(embed=embed)
        return

    # Si aucune catégorie n'est spécifiée, utiliser celle du salon de création
    if not category:
        category = create_channel.category

    # Sauvegarder la configuration
    voice_config[ctx.guild.id] = {
        'create_channel_id': create_channel.id,
        'category_id': category.id if category else None,
        'temp_channels': []
    }

    embed = discord.Embed(
        title='✅ Configuration Vocal Dashboard Réussie',
        description=f'**Salon de création:** {create_channel.mention}\n**Catégorie:** {category.mention if category else "Aucune"}\n\nLes utilisateurs peuvent maintenant rejoindre ce salon pour créer automatiquement un salon vocal avec dashboard de gestion!',
        color=CONFIG['success_color']
    )
    embed.add_field(
        name='Comment ça marche?',
        value='1️⃣ L\'utilisateur rejoint le salon de création\n2️⃣ Un salon vocal + textuel sont créés automatiquement\n3️⃣ L\'utilisateur est déplacé dans son salon vocal\n4️⃣ Un dashboard interactif apparaît dans le salon textuel\n5️⃣ Gestion complète via boutons (renommer, limite, verrouiller, expulser)\n6️⃣ Les salons se suppriment quand ils deviennent vides',
        inline=False
    )
    await ctx.reply(embed=embed)

@bot.event
async def on_voice_state_update(member, before, after):
    """Gérer les changements d'état vocal"""
    
    guild_config = voice_config.get(member.guild.id)
    if not guild_config:
        return

    # Utilisateur rejoint le salon de création
    if after.channel and after.channel.id == guild_config['create_channel_id']:
        await create_temp_voice_channel(member, guild_config)
    
    # Vérifier si un salon temporaire devient vide
    if before.channel and before.channel.id in temp_channels:
        await check_temp_channel_empty(before.channel)

async def create_temp_voice_channel(member, guild_config):
    """Créer un salon vocal temporaire avec dashboard pour un utilisateur"""
    
    try:
        guild = member.guild
        category = bot.get_channel(guild_config['category_id']) if guild_config['category_id'] else None
        
        # Nom par défaut du salon
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
            reason=f"Salon textuel pour le vocal de {member}"
        )
        
        # Donner les permissions au propriétaire
        await temp_voice.set_permissions(member, manage_channels=True, manage_permissions=True)
        await temp_text.set_permissions(member, manage_channels=True, manage_permissions=True, manage_messages=True)
        
        # Cacher le salon textuel des autres utilisateurs par défaut
        await temp_text.set_permissions(guild.default_role, view_channel=False)
        await temp_text.set_permissions(member, view_channel=True)
        
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
        await create_dashboard_message(temp_voice, temp_text, member.id)
        
        # Message de bienvenue dans le salon textuel
        welcome_embed = discord.Embed(
            title='🎉 Bienvenue dans votre salon privé!',
            description=f'Salut {member.mention}! Voici votre espace personnel avec dashboard de gestion.',
            color=CONFIG['voice_color']
        )
        welcome_embed.add_field(
            name='📋 Votre salon',
            value=f'**Vocal:** {temp_voice.mention}\n**Textuel:** {temp_text.mention}',
            inline=False
        )
        welcome_embed.add_field(
            name='🎛️ Dashboard',
            value='Utilisez les boutons du dashboard ci-dessus pour gérer votre salon:\n• Renommer votre salon\n• Définir une limite d\'utilisateurs\n• Verrouiller/Déverrouiller l\'accès\n• Expulser des utilisateurs\n• Actualiser les informations',
            inline=False
        )
        welcome_embed.set_footer(text='Les salons se suppriment automatiquement quand ils sont vides')
        
        await temp_text.send(embed=welcome_embed)
            
    except discord.Forbidden:
        print(f"❌ Permissions insuffisantes pour créer des salons pour {member}")
    except Exception as e:
        print(f"❌ Erreur lors de la création des salons: {e}")

async def check_temp_channel_empty(voice_channel):
    """Vérifier si un salon temporaire est vide et le supprimer si c'est le cas"""
    
    if voice_channel.id not in temp_channels:
        return
    
    # Attendre un peu pour éviter les suppressions accidentelles lors de déconnexions rapides
    await asyncio.sleep(3)
    
    # Revérifier que le salon existe encore et qu'il est vide
    try:
        voice_channel = bot.get_channel(voice_channel.id)
        if voice_channel and len(voice_channel.members) == 0:
            channel_data = temp_channels[voice_channel.id]
            
            # Supprimer le salon textuel aussi
            text_channel = bot.get_channel(channel_data['text_channel_id'])
            if text_channel:
                await text_channel.delete(reason="Salon vocal temporaire vide")
            
            # Supprimer le salon vocal
            await voice_channel.delete(reason="Salon vocal temporaire vide")
            
            # Supprimer de notre stockage
            del temp_channels[voice_channel.id]
                
    except discord.NotFound:
        # Le salon a déjà été supprimé
        if voice_channel.id in temp_channels:
            del temp_channels[voice_channel.id]
    except Exception as e:
        print(f"❌ Erreur lors de la suppression des salons temporaires: {e}")

async def cleanup_temp_channels():
    """Nettoyer les anciens salons vocaux temporaires au démarrage"""
    
    print("🧹 Nettoyage des anciens salons temporaires...")
    
    channels_to_remove = []
    for voice_channel_id, data in temp_channels.items():
        try:
            voice_channel = bot.get_channel(voice_channel_id)
            text_channel = bot.get_channel(data.get('text_channel_id'))
            
            if not voice_channel:
                channels_to_remove.append(voice_channel_id)
                if text_channel:
                    await text_channel.delete(reason="Nettoyage - salon vocal introuvable")
            elif len(voice_channel.members) == 0:
                if text_channel:
                    await text_channel.delete(reason="Nettoyage - salon vide au démarrage")
                await voice_channel.delete(reason="Nettoyage - salon vide au démarrage")
                channels_to_remove.append(voice_channel_id)
        except:
            channels_to_remove.append(voice_channel_id)
    
    for channel_id in channels_to_remove:
        if channel_id in temp_channels:
            del temp_channels[channel_id]
    
    print(f"✅ {len(channels_to_remove)} salons temporaires nettoyés.")

@bot.command(name='vinfo')
async def voice_info(ctx):
    """Afficher les informations sur les salons vocaux temporaires"""
    
    guild_config = voice_config.get(ctx.guild.id)
    if not guild_config:
        await ctx.reply('❌ Le système vocal dashboard n\'est pas configuré sur ce serveur. Utilisez `!vsetup` pour le configurer.')
        return

    # Compter les salons temporaires actifs
    active_temp_channels = [data for voice_id, data in temp_channels.items() 
                           if data['guild_id'] == ctx.guild.id]

    create_channel = bot.get_channel(guild_config['create_channel_id'])
    category = bot.get_channel(guild_config['category_id']) if guild_config['category_id'] else None
    
    embed = discord.Embed(
        title='📊 Informations Vocal Dashboard',
        color=CONFIG['voice_color']
    )
    
    embed.add_field(
        name='⚙️ Configuration',
        value=f'**Salon de création:** {create_channel.mention if create_channel else "❌ Introuvable"}\n**Catégorie:** {category.mention if category else "Aucune"}\n**Salons actifs:** {len(active_temp_channels)}',
        inline=False
    )
    
    if active_temp_channels:
        channels_info = []
        for data in active_temp_channels[:3]:  # Limiter à 3 pour éviter les embeds trop longs
            voice_channel = bot.get_channel(data['voice_channel_id'])
            text_channel = bot.get_channel(data['text_channel_id'])
            if voice_channel:
                owner = bot.get_user(data['owner_id'])
                channels_info.append(f'🔊 **{voice_channel.name}** - {owner.mention if owner else "Propriétaire introuvable"}\n   💬 {text_channel.mention if text_channel else "Salon textuel supprimé"} ({len(voice_channel.members)} membres)')
        
        embed.add_field(
            name='🎛️ Salons Dashboard Actifs',
            value='\n'.join(channels_info) + (f'\n... et {len(active_temp_channels) - 3} autres' if len(active_temp_channels) > 3 else ''),
            inline=False
        )
    
    embed.add_field(
        name='✨ Fonctionnalités Dashboard',
        value='• 🎛️ Dashboard interactif avec boutons\n• ✏️ Renommage en temps réel\n• 👥 Gestion des limites d\'utilisateurs\n• 🔒 Verrouillage/Déverrouillage\n• 👢 Expulsion d\'utilisateurs\n• 🔄 Actualisation automatique\n• 🗑️ Suppression automatique',
        inline=False
    )
    
    await ctx.reply(embed=embed)

# ==================== SYSTÈME GIVEAWAY (code existant) ====================

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
            giveaway['participants'].add(user_i