# Bot Discord Premium - Giveaway & Système Vocal (Style DraftBot)
# Système complet combiné avec interface moderne
# Requirements: discord.py
# Installation: pip install discord.py

import discord
from discord.ext import commands, tasks
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
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Stockage des données (en mémoire)
# GIVEAWAYS
active_giveaways = {}

# VOCAL
voice_config = {}
temp_channels = {}
user_voice_settings = {}

# Configuration design moderne
CONFIG = {
    'colors': {
        'primary': 0x5865F2,      # Discord Blurple
        'success': 0x57F287,      # Vert moderne
        'error': 0xED4245,        # Rouge moderne
        'warning': 0xFEE75C,      # Jaune moderne
        'info': 0x5865F2,         # Bleu moderne
        'voice': 0x9B59B6         # Violet pour le vocal
    },
    'emojis': {
        'giveaway': '🎉',
        'winner': '🏆',
        'participants': '👥',
        'time': '⏰',
        'host': '👑',
        'gift': '🎁',
        'voice': '🔊',
        'settings': '⚙️',
        'lock': '🔒',
        'unlock': '🔓',
        'kick': '👢',
        'rename': '✏️',
        'info': 'ℹ️'
    },
    'limits': {
        'max_channels_per_guild': 30,
        'max_channel_name_length': 80,
        'channel_cleanup_delay': 3
    }
}

@bot.event
async def on_ready():
    print(f'🚀 {bot.user} est connecté!')
    print(f'📊 Présent sur {len(bot.guilds)} serveur(s)')
    
    # Démarrer les tâches automatiques
    cleanup_empty_channels.start()
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=f"🎉 Giveaways & 🔊 Vocal sur {len(bot.guilds)} serveurs"
        )
    )
    
    # Configuration automatique des serveurs
    await setup_all_guilds()

async def setup_all_guilds():
    """Configuration automatique pour tous les serveurs"""
    for guild in bot.guilds:
        await auto_setup_vocal(guild)

async def auto_setup_vocal(guild):
    """Configuration automatique du système vocal"""
    if guild.id in voice_config:
        return
        
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
        
        voice_config[guild.id] = {
            'category_id': category.id,
            'creation_channel_id': creation_channel.id,
            'temp_channels': [],
            'auto_setup': True
        }
        
        print(f"✅ Système vocal configuré: {guild.name}")
        
    except discord.Forbidden:
        print(f"❌ Permissions insuffisantes sur: {guild.name}")

@bot.event
async def on_guild_join(guild):
    """Configuration automatique lors de l'ajout à un nouveau serveur"""
    await auto_setup_vocal(guild)

# ==================== SYSTÈME GIVEAWAY ====================

class GiveawayView(discord.ui.View):
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
        giveaway = active_giveaways.get(self.giveaway_id)
        if not giveaway:
            return
            
        embed = self.create_giveaway_embed(giveaway, self.giveaway_id)
        
        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except:
            pass

    def create_giveaway_embed(self, giveaway, giveaway_id):
        participants_count = len(giveaway['participants'])
        end_time = giveaway['end_time']
        
        embed = discord.Embed(
            title=f"{CONFIG['emojis']['giveaway']} **GIVEAWAY EN COURS** {CONFIG['emojis']['giveaway']}",
            color=CONFIG['colors']['primary']
        )
        
        embed.description = f"### {CONFIG['emojis']['gift']} **{giveaway['prize']}**"
        
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
        
        embed.set_footer(
            text=f"ID: {giveaway_id} • Cliquez pour participer!",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        
        embed.timestamp = end_time
        
        return embed

@bot.command(name='giveaway', aliases=['g', 'gw'])
async def create_giveaway(ctx, duration: str = None, winners: int = None, *, prize: str = None):
    """🎉 Créer un giveaway moderne"""
    
    if not ctx.author.guild_permissions.manage_messages:
        embed = discord.Embed(
            description='❌ Permission requise: **Gérer les messages**',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

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

    duration_seconds = parse_duration(duration)
    if not duration_seconds:
        embed = discord.Embed(
            description='❌ Durée invalide. Formats: `s` `m` `h` `d` `w`',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    if winners < 1 or winners > 20:
        embed = discord.Embed(
            description='❌ Nombre de gagnants: entre 1 et 20',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    if len(prize) > 150:
        embed = discord.Embed(
            description='❌ Le prix doit faire moins de 150 caractères',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration_seconds)
    giveaway_id = f"{ctx.guild.id}_{int(datetime.datetime.now().timestamp())}"

    giveaway_data = {
        'message_id': None,
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

    view = GiveawayView(giveaway_id)
    embed = view.create_giveaway_embed(giveaway_data, giveaway_id)

    try:
        giveaway_message = await ctx.send(embed=embed, view=view)
        
        giveaway_data['message_id'] = giveaway_message.id
        active_giveaways[giveaway_id] = giveaway_data

        asyncio.create_task(schedule_giveaway_end(giveaway_id, duration_seconds))
        
        try:
            await ctx.message.delete()
        except:
            pass

        confirm_embed = discord.Embed(
            description=f'✅ Giveaway créé!\n**Prix:** {prize}\n**Durée:** {duration}\n**Gagnants:** {winners}',
            color=CONFIG['colors']['success']
        )
        await ctx.send(embed=confirm_embed, delete_after=8)
        
    except discord.Forbidden:
        embed = discord.Embed(
            description='❌ Permissions insuffisantes',
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
            description='❌ **Usage:** `!gend <message_id>`',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    giveaway_id = None
    for gid, giveaway in active_giveaways.items():
        if giveaway['message_id'] == message_id and giveaway['guild_id'] == ctx.guild.id:
            giveaway_id = gid
            break

    if not giveaway_id:
        embed = discord.Embed(
            description='❌ Giveaway introuvable',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    await finish_giveaway(giveaway_id)
    
    embed = discord.Embed(
        description='✅ Giveaway terminé!',
        color=CONFIG['colors']['success']
    )
    await ctx.reply(embed=embed)

@bot.command(name='greroll', aliases=['reroll'])
async def reroll_giveaway(ctx, message_id: int = None):
    """🔄 Refaire le tirage"""
    
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

        participants = []
        for reaction in message.reactions:
            if str(reaction.emoji) == '🎉':
                async for user in reaction.users():
                    if not user.bot:
                        participants.append(user)
                break

        if not participants:
            embed = discord.Embed(
                description='❌ Aucun participant trouvé',
                color=CONFIG['colors']['error']
            )
            await ctx.reply(embed=embed)
            return

        winner = random.choice(participants)
        
        embed_desc = message.embeds[0].description or ""
        prize = "Prix inconnu"
        if '**' in embed_desc:
            try:
                prize = embed_desc.split('**')[1]
            except:
                prize = "Prix inconnu"

        winner_embed = discord.Embed(
            title='🔄 NOUVEAU TIRAGE!',
            description=f'**Nouveau gagnant:** {winner.mention}\n**Prix:** {prize}',
            color=CONFIG['colors']['success']
        )
        
        await ctx.send(f'{winner.mention}', embed=winner_embed)

    except discord.NotFound:
        embed = discord.Embed(
            description='❌ Message introuvable',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)

# ==================== SYSTÈME VOCAL ====================

class VoiceControlPanel(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.owner_id = owner_id

    @discord.ui.button(
        label='Renommer',
        emoji='✏️',
        style=discord.ButtonStyle.secondary
    )
    async def rename_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
            
        modal = RenameModal(self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label='Limite',
        emoji='👥',
        style=discord.ButtonStyle.secondary
    )
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
            
        modal = LimitModal(self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label='Verrouiller',
        emoji='🔒',
        style=discord.ButtonStyle.danger
    )
    async def lock_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
            
        await self.toggle_lock(interaction, button)

    async def check_owner(self, interaction):
        if interaction.user.id != self.owner_id:
            embed = discord.Embed(
                description='❌ Seul le propriétaire peut utiliser ce bouton',
                color=CONFIG['colors']['error']
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    async def toggle_lock(self, interaction, button):
        voice_channel = bot.get_channel(self.channel_id)
        if not voice_channel:
            await interaction.response.send_message('❌ Salon introuvable', ephemeral=True)
            return

        try:
            everyone_role = interaction.guild.default_role
            current_perms = voice_channel.overwrites_for(everyone_role)
            
            if current_perms.connect is False:
                await voice_channel.set_permissions(everyone_role, connect=None)
                button.label = "Verrouiller"
                button.emoji = "🔒"
                status = "🔓 Salon déverrouillé"
                color = CONFIG['colors']['success']
            else:
                await voice_channel.set_permissions(everyone_role, connect=False)
                button.label = "Déverrouiller"
                button.emoji = "🔓"
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

    async def create_panel_embed(self, voice_channel):
        owner = bot.get_user(self.owner_id)
        member_count = len(voice_channel.members)
        
        everyone_role = voice_channel.guild.default_role
        current_perms = voice_channel.overwrites_for(everyone_role)
        lock_status = "🔒 Verrouillé" if current_perms.connect is False else "🔓 Ouvert"
        
        limit = f"{voice_channel.user_limit}" if voice_channel.user_limit > 0 else "∞"
        
        embed = discord.Embed(
            title=f'🎛️ Panneau de Contrôle',
            description=f'**{voice_channel.name}**',
            color=CONFIG['colors']['voice']
        )
        
        embed.add_field(
            name='👑 Propriétaire',
            value=owner.mention if owner else 'Inconnu',
            inline=True
        )
        
        embed.add_field(
            name='👥 Connectés',
            value=f'{member_count}/{limit}',
            inline=True
        )
        
        embed.add_field(
            name='ℹ️ Statut',
            value=lock_status,
            inline=True
        )
        
        if voice_channel.members:
            member_list = []
            for member in voice_channel.members[:8]:
                if member.id == self.owner_id:
                    member_list.append(f'👑 **{member.display_name}**')
                else:
                    member_list.append(f'• {member.display_name}')
            
            members_text = '\n'.join(member_list)
            if len(voice_channel.members) > 8:
                members_text += f'\n... et {len(voice_channel.members) - 8} autres'
                
            embed.add_field(
                name='👥 Membres connectés',
                value=members_text,
                inline=False
            )
        
        embed.set_footer(text='Utilisez les boutons pour gérer votre salon')
        embed.timestamp = datetime.datetime.utcnow()
        
        return embed

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
            placeholder="Entrez un nombre entre 0 et 50...",
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
            if limit < 0 or limit > 50:
                await interaction.response.send_message('❌ La limite doit être entre 0 et 50', ephemeral=True)
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
        asyncio.create_task(check_and_delete_empty_channel(before.channel.id))

async def create_temp_voice_channel(member, guild_config):
    """Créer un salon vocal temporaire"""
    
    guild_temp_channels = [ch for ch in temp_channels.values() if ch['guild_id'] == member.guild.id]
    if len(guild_temp_channels) >= CONFIG['limits']['max_channels_per_guild']:
        return

    try:
        guild = member.guild
        category = bot.get_channel(guild_config['category_id'])
        
        user_settings_data = user_voice_settings.get(member.id, {})
        default_name = user_settings_data.get('default_name', f"Salon de {member.display_name}")
        
        temp_voice = await guild.create_voice_channel(
            name=default_name,
            category=category,
            reason=f"Salon vocal temporaire créé pour {member}"
        )
        
        await temp_voice.set_permissions(
            member, 
            manage_channels=True, 
            manage_permissions=True,
            move_members=True
        )
        
        await member.move_to(temp_voice)
        
        temp_channels[temp_voice.id] = {
            'channel_id': temp_voice.id,
            'owner_id': member.id,
            'guild_id': guild.id,
            'created_at': datetime.datetime.utcnow()
        }
        
        await send_control_panel(member, temp_voice)
        
        print(f"✅ Salon créé: {temp_voice.name} pour {member}")
        
    except discord.Forbidden:
        print(f"❌ Permissions insuffisantes pour {member}")
    except Exception as e:
        print(f"❌ Erreur création salon: {e}")

async def send_control_panel(member, voice_channel):
    """Envoyer le panneau de contrôle"""
    
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
            value='Utilisez les boutons ci-dessous pour gérer votre salon',
            inline=False
        )
        
        await member.send(embeds=[welcome_embed, embed], view=view)
        
    except discord.Forbidden:
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
                
                await asyncio.sleep(60)
                try:
                    await message.delete()
                except:
                    pass
        except:
            pass

async def check_and_delete_empty_channel(channel_id):
    """Vérifier et supprimer un salon vide"""
    
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
    """Nettoyage périodique des salons vides"""
    
    channels_to_remove = []
    
    for channel_id, data in temp_channels.items():
        try:
            voice_channel = bot.get_channel(channel_id)
            
            # Supprimer les salons vides
            if not voice_channel or len(voice_channel.members) == 0:
                try:
                    if voice_channel:
                        await voice_channel.delete(reason="Nettoyage automatique")
                except:
                    pass
                channels_to_remove.append(channel_id)
                    
            # Supprimer les salons trop anciens (12h)
            age = datetime.datetime.utcnow() - data['created_at']
            if age.total_seconds() > 43200:
                try:
                    if voice_channel:
                        await voice_channel.delete(reason="Salon trop ancien")
                except:
                    pass
                channels_to_remove.append(channel_id)
                    
            print(f"❌ Erreur nettoyage {channel_id}: {e}")
            channels_to_remove.append(channel_id)
    
    for channel_id in channels_to_remove:
        if channel_id in temp_channels:
            del temp_channels[channel_id]
    
    if channels_to_remove:
        print(f"🧹 Nettoyage: {len(channels_to_remove)} salons supprimés")

# ==================== COMMANDES COMBINÉES ====================

@bot.command(name='vsetup')
async def manual_vocal_setup(ctx):
    """🔊 Configuration du système vocal"""
    
    if not ctx.author.guild_permissions.manage_channels:
        embed = discord.Embed(
            description='❌ Permission requise: **Gérer les salons**',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

    await auto_setup_vocal(ctx.guild)
    
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
        value='Les utilisateurs peuvent maintenant rejoindre le salon **➕ Créer un salon** pour obtenir leur salon vocal personnalisé!',
        inline=False
    )
    
    await ctx.reply(embed=embed)

@bot.command(name='vinfo')
async def voice_info(ctx):
    """📊 Informations système vocal"""
    
    config = voice_config.get(ctx.guild.id)
    if not config:
        embed = discord.Embed(
            description='❌ Système vocal non configuré. Utilisez `!vsetup`',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
        return

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
        for i, data in enumerate(guild_temp_channels[:5], 1):
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
        value='1️⃣ Rejoignez **➕ Créer un salon**\n2️⃣ Un salon personnalisé est créé\n3️⃣ Panneau de contrôle envoyé en MP\n4️⃣ Gérez avec les boutons interactifs\n5️⃣ Suppression automatique quand vide',
        inline=False
    )
    
    await ctx.reply(embed=embed)

@bot.command(name='vconfig')
async def voice_user_config(ctx, *, default_name: str = None):
    """⚙️ Configurer vos préférences vocales"""
    
    if default_name:
        if len(default_name) > CONFIG['limits']['max_channel_name_length']:
            embed = discord.Embed(
                description=f'❌ Le nom doit faire moins de {CONFIG["limits"]["max_channel_name_length"]} caractères',
                color=CONFIG['colors']['error']
            )
            await ctx.reply(embed=embed)
            return
        
        user_voice_settings[ctx.author.id] = {
            'default_name': default_name,
            'updated_at': datetime.datetime.utcnow()
        }
        
        embed = discord.Embed(
            title='✅ Configuration sauvegardée',
            description=f'**Nom par défaut:** {default_name}\n\nVos futurs salons vocaux utiliseront ce nom.',
            color=CONFIG['colors']['success']
        )
        await ctx.reply(embed=embed)
    else:
        user_config = user_voice_settings.get(ctx.author.id, {})
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

    for i, (gid, giveaway) in enumerate(guild_giveaways[:8], 1):
        prize = giveaway['prize']
        if len(prize) > 40:
            prize = prize[:37] + "..."
            
        embed.add_field(
            name=f"{i}. {prize}",
            value=f"**Canal:** <#{giveaway['channel_id']}>\n**Fin:** <t:{int(giveaway['end_time'].timestamp())}:R>\n**Participants:** {len(giveaway['participants'])}",
            inline=True
        )

    if len(guild_giveaways) > 8:
        embed.set_footer(text=f'... et {len(guild_giveaways) - 8} autres giveaways')

    await ctx.reply(embed=embed)

@bot.command(name='help', aliases=['aide', 'h'])
async def bot_help(ctx):
    """📖 Guide complet du bot"""
    
    embed = discord.Embed(
        title='🤖 Bot Premium - Giveaway & Vocal',
        description='Bot moderne combinant système de giveaways et salons vocaux temporaires',
        color=CONFIG['colors']['primary']
    )
    
    # Giveaways
    embed.add_field(
        name='🎉 Giveaways',
        value='`!giveaway <durée> <gagnants> <prix>` - Créer\n`!gend <message_id>` - Terminer\n`!greroll <message_id>` - Nouveau tirage\n`!glist` - Liste active',
        inline=True
    )
    
    # Vocal
    embed.add_field(
        name='🔊 Système Vocal',
        value='`!vsetup` - Configuration (Admin)\n`!vinfo` - Informations\n`!vconfig [nom]` - Préférences\nRejoindre "➕ Créer un salon"',
        inline=True
    )
    
    embed.add_field(
        name='⏰ Durées Giveaway',
        value='`30s` `5m` `2h` `1d` `1w`',
        inline=True
    )
    
    embed.add_field(
        name='🎛️ Panneau Vocal',
        value='• Renommer le salon\n• Définir limite utilisateurs\n• Verrouiller/Déverrouiller',
        inline=True
    )
    
    embed.add_field(
        name='🔐 Permissions',
        value='**Giveaway:** Gérer les messages\n**Vocal:** Gérer les salons',
        inline=True
    )
    
    embed.add_field(
        name='💡 Exemples',
        value='`!g 24h 1 Nitro Discord`\n`!vconfig Mon Salon`',
        inline=True
    )
    
    embed.add_field(
        name='✨ Fonctionnalités',
        value='• Interface moderne avec boutons\n• Gestion automatique\n• Configuration personnalisée\n• Multi-serveurs optimisé',
        inline=False
    )
    
    embed.set_footer(
        text='Bot Premium • Simple & Efficace',
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
    """Programmer la fin d'un giveaway"""
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
        
        if not participants:
            embed = discord.Embed(
                title=f"{CONFIG['emojis']['giveaway']} **GIVEAWAY TERMINÉ** {CONFIG['emojis']['giveaway']}",
                description=f"### {CONFIG['emojis']['gift']} **{giveaway['prize']}**\n\n❌ **Aucun participant**",
                color=CONFIG['colors']['error']
            )
        else:
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
                name=f"{CONFIG['emojis']['participants']} Participants",
                value=f"**{len(participants)}**",
                inline=True
            )
            
            embed.add_field(
                name=f"{CONFIG['emojis']['host']} Organisé par",
                value=f"<@{giveaway['host_id']}>",
                inline=True
            )

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
        
        await message.edit(embed=embed, view=None)

    except Exception as e:
        print(f'❌ Erreur fin giveaway {giveaway_id}: {e}')

    if giveaway_id in active_giveaways:
        del active_giveaways[giveaway_id]

def parse_duration(duration_str):
    """Parser une durée en secondes"""
    pattern = r'^(\d+)([smhdw])
            
    match = re.match(pattern, duration_str.lower())
    
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if value <= 0:
        return None
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800
    }
    
    duration_seconds = value * multipliers.get(unit, 0)
    
    # Limites: minimum 10 secondes, maximum 2 semaines
    if duration_seconds < 10 or duration_seconds > 1209600:
        return None
        
    return duration_seconds

@bot.event
async def on_command_error(ctx, error):
    """Gestion des erreurs"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            description='❌ Arguments manquants. Utilisez `!help`',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            description='❌ Argument invalide. Utilisez `!help`',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            description='❌ Permissions insuffisantes',
            color=CONFIG['colors']['error']
        )
        await ctx.reply(embed=embed)
    else:
        print(f'❌ Erreur: {error}')

@cleanup_empty_channels.before_loop
async def before_cleanup():
    await bot.wait_until_ready()

# ==================== DÉMARRAGE ====================

TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print('❌ Variable DISCORD_TOKEN non définie!')
    print('🔧 Ajoutez votre token Discord dans les variables d\'environnement')
    exit(1)

if __name__ == '__main__':
    print('🚀 Démarrage du Bot Premium Giveaway & Vocal...')
    bot.run(TOKEN)
