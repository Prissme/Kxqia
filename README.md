# Discord Bot + Dashboard Flask

Bot Discord en **discord.py** avec dashboard web en **Flask + Flask-SocketIO** pour Koyeb. Le bot et le serveur web tournent dans le même processus grâce au threading.

## Fonctionnalités
- Commandes slash `/purge`, `/unpurge`, `/stats_last_3_months`, `/stats_messages`.
- Commandes préfixées `!ping`, `!help`.
- Dashboard complet : overview, analytics, modération, logs, settings (theme dark/light, export CSV/JSON).
- WebSocket temps réel (Socket.IO) pour stats live, actions modération, statut bot.
- API REST (`/api/stats/*`, `/api/logs`, `/api/moderation/*`, `/api/config`, `/api/export/*`).
- Health check `/health` prêt pour Koyeb.
- Base SQLite (logs, stats quotidiennes, actions de modération, config).

## Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration
Variables d'environnement principales :
```
DISCORD_TOKEN=votre_token
PORT=8000
DATABASE_PATH=data/bot.db
SECRET_KEY=change-me
```

## Démarrage local
```bash
python main.py
```
Le dashboard est disponible sur http://localhost:8000 et le bot se connecte à Discord.

## Déploiement Koyeb
- Service Web sur le port `8000` (variable `PORT`).
- Commande de démarrage : `python main.py`
- Health check HTTP `/health`.
- Volume persistant recommandé pour `data/` (SQLite).

## Export & sauvegarde
- `GET /api/export/logs` → CSV des logs
- `GET /api/export/config` → JSON de la configuration
- `GET /api/export/stats` → CSV des stats quotidiennes

## Structure
```
main.py                  # Discord bot + Flask + SocketIO + threading
dashboard/templates      # Pages HTML (Tailwind + Chart.js)
dashboard/static/css     # Styles custom
dashboard/static/js      # JS (charts, websocket, interactions)
database/db.py           # SQLite + requêtes
database/models.py       # Modèles Config
requirements.txt         # Dépendances Python
Dockerfile               # Image Python 3.11 ready
```
