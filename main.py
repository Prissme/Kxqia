import datetime
import json
import logging
import os
import threading
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, jsonify, render_template, request, send_file
from flask_socketio import SocketIO

from database import db
from database.models import Config

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
)
logger = logging.getLogger(__name__)

# --- Discord Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.messages = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
bot_status = {'ready': False}

# --- Flask + SocketIO
app = Flask(__name__, template_folder='dashboard/templates', static_folder='dashboard/static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-me')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

start_time = datetime.datetime.utcnow()

# --- Database initialization
db.init_db()
config = db.load_config()


def uptime() -> str:
    delta = datetime.datetime.utcnow() - start_time
    days, remainder = divmod(delta.total_seconds(), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{int(days)}d {int(hours)}h {int(minutes)}m"


# --- Discord helpers

def _iter_message_channels(guild: discord.Guild) -> Iterable[discord.abc.Messageable]:
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


# --- Discord events and commands
@bot.event
async def on_ready():
    bot_status['ready'] = True
    logger.info('%s est connecté!', bot.user)
    try:
        await bot.tree.sync()
    except Exception as exc:  # noqa: BLE001
        logger.exception('Sync des commandes échouée: %s', exc)
    socketio.emit('bot_status', {
        'status': 'online',
        'latency': round(bot.latency * 1000, 2) if bot.latency else None,
        'guilds': len(bot.guilds),
    })


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    db.log_event('system', 'info', 'Message reçu', user_id=str(message.author.id), user_name=str(message.author), channel_id=str(message.channel.id))
    db.record_daily_stats(date_value=datetime.date.today(), guild_id=str(message.guild.id if message.guild else 'dm'), members_total=message.guild.member_count if message.guild else 0, messages_sent=1, commands_used=0)


@bot.command(name='help')
async def help_command(ctx: commands.Context):
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
async def ping(ctx: commands.Context):
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error('Error: %s', error)


@bot.tree.command(name='purge', description='Nettoie les messages et verrouille le salon pour les membres')
@app_commands.describe(amount='Nombre de messages à supprimer (1-1000)', reason='Raison affichée dans le journal')
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000] = 100, reason: Optional[str] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message('Permissions insuffisantes pour utiliser cette commande.', ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=True)

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send('Cette commande ne peut être utilisée que dans un salon textuel.', ephemeral=True)
        return

    log_reason = reason or f'Purge demandée par {interaction.user}'
    deleted = await channel.purge(limit=amount, reason=log_reason)

    overwrite = channel.overwrites_for(interaction.guild.default_role) or discord.PermissionOverwrite()
    overwrite.send_messages = False
    overwrite.add_reactions = True
    overwrite.create_public_threads = False
    overwrite.create_private_threads = False
    overwrite.send_messages_in_threads = False

    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason='Salon verrouillé après purge')

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

    db.add_moderation_action('purge', str(channel.id), channel.name, str(interaction.user.id), str(interaction.user), reason or '', {'messages_deleted': len(deleted)})
    db.log_event('moderation', 'info', 'Purge effectuée', user_id=str(interaction.user.id), user_name=str(interaction.user), channel_id=str(channel.id), metadata={'messages_deleted': len(deleted)})
    socketio.emit('moderation_action', {
        'type': 'purge',
        'channel': channel.name,
        'user': str(interaction.user),
        'details': f"{len(deleted)} messages",
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

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

    overwrite = channel.overwrites_for(interaction.guild.default_role) or discord.PermissionOverwrite()
    overwrite.send_messages = True
    overwrite.add_reactions = True
    overwrite.create_public_threads = True
    overwrite.create_private_threads = True
    overwrite.send_messages_in_threads = True

    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason or 'Salon rouvert après unpurge')

    info_embed = discord.Embed(
        title='🔓 Salon rouvert',
        description='Les membres peuvent à nouveau envoyer des messages et créer des fils.',
        color=0x57F287
    )
    if reason:
        info_embed.add_field(name='Raison', value=reason, inline=False)
    info_embed.set_footer(text=f'Action effectuée par {interaction.user.display_name}')

    db.add_moderation_action('unpurge', str(channel.id), channel.name, str(interaction.user.id), str(interaction.user), reason or '', {})
    db.log_event('moderation', 'info', 'Unpurge effectué', user_id=str(interaction.user.id), user_name=str(interaction.user), channel_id=str(channel.id))
    socketio.emit('moderation_action', {
        'type': 'unpurge',
        'channel': channel.name,
        'user': str(interaction.user),
        'details': reason or 'Rouverte',
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

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
@app_commands.describe(min_messages='Nombre minimal de messages', window_days='Fenêtre de temps en jours')
async def stats_messages(interaction: discord.Interaction, min_messages: app_commands.Range[int, 1, 1000], window_days: app_commands.Range[int, 1, 365]):
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

    await interaction.followup.send("Classement des membres (historique inclus) :\n" + "\n".join(lines), ephemeral=True)


# --- Flask routes
@app.route('/')
def home():
    return render_template('index.html', title='Dashboard')


@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html', title='Analytics')


@app.route('/moderation')
def moderation_page():
    return render_template('moderation.html', title='Modération')


@app.route('/logs')
def logs_page():
    return render_template('logs.html', title='Logs')


@app.route('/settings')
def settings_page():
    return render_template('settings.html', title='Settings')


@app.route('/health')
def health():
    ready = bot_status.get('ready', False)
    if ready:
        return jsonify({
            'status': 'ok',
            'bot': 'ready',
            'latency': round(bot.latency * 1000, 2) if bot.latency else None,
            'guilds': len(bot.guilds)
        }), 200
    return jsonify({'status': 'starting', 'bot': 'connecting'}), 503


@app.route('/api/stats/overview')
def stats_overview():
    overview = db.get_overview()
    overview.update({
        'uptime': uptime(),
        'bot_status': 'online' if bot_status.get('ready') else 'offline',
        'latency': round(bot.latency * 1000, 2) if bot_status.get('ready') and bot.latency else None,
        'guilds': len(bot.guilds) if bot_status.get('ready') else 0,
        'chart_data': _fake_chart_data(),
        'members_today': 0,
        'messages_today': 0,
        'guild': _guild_metadata(),
    })
    return jsonify(overview)


@app.route('/api/stats/messages')
def stats_messages_api():
    period = request.args.get('period', '7d')
    min_messages = int(request.args.get('min_messages', 1))
    payload = [
        {'user_id': '1', 'username': 'User#1234', 'count': 120, 'percentage': 12.5},
        {'user_id': '2', 'username': 'User#5678', 'count': 95, 'percentage': 9.3},
    ]
    return jsonify({'period': period, 'min_messages': min_messages, 'results': payload})


@app.route('/api/stats/channels')
def stats_channels_api():
    payload = [
        {'channel_id': '1', 'name': 'général', 'message_count': 340},
        {'channel_id': '2', 'name': 'annonces', 'message_count': 120},
    ]
    return jsonify(payload)


@app.route('/api/logs')
def api_logs():
    filters = {
        'type': request.args.get('type', 'all'),
        'search': request.args.get('search'),
        'start': request.args.get('start'),
        'end': request.args.get('end'),
    }
    return jsonify(db.get_logs(filters))


@app.route('/api/moderation/history')
def api_moderation_history():
    filters = {
        'type': request.args.get('type', 'all'),
        'date': request.args.get('date'),
    }
    channels = _guild_channels()
    response = db.get_moderation_history(filters)
    response['channels'] = channels
    return jsonify(response)


@app.route('/api/moderation/purge', methods=['POST'])
def api_purge():
    payload = request.get_json(force=True)
    amount = int(payload.get('amount', 0))
    if amount <= 0 or amount > 1000:
        return jsonify({'success': False, 'error': 'amount must be 1-1000'}), 400
    channel_id = str(payload.get('channel_id'))
    reason = payload.get('reason', '')
    db.add_moderation_action('purge', channel_id, f'#{channel_id}', 'dashboard', 'Dashboard', reason, {'messages_deleted': amount})
    db.log_event('moderation', 'info', f'Purge demandée via API ({amount})', channel_id=channel_id, user_name='Dashboard')
    socketio.emit('moderation_action', {
        'type': 'purge',
        'channel': channel_id,
        'user': 'Dashboard',
        'details': f'{amount} messages',
        'timestamp': datetime.datetime.utcnow().isoformat(),
    })
    socketio.emit('request_purge', {'channel_id': channel_id, 'amount': amount, 'reason': reason})
    return jsonify({'success': True, 'messages_deleted': amount})


@app.route('/api/moderation/unpurge', methods=['POST'])
def api_unpurge():
    payload = request.get_json(force=True)
    channel_id = str(payload.get('channel_id'))
    reason = payload.get('reason', '')
    db.add_moderation_action('unpurge', channel_id, f'#{channel_id}', 'dashboard', 'Dashboard', reason, {})
    db.log_event('moderation', 'info', 'Unpurge demandé via API', channel_id=channel_id, user_name='Dashboard')
    socketio.emit('request_unpurge', {'channel_id': channel_id, 'reason': reason})
    return jsonify({'success': True})


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    global config
    if request.method == 'GET':
        return jsonify(config.to_dict())
    payload = request.get_json(force=True)
    new_config = Config.from_mapping(payload)
    db.save_config(new_config)
    config = new_config
    return jsonify({'success': True, 'config': new_config.to_dict()})


@app.route('/api/export/logs')
def export_logs():
    return _export_csv('logs')


@app.route('/api/export/config')
def export_config():
    path = Path('/tmp/config.json')
    path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
    return send_file(path, mimetype='application/json', as_attachment=True, download_name='config.json')


@app.route('/api/export/stats')
def export_stats():
    return _export_csv('daily_stats')


def _export_csv(table: str):
    path = Path(f'/tmp/{table}.csv')
    rows = list(db.export_table(table))
    if not rows:
        path.write_text('')
        return send_file(path, mimetype='text/csv', as_attachment=True, download_name=f'{table}.csv')
    headers = rows[0].keys()
    with path.open('w', encoding='utf-8') as handle:
        handle.write(','.join(headers) + '\n')
        for row in rows:
            handle.write(','.join(str(row[h]) for h in headers) + '\n')
    return send_file(path, mimetype='text/csv', as_attachment=True, download_name=f'{table}.csv')


@app.route('/api/guilds')
def api_guilds():
    guilds = [_guild_metadata(g) for g in bot.guilds] if bot_status.get('ready') else []
    return jsonify(guilds)


@app.route('/api/guilds/<guild_id>')
def api_guild_detail(guild_id: str):
    guild = next((g for g in bot.guilds if str(g.id) == guild_id), None) if bot_status.get('ready') else None
    return jsonify(_guild_metadata(guild))


# --- Socket.IO events
@socketio.on('request_purge')
def handle_request_purge(data):
    db.log_event('moderation', 'info', 'Purge demandée via websocket', channel_id=data.get('channel_id'), user_name='Dashboard')
    socketio.emit('moderation_action', {
        'type': 'purge',
        'channel': data.get('channel_id'),
        'user': 'Dashboard',
        'details': f"{data.get('amount', 0)} messages",
        'timestamp': datetime.datetime.utcnow().isoformat(),
    })


@socketio.on('update_config')
def handle_update_config(data):
    new_cfg = Config.from_mapping(data)
    db.save_config(new_cfg)
    global config
    config = new_cfg
    socketio.emit('config_updated', new_cfg.to_dict())


# --- Helpers

def _guild_metadata(guild: Optional[discord.Guild] = None) -> dict:
    if guild is None:
        return {'name': 'N/A', 'id': '--', 'members': 0, 'online': 0, 'bots': 0, 'created_at': '--', 'owner': '--', 'roles': []}
    roles = [role.name for role in sorted(guild.roles, key=lambda r: r.position, reverse=True)[:5]]
    return {
        'name': guild.name,
        'id': str(guild.id),
        'members': guild.member_count,
        'online': len([m for m in guild.members if m.status != discord.Status.offline]),
        'bots': len([m for m in guild.members if m.bot]),
        'created_at': guild.created_at.strftime('%Y-%m-%d'),
        'owner': str(guild.owner) if guild.owner else 'Unknown',
        'roles': roles,
    }


def _guild_channels() -> list[dict[str, str]]:
    if not bot_status.get('ready'):
        return []
    channels = []
    for guild in bot.guilds:
        for channel in guild.text_channels:
            channels.append({'id': str(channel.id), 'name': channel.name})
    return channels


def _fake_chart_data() -> dict:
    return {
        'messages': [{'label': (datetime.date.today() - datetime.timedelta(days=i)).strftime('%d/%m'), 'value': max(10, 100 - i * 5)} for i in range(6, -1, -1)],
        'channels': [{'label': '#général', 'value': 320}, {'label': '#annonces', 'value': 120}, {'label': '#random', 'value': 95}, {'label': '#dev', 'value': 80}, {'label': '#support', 'value': 65}],
        'events': [{'label': 'purge', 'value': 12}, {'label': 'unpurge', 'value': 3}, {'label': 'stats', 'value': 5}],
        'heatmap': [{'label': f"{h}h", 'value': (h * 7) % 50 + 5} for h in range(0, 24, 3)],
    }


# --- Runner

def run_bot():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error('ERREUR: Token Discord non trouvé!')
        return
    bot.run(token)


def run_flask():
    port = int(os.getenv('PORT', 8000))
    # allow_unsafe_werkzeug enables the built-in dev server in environments like Koyeb
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    run_flask()
