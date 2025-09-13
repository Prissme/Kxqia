# Bot Discord - Système Vocal Personnalisé (Style DraftBot)
# Système complet de salons vocaux temporaires avec interface moderne
# Requirements: discord.py
# Installation: pip install discord.py

import discord
from discord.ext import commands, tasks
import asyncio
import datetime
import json
import os

# Configuration moderne du bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Stockage des données (en mémoire)
voice_config = {}  # Configuration par serveur
temp_channels = {}  # Salons temporaires actifs
user_settings = {}  # Paramètres utilisateur

# Configuration design moderne
CONFIG = {
    'colors': {
        'primary': 0x5865F2,      # Discord Blurple
        'success': 0x57F287,      # Vert moderne
        'error': 0xED4245,        # Rouge moderne
        'warning': 0xFEE75C,      # Jaune moderne
        'voice': 0x9B59B6         # Violet pour le vocal
    },
    'emojis': {
        'voice': '🔊',
        'settings': '⚙️',
        'users': '👥',
        'lock': '🔒',
        'unlock': '🔓',
        'kick': '👢',
        'rename': '✏️',
        'crown': '👑',
        'info': 'ℹ️'
    },
    'limits': {
        'max_channels_per_guild': 50,
        'max_channel_name_length': 100,
        'channel_cleanup_delay': 5
    }
}

@bot.event
async def on_ready():
    print(f'🔊 {bot.user} est connecté!')
    print(f'📊 Présent sur {len(bot.guilds)} serveur(s)')
    
    # Démarrer le nettoyage automatique
    cleanup_empty_channels.start()
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening, 
            name=f"🔊 Vocaux sur {len(bot.guilds)} serveurs"
        )
    )
    
    # Créer automatiquement les salons de création
    await setup_all_guilds()

async def setup_all_guilds():
    """Configuration automatique pour tous les serveurs"""
    for guild in bot.guilds:
        await auto_setup_guild(guild)

async def auto_setup_guild(guild):
    """Configuration automatique d'un serveur"""
    if guild.id in voice_config:
        return  # Déjà configuré
        
    try:
        # Chercher ou créer la catégorie
        category = discord.utils.get(guild.categories, name="🔊 Salons Vocaux")
        if not category:
            category = await guild.create_category("🔊 Salons Vocaux")
        
        # Chercher ou créer le salon de création
        creation_channel = discord.utils.get(guild.voice_channels, name="➕ Créer un salon")
        if not creation_channel:
            creation_channel = await guild.create_voice_channel(
                "➕ Créer un salon",
                category=category
            )
        
        # Sauvegarder la configuration
        voice_config[guild.id] = {
            'category_id': category.id,
            'creation_channel_id': creation_channel.id,
            'temp_channels': [],
            'auto_setup': True
        }
        
        print(f"✅ Configuration automatique: {guild.name}")
        
    except discord.Forbidden:
        print(f"❌ Permissions insuffisantes sur: {guild.name}")

@bot.event
async def on_guild_join(guild):
    """Configuration automatique lors de l'ajout à un nouveau serveur"""
    await auto_setup_guild(guild)

# ==================== SYSTÈME VOCAL MODERNE ====================

class VoiceControlPanel(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.owner_id = owner_id

    @discord.ui.button(
        label='Renommer',
        emoji='✏️',
        style=discord.ButtonStyle.secondary,
        custom_id='rename_channel'
    )
    async def rename_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
            
        modal = RenameModal(self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label='Limite',
        emoji='👥',
        style=discord.ButtonStyle.secondary,
        custom_id='set_limit'
    )
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
            
        modal = LimitModal(self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label='Verrouiller',
        emoji='🔒',
        style=discord.ButtonStyle.danger,
        custom_id='lock_channel'
    )
    async def lock_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
            
        await self.toggle_lock(interaction, button)

    @discord.ui.button(
        label='Expulser',
        emoji='👢',
        style=discord.ButtonStyle.danger,
        custom_id='kick_user'
    )
    async def kick_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
            
        await self.show_kick_menu(interaction)

    @discord.ui.button(
        label='Inviter',
        emoji='📨',
        style=discord.ButtonStyle.success,
        custom_id='invite_user'
    )
    async def invite_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
            
        await self.show_invite_menu(interaction)

    async def check_owner(self, interaction):
        """Vérifier si l'utilisateur est le propriétaire"""
        if interaction.user.id != self.owner_id:
            embed = discord.Embed(
                description='❌ Seul le propriétaire du salon peut utiliser ce bouton',
                color=CONFIG['colors']['error']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    async def toggle_lock(self, interaction, button):
        """Verrouiller/Déverrouiller le salon"""
        voice_channel = bot.get_channel(self.channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon introuvable', ephemeral=True)
            return

        try:
            everyone_role = interaction.guild.default_role
            current_perms = voice_channel.overwrites_for(everyone_role)
            
            if current_perms.connect is False:
                # Déverrouiller
                await voice_channel.set_permissions(everyone_role, connect=None)
                button.label = "Verrouiller"
                button.emoji = "🔒"
                button.style = discord.ButtonStyle.danger
                status = "🔓 Salon déverrouillé"
                color = CONFIG['colors']['success']
            else:
                # Verrouiller
                await voice_channel.set_permissions(everyone_role, connect=False)
                button.label = "Déverrouiller"
                button.emoji = "🔓"
                button.style = discord.ButtonStyle.success
                status = "🔒 Salon verrouillé"
                color = CONFIG['colors']['voice']
            
            embed = discord.Embed(description=status, color=color)
            await interaction.response.edit_message(embed=await self.create_panel_embed(voice_channel), view=self)
            
        except discord.Forbidden:
            embed = discord.Embed(
                description='❌ Permissions insuffisantes',
                color=CONFIG['colors']['error']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def show_kick_menu(self, interaction):
        """Afficher le menu d'expulsion"""
        voice_channel = bot.get_channel(self.channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon introuvable', ephemeral=True)
            return

        kickable_members = [m for m in voice_channel.members if m.id != self.owner_id and not m.bot]
        
        if not kickable_members:
            embed = discord.Embed(
                description='❌ Aucun utilisateur à expulser',
                color=CONFIG['colors']['warning']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        options = []
        for member in kickable_members[:25]:  # Limite Discord
            options.append(discord.SelectOption(
                label=member.display_name[:100],
                description=f"Expulser {member.display_name}",
                value=str(member.id),
                emoji="👢"
            ))

        select = KickUserSelect(options, self.channel_id)
        view = discord.ui.View()
        view.add_item(select)
        
        embed = discord.Embed(
            title='👢 Expulser un utilisateur',
            description='Sélectionnez l\'utilisateur à expulser:',
            color=CONFIG['colors']['warning']
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def show_invite_menu(self, interaction):
        """Afficher le menu d'invitation"""
        voice_channel = bot.get_channel(self.channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon introuvable', ephemeral=True)
            return

        # Utilisateurs non connectés au salon
        voice_members = [m.id for m in voice_channel.members]
        invitable_members = [m for m in interaction.guild.members 
                           if not m.bot and m.id not in voice_members]

        if not invitable_members:
            embed = discord.Embed(
                description='❌ Aucun utilisateur à inviter',
                color=CONFIG['colors']['warning']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Prendre les 25 premiers (limite Discord)
        options = []
        for member in invitable_members[:25]:
            options.append(discord.SelectOption(
                label=member.display_name[:100],
                description=f"Inviter {member.display_name}",
                value=str(member.id),
                emoji="📨"
            ))

        select = InviteUserSelect(options, self.channel_id, interaction.user.id)
        view = discord.ui.View()
        view.add_item(select)
        
        embed = discord.Embed(
            title='📨 Inviter un utilisateur',
            description='Sélectionnez l\'utilisateur à inviter:',
            color=CONFIG['colors']['success']
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def create_panel_embed(self, voice_channel):
        """Créer l'embed du panneau de contrôle"""
        owner = bot.get_user(self.owner_id)
        member_count = len(voice_channel.members)
        
        # Statut de verrouillage
        everyone_role = voice_channel.guild.default_role
        current_perms = voice_channel.overwrites_for(everyone_role)
        lock_status = "🔒 Verrouillé" if current_perms.connect is False else "🔓 Ouvert"
        
        # Limite d'utilisateurs
        limit = f"{voice_channel.user_limit}" if voice_channel.user_limit > 0 else "∞"
        
        embed = discord.Embed(
            title=f'🎛️ Panneau de Contrôle',
            description=f'**{voice_channel.name}**',
            color=CONFIG['colors']['voice']
        )
        
        embed.add_field(
            name=f'{CONFIG["emojis"]["crown"]} Propriétaire',
            value=owner.mention if owner else 'Inconnu',
            inline=True
        )
        
        embed.add_field(
            name=f'{CONFIG["emojis"]["users"]} Connectés',
            value=f'{member_count}/{limit}',
            inline=True
        )
        
        embed.add_field(
            name=f'{CONFIG["emojis"]["info"]} Statut',
            value=lock_status,
            inline=True
        )
        
        # Liste des membres connectés
        if voice_channel.members:
            member_list = []
            for member in voice_channel.members[:10]:  # Limite à 10
                if member.id == self.owner_id:
                    member_list.append(f'👑 **{member.display_name}**')
                else:
                    member_list.append(f'• {member.display_name}')
            
            members_text = '\n'.join(member_list)
            if len(voice_channel.members) > 10:
                members_text += f'\n... et {len(voice_channel.members) - 10} autres'
                
            embed.add_field(
                name=f'{CONFIG["emojis"]["users"]} Membres connectés',
                value=members_text,
                inline=False
            )
        
        embed.set_footer(text='Utilisez les boutons pour gérer votre salon')
        embed.timestamp = datetime.datetime.utcnow()
        
        return embed

class KickUserSelect(discord.ui.Select):
    def __init__(self, options, channel_id):
        super().__init__(placeholder="Choisir un utilisateur à expulser...", options=options)
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        voice_channel = bot.get_channel(self.channel_id)
        member_id = int(self.values[0])
        member = interaction.guild.get_member(member_id)
        
        if not member or not voice_channel:
            await interaction.response.send_message('❌ Utilisateur ou salon introuvable', ephemeral=True)
            return

        try:
            await member.move_to(None)
            embed = discord.Embed(
                description=f'✅ **{member.display_name}** a été expulsé du salon',
                color=CONFIG['colors']['success']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            embed = discord.Embed(
                description='❌ Permissions insuffisantes pour expulser cet utilisateur',
                color=CONFIG['colors']['error']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class InviteUserSelect(discord.ui.Select):
    def __init__(self, options, channel_id, inviter_id):
        super().__init__(placeholder="Choisir un utilisateur à inviter...", options=options)
        self.channel_id = channel_id
        self.inviter_id = inviter_id

    async def callback(self, interaction: discord.Interaction):
        voice_channel = bot.get_channel(self.channel_id)
        member_id = int(self.values[0])
        member = interaction.guild.get_member(member_id)
        inviter = interaction.guild.get_member(self.inviter_id)
        
        if not member or not voice_channel:
            await interaction.response.send_message('❌ Utilisateur ou salon introuvable', ephemeral=True)
            return

        try:
            # Envoyer l'invitation en MP
            invite_embed = discord.Embed(
                title='📨 Invitation Salon Vocal',
                description=f'**{inviter.display_name}** vous invite à rejoindre son salon vocal!\n\n**Salon:** {voice_channel.name}\n**Serveur:** {interaction.guild.name}',
                color=CONFIG['colors']['success']
            )
            
            # Créer une invitation vers le salon vocal
            invite = await voice_channel.create_invite(
                max_age=3600,  # 1 heure
                max_uses=1,
                reason=f'Invitation de {inviter.display_name}'
            )
            
            invite_embed.add_field(
                name='🔗 Rejoindre',
                value=f'[Cliquez ici pour rejoindre]({invite.url})',
                inline=False
            )
            
            await member.send(embed=invite_embed)
            
            # Confirmation
            embed = discord.Embed(
                description=f'✅ Invitation envoyée à **{member.display_name}**',
                color=CONFIG['colors']['success']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            embed = discord.Embed(
                description=f'❌ Impossible d\'envoyer l\'invitation à **{member.display_name}** (MP fermés)',
                color=CONFIG['colors']['error']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class RenameModal(discord.ui.Modal):
    def __init__(self, channel_id):
        super().__init__(title="Renommer le salon vocal")
        self.channel_id = channel_id
        
        self.name_input = discord.ui.TextInput(
            label="Nouveau nom du salon",
            placeholder="Entrez le nouveau nom...",
            max_length=CONFIG['limits']['max_channel_name_length'],
            required=True
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        voice_channel = bot.get_channel(self.channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon introuvable', ephemeral=True)
            return

        new_name = self.name_input.value.strip()
        if not new_name:
            await interaction.response.send_message('❌ Le nom ne peut pas être vide', ephemeral=True)
            return

        try:
            old_name = voice_channel.name
            await voice_channel.edit(name=new_name)
            
            embed = discord.Embed(
                title='✅ Salon renommé',
                description=f'**Ancien nom:** {old_name}\n**Nouveau nom:** {new_name}',
                color=CONFIG['colors']['success']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message('❌ Permissions insuffisantes', ephemeral=True)

class LimitModal(discord.ui.Modal):
    def __init__(self, channel_id):
        super().__init__(title="Définir la limite d'utilisateurs")
        self.channel_id = channel_id
        
        self.limit_input = discord.ui.TextInput(
            label="Limite d'utilisateurs (0 = illimité)",
            placeholder="Entrez un nombre entre 0 et 99...",
            max_length=2,
            required=True
        )
        self.add_item(self.limit_input)

    async def on_submit(self, interaction: discord.Interaction):
        voice_channel = bot.get_channel(self.channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon introuvable', ephemeral=True)
            return

        try:
            limit = int(self.limit_input.value.strip())
            if limit < 0 or limit > 99:
                await interaction.response.send_message('❌ La limite doit être entre 0 et 99', ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message('❌ Veuillez entrer un nombre valide', ephemeral=True)
            return

        try:
            await voice_channel.edit(user_limit=limit)
            
            limit_text = str(limit) if limit > 0 else "Illimitée"
            embed = discord.Embed(
                title='✅ Limite modifiée',
                description=f'**Salon:** {voice_channel.name}\n**Nouvelle limite:** {limit_text}',
                color=CONFIG['colors']['success']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message('❌ Permissions insuffisantes', ephemeral=True)

@bot.event
async def on_voice_state_update(member, before, after):
    """Gérer les changements d'état vocal"""
    
    guild_config = voice_config.get(member.guild.id)
    if not guild_config:
        return

    # Utilisateur rejoint le salon de création
    if after.channel and after.channel.id == guild_config['creation_channel_id']:
        await create_temp_voice_channel(member, guild_config)
    
    # Vérifier si un salon temporaire devient vide
    if before.channel and before.channel.id in temp_channels:
        # Programmer la vérification avec délai
        asyncio.create_task(check_and_delete_empty_channel(before.channel.id))

async def create_temp_voice_channel(member, guild_config):
    """Créer un salon vocal temporaire pour un utilisateur"""
    
    # Vérifier les limites
    guild_temp_channels = [ch for ch in temp_channels.values() if ch['guild_id'] == member.guild.id]
    if len(guild_temp_channels) >= CONFIG['limits']['max_channels_per_guild']:
        return

    try:
        guild = member.guild
        category = bot.get_channel(guild_config['category_id'])
        
        # Nom du salon avec emoji
        user_settings_data = user_settings.get(member.id, {})
        default_name = user_settings_data.get('default_name', f"Salon de {member.display_name}")
        
        # Créer le salon vocal temporaire
        temp_voice = await guild.create_voice_channel(
            name=default_name,
            category=category,
            reason=f"Salon vocal temporaire créé pour {member}"
        )
        
        # Permissions pour le propriétaire
        await temp_voice.set_permissions(
            member, 
            manage_channels=True, 
            manage_permissions=True,
            move_members=True
        )
        
        # Déplacer l'utilisateur
        await member.move_to(temp_voice)
        
        # Enregistrer le salon temporaire
        temp_channels[temp_voice.id] = {
            'channel_id': temp_voice.id,
            'owner_id': member.id,
            'guild_id': guild.id,
            'created_at': datetime.datetime.utcnow(),
            'last_activity': datetime.datetime.utcnow()
        }
        
        # Envoyer le panneau de contrôle en MP
        await send_control_panel(member, temp_voice)
        
        print(f"✅ Salon créé: {temp_voice.name} pour {member}")
        
    except discord.Forbidden:
        print(f"❌ Permissions insuffisantes pour {member}")
    except Exception as e:
        print(f"❌ Erreur création salon: {e}")

async def send_control_panel(member, voice_channel):
    """Envoyer le panneau de contrôle à l'utilisateur"""
    
    try:
        view = VoiceControlPanel(voice_channel.id, member.id)
        embed = await view.create_panel_embed(voice_channel)
        
        welcome_embed = discord.Embed(
            title='🎉 Votre salon vocal a été créé!',
            description=f'**Salon:** {voice_channel.mention}\n**Serveur:** {voice_channel.guild.name}',
            color=CONFIG['colors']['success']
        )
        welcome_embed.add_field(
            name='🎛️ Panneau de contrôle',
            value='Utilisez les boutons ci-dessous pour gérer votre salon:',
            inline=False
        )
        
        await member.send(embeds=[welcome_embed, embed], view=view)
        
    except discord.Forbidden:
        # Si les MP sont fermés, essayer dans le serveur
        try:
            general_channel = discord.utils.find(
                lambda c: c.name in ['general', 'général', 'chat'], 
                voice_channel.guild.text_channels
            )
            
            if general_channel:
                embed = discord.Embed(
                    title='🎛️ Panneau de contrôle',
                    description=f'**{member.mention}**, votre salon {voice_channel.mention} a été créé!\n\n*Panneau envoyé ici car vos MP sont fermés*',
                    color=CONFIG['colors']['warning']
                )
                
                view = VoiceControlPanel(voice_channel.id, member.id)
                message = await general_channel.send(embed=embed, view=view)
                
                # Supprimer après 60 secondes
                await asyncio.sleep(60)
                try:
                    await message.delete()
                except:
                    pass
        except:
            pass

async def check_and_delete_empty_channel(channel_id):
    """Vérifier et supprimer un salon vide avec délai"""
    
    await asyncio.sleep(CONFIG['limits']['channel_cleanup_delay'])
    
    if channel_id not in temp_channels:
        return
        
    try:
        voice_channel = bot.get_channel(channel_id)
        if voice_channel and len(voice_channel.members) == 0:
            await voice_channel.delete(reason="Salon vocal temporaire vide")
            del temp_channels[channel_id]
            print(f"🗑️ Salon supprimé: {voice_channel.name}")
            
    except discord.NotFound:
        if channel_id in temp_channels:
            del temp_channels[channel_id]
    except Exception as e:
        print(f"❌ Erreur suppression salon {channel_id}: {e}")

@tasks.loop(minutes=30)
async def cleanup_empty_channels():
    """Nettoyage périodique des salons vides ou orphelins"""
    
    channels_to_remove = []
    
    for channel_id, data in temp_channels.items():
        try:
            voice_channel = bot.get_channel(channel_id)
            
            if not voice_channel:
                # Salon introuvable
                channels_to_remove.append(channel_id)
                continue
                
            if len(voice_channel.members) == 0:
                # Salon vide
                try:
                    await voice_channel.delete(reason="Nettoyage automatique")
                    channels_to_remove.append(channel_id)
                except:
                    pass
                    
            # Vérifier l'âge du salon (24h max)
            age = datetime.datetime.utcnow() - data['created_at']
            if age.total_seconds() > 86400:  # 24 heures
                try:
                    await voice_channel.delete(reason="Salon trop ancien")
                    channels_to_remove.append(channel_id)
                except:
                    pass
                    
        except Exception as e:
            print(f"❌ Erreur nettoyage {channel_id}: {e}")
            channels_to_remove.append(channel_id)
    
    # Supprimer les entrées
    for channel_id in channels_to_remove:
        if channel_id in temp_channels:
            del temp_channels[channel_id]
    
    if channels_to_remove:
        print(f"🧹 Nettoyage: {len(channels_to_remove)} salons supprimés")

# ==================== COMMANDES ====================

@bot.command(name='vsetup')
async def manual_setup(ctx):
    """Configuration manuelle du système vocal"""
    
    if not ctx.author.guild_permissions.manage_channels:
        embed = discord.Embed(
            description='❌ Permission requise: **Gérer les salons**',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    await auto_setup_guild(ctx.guild)
    
    embed = discord.Embed(
        title='✅ Système vocal configuré!',
        description='Le système de salons vocaux temporaires est maintenant actif.',
        color=CONFIG['colors']['success']
    )
    
    config = voice_config.get(ctx.guild.id)
    if config:
        category = bot.get_channel(config['category_id'])
        creation_channel = bot.get_channel(config['creation_channel_id'])
        
        embed.add_field(
            name='⚙️ Configuration',
            value=f'**Catégorie:** {category.mention if category else "Erreur"}\n**Salon de création:** {creation_channel.mention if creation_channel else "Erreur"}',
            inline=False
        )
    
    embed.add_field(
        name='🚀 Utilisation',
        value='Les utilisateurs peuvent maintenant rejoindre le salon **➕ Créer un salon** pour obtenir automatiquement leur salon vocal personnalisé!',
        inline=False
    )
    
    await ctx.reply(embed=embed)

@bot.command(name='vinfo')
async def voice_info(ctx):
    """Informations sur le système vocal"""
    
    config = voice_config.get(ctx.guild.id)
    if not config:
        embed = discord.Embed(
            description='❌ Système vocal non configuré. Utilisez `!vsetup`',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    # Compter les salons actifs
    guild_temp_channels = [ch for ch in temp_channels.values() if ch['guild_id'] == ctx.guild.id]
    
    category = bot.get_channel(config['category_id'])
    creation_channel = bot.get_channel(config['creation_channel_id'])
    
    embed = discord.Embed(
        title='📊 Système Vocal - Informations',
        color=CONFIG['colors']['voice']
    )
    
    embed.add_field(
        name='⚙️ Configuration',
        value=f'**Catégorie:** {category.mention if category else "❌ Introuvable"}\n**Salon de création:** {creation_channel.mention if creation_channel else "❌ Introuvable"}\n**Salons actifs:** {len(guild_temp_channels)}/{CONFIG["limits"]["max_channels_per_guild"]}',
        inline=False
    )
    
    if guild_temp_channels:
        channels_info = []
        for i, data in enumerate(guild_temp_channels[:5], 1):  # Limiter à 5
            voice_channel = bot.get_channel(data['channel_id'])
            if voice_channel:
                owner = bot.get_user(data['owner_id'])
                age = datetime.datetime.utcnow() - data['created_at']
                age_str = f"{int(age.total_seconds() // 3600)}h {int((age.total_seconds() % 3600) // 60)}m"
                channels_info.append(f'{i}. **{voice_channel.name}** - {owner.mention if owner else "Inconnu"} ({len(voice_channel.members)} membres, {age_str})')
        
        embed.add_field(
            name='🎛️ Salons Actifs',
            value='\n'.join(channels_info) + (f'\n... et {len(guild_temp_channels) - 5} autres' if len(guild_temp_channels) > 5 else ''),
            inline=False
        )
    
    embed.add_field(
        name='✨ Comment ça marche?',
        value='1️⃣ Rejoignez le salon **➕ Créer un salon**\n2️⃣ Un salon vocal personnalisé est créé automatiquement\n3️⃣ Vous recevez un panneau de contrôle complet en MP\n4️⃣ Gérez votre salon avec les boutons interactifs\n5️⃣ Le salon se supprime automatiquement quand il est vide',
        inline=False
    )
    
    embed.set_footer(text='Système vocal style DraftBot')
    
    await ctx.reply(embed=embed)

@bot.command(name='vconfig')
async def voice_user_config(ctx, *, default_name: str = None):
    """Configurer vos préférences de salon vocal"""
    
    if default_name:
        if len(default_name) > CONFIG['limits']['max_channel_name_length']:
            embed = discord.Embed(
                description=f'❌ Le nom doit faire moins de {CONFIG["limits"]["max_channel_name_length"]} caractères',
                color=CONFIG['colors']['error']
            )
            await ctx.reply(embed=embed)
            return
        
        # Sauvegarder les préférences
        user_settings[ctx.author.id] = {
            'default_name': default_name,
            'updated_at': datetime.datetime.utcnow()
        }
        
        embed = discord.Embed(
            title='✅ Configuration sauvegardée',
            description=f'**Nom par défaut:** {default_name}\n\nVos futurs salons vocaux utiliseront ce nom par défaut.',
            color=CONFIG['colors']['success']
        )
        await ctx.reply(embed=embed)
    else:
        # Afficher la configuration actuelle
        user_config = user_settings.get(ctx.author.id, {})
        current_name = user_config.get('default_name', f'Salon de {ctx.author.display_name}')
        
        embed = discord.Embed(
            title='⚙️ Vos préférences vocales',
            description=f'**Nom par défaut:** {current_name}',
            color=CONFIG['colors']['info']
        )
        
        embed.add_field(
            name='📝 Modifier',
            value='`!vconfig <nouveau_nom>` pour changer le nom par défaut',
            inline=False
        )
        
        await ctx.reply(embed=embed)

@bot.command(name='vstats')
async def voice_stats(ctx):
    """Statistiques globales du système vocal"""
    
    if not ctx.author.guild_permissions.manage_guild:
        embed = discord.Embed(
            description='❌ Permission requise: **Gérer le serveur**',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    guild_channels = [ch for ch in temp_channels.values() if ch['guild_id'] == ctx.guild.id]
    
    # Statistiques
    total_channels = len(guild_channels)
    total_users = sum(len(bot.get_channel(ch['channel_id']).members) 
                     for ch in guild_channels 
                     if bot.get_channel(ch['channel_id']))
    
    # Top propriétaires
    owners = {}
    for ch in guild_channels:
        owner_id = ch['owner_id']
        owners[owner_id] = owners.get(owner_id, 0) + 1
    
    embed = discord.Embed(
        title='📈 Statistiques Vocales',
        color=CONFIG['colors']['info'],
        timestamp=datetime.datetime.utcnow()
    )
    
    embed.add_field(
        name='📊 Général',
        value=f'**Salons actifs:** {total_channels}\n**Utilisateurs connectés:** {total_users}\n**Limite serveur:** {CONFIG["limits"]["max_channels_per_guild"]}',
        inline=False
    )
    
    if owners:
        top_owners = sorted(owners.items(), key=lambda x: x[1], reverse=True)[:5]
        top_list = []
        for i, (owner_id, count) in enumerate(top_owners, 1):
            owner = bot.get_user(owner_id)
            top_list.append(f'{i}. {owner.mention if owner else "Inconnu"} ({count} salon{"s" if count > 1 else ""})')
        
        embed.add_field(
            name='👑 Top Créateurs',
            value='\n'.join(top_list),
            inline=False
        )
    
    # Activité récente
    recent_channels = sorted(guild_channels, key=lambda x: x['created_at'], reverse=True)[:3]
    if recent_channels:
        recent_list = []
        for data in recent_channels:
            voice_channel = bot.get_channel(data['channel_id'])
            if voice_channel:
                owner = bot.get_user(data['owner_id'])
                age = datetime.datetime.utcnow() - data['created_at']
                age_str = f"{int(age.total_seconds() // 60)}m"
                recent_list.append(f'• **{voice_channel.name}** par {owner.mention if owner else "Inconnu"} (il y a {age_str})')
        
        embed.add_field(
            name='🕒 Créations Récentes',
            value='\n'.join(recent_list),
            inline=False
        )
    
    await ctx.reply(embed=embed)

@bot.command(name='help', aliases=['aide', 'h'])
async def bot_help(ctx):
    """Guide complet du bot vocal"""
    
    embed = discord.Embed(
        title='🔊 Bot Vocal Personnalisé (Style DraftBot)',
        description='Système complet de salons vocaux temporaires avec interface moderne',
        color=CONFIG['colors']['primary']
    )
    
    # Commandes principales
    embed.add_field(
        name='🎛️ Commandes Principales',
        value='`!vsetup` - Configurer le système (Admin)\n`!vinfo` - Informations du système\n`!vconfig [nom]` - Vos préférences\n`!vstats` - Statistiques (Admin)',
        inline=False
    )
    
    # Utilisation
    embed.add_field(
        name='🚀 Utilisation',
        value='1️⃣ Rejoignez le salon **➕ Créer un salon**\n2️⃣ Votre salon personnel est créé automatiquement\n3️⃣ Recevez le panneau de contrôle en MP\n4️⃣ Gérez votre salon avec les boutons',
        inline=False
    )
    
    # Fonctionnalités du panneau
    embed.add_field(
        name='🎛️ Panneau de Contrôle',
        value='• **Renommer** - Changez le nom de votre salon\n• **Limite** - Définissez un max d\'utilisateurs\n• **Verrouiller** - Bloquez/débloquez l\'accès\n• **Expulser** - Éjectez des utilisateurs\n• **Inviter** - Invitez des utilisateurs par MP',
        inline=False
    )
    
    # Permissions
    embed.add_field(
        name='🔐 Permissions Requises',
        value='**Admin:** Gérer les salons, Gérer le serveur\n**Utilisateurs:** Aucune permission spéciale',
        inline=False
    )
    
    # Fonctionnalités avancées
    embed.add_field(
        name='✨ Fonctionnalités',
        value='• Création automatique des salons\n• Interface moderne avec boutons\n• Système d\'invitations privées\n• Nettoyage automatique\n• Configuration personnalisée\n• Statistiques détaillées',
        inline=False
    )
    
    embed.set_footer(
        text='Bot Vocal Style DraftBot • Interface moderne & intuitive',
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

# ==================== GESTION D'ERREURS ====================

@bot.event
async def on_command_error(ctx, error):
    """Gestion des erreurs de commandes"""
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

# Nettoyage au démarrage
@cleanup_empty_channels.before_loop
async def before_cleanup():
    await bot.wait_until_ready()

# ==================== DÉMARRAGE ====================

# Récupération du token
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print('❌ Variable DISCORD_TOKEN non définie!')
    print('🔧 Ajoutez votre token Discord dans les variables d\'environnement')
    exit(1)

# Démarrage du bot
if __name__ == '__main__':
    print('🚀 Démarrage du Bot Vocal Style DraftBot...')
    bot.run(TOKEN)

"""
📁 FICHIERS REQUIS POUR LE DÉPLOIEMENT:

1. voice_bot.py (ce fichier)
2. requirements.txt (même que pour le bot giveaway)

📋 requirements.txt:
discord.py>=2.3.0,<2.4.0

🔊 SYSTÈME VOCAL STYLE DRAFTBOT - FONCTIONNALITÉS:

✨ CRÉATION AUTOMATIQUE:
✅ Configuration automatique à l'ajout du bot
✅ Création de la catégorie "🔊 Salons Vocaux"
✅ Salon de création "➕ Créer un salon"
✅ Support multi-serveurs

🎛️ PANNEAU DE CONTRÔLE MODERNE:
✅ Interface avec boutons interactifs (comme DraftBot)
✅ Renommer le salon (modal moderne)
✅ Définir limite d'utilisateurs (modal)
✅ Verrouiller/Déverrouiller (toggle button)
✅ Expulser des utilisateurs (menu déroulant)
✅ Inviter des utilisateurs (menu + MP automatique)

🚀 FONCTIONNALITÉS AVANCÉES:
✅ Préférences utilisateur personnalisées
✅ Noms de salon par défaut configurables
✅ Système d'invitations privées avec liens
✅ Statistiques détaillées pour les admins
✅ Nettoyage automatique (vides + anciens)
✅ Limites de sécurité configurables

🎮 COMMANDES DISPONIBLES:

📊 ADMINISTRATION:
- !vsetup - Configuration automatique du système
- !vinfo - Informations et statistiques
- !vstats - Statistiques détaillées (Admin)

👤 UTILISATEUR:
- !vconfig [nom] - Définir le nom par défaut de vos salons
- !help - Aide complète
- !ping - Latence

🛠️ PROCESSUS AUTOMATIQUE:

1️⃣ **Installation:** Bot ajouté → Configuration automatique
2️⃣ **Utilisation:** Utilisateur rejoint "➕ Créer un salon"
3️⃣ **Création:** Salon vocal personnalisé créé instantanément
4️⃣ **Contrôle:** Panneau envoyé en MP avec 5 boutons
5️⃣ **Gestion:** Interface complète (renommer, limite, verrouiller, expulser, inviter)
6️⃣ **Nettoyage:** Suppression automatique quand vide

🎛️ INTERFACE MODERNE (Style DraftBot):
✅ Embeds colorés avec design Discord officiel
✅ Boutons interactifs pour toutes les actions
✅ Modals pour la saisie de données
✅ Menus déroulants pour la sélection
✅ Messages éphémères pour les confirmations
✅ Panneau de contrôle en temps réel

🔧 SÉCURITÉ & PERFORMANCE:
✅ Limites configurables (50 salons/serveur par défaut)
✅ Validation des entrées utilisateur
✅ Nettoyage automatique toutes les 30 minutes
✅ Suppression des salons de +24h
✅ Gestion d'erreurs complète
✅ Fallback si MP fermés

🎯 COMPARAISON AVEC DRAFTBOT:
✅ Interface identique avec boutons
✅ Même système de panneau de contrôle
✅ Fonctionnalités d'invitation avancées
✅ Statistiques détaillées
✅ Configuration utilisateur
✅ Design moderne et intuitif

💡 EXEMPLE D'UTILISATION:
1. Utilisateur rejoint "➕ Créer un salon"
2. Salon "Salon de PseudoUser" créé automatiquement
3. Utilisateur reçoit en MP un embed avec 5 boutons:
   - ✏️ Renommer
   - 👥 Limite 
   - 🔒 Verrouiller
   - 👢 Expulser
   - 📨 Inviter
4. Clics sur boutons → Actions immédiates
5. Salon se supprime automatiquement quand vide

🌟 POINTS FORTS:
✅ Configuration 100% automatique
✅ Interface moderne identique à DraftBot
✅ Système d'invitations privées unique
✅ Préférences utilisateur sauvegardées
✅ Statistiques administrateur complètes
✅ Code optimisé et sécurisé

Ce système vocal est une réplique moderne et améliorée du système DraftBot
avec une interface utilisateur identique et des fonctionnalités supplémentaires!
"""
