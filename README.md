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
- Système de tickets dédié au serveur `1376052088047665242` : panneau embed avec bouton d'ouverture et persistance Supabase.

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
DATABASE_PATH=/data/bot.db
SECRET_KEY=change-me
SUPABASE_URL=https://...supabase.co
SUPABASE_KEY=cle_api_service_role
TICKET_GUILD_ID=1376052088047665242
TICKET_SUPPORT_ROLE_ID=role_id_staff
TICKET_CATEGORY_ID=category_id_tickets
```

### Configuration Supabase
1. Crée un projet Supabase et récupère l'URL et la clé **service_role** puis renseigne `SUPABASE_URL` et `SUPABASE_KEY` dans les variables d'environnement.
2. Ajoute une table `tickets` avec les colonnes :
   - `id` (bigint, primary key, auto increment)
   - `guild_id` (text, non nul)
   - `user_id` (text, non nul)
   - `channel_id` (text, non nul)
   - `topic` (text, nullable)
   - `status` (text, non nul, valeurs attendues : `open`, `closed`, `deleted`)
   - `created_at` (timestamp, non nul, default `now()`)
   - `closed_at` (timestamp, nullable)
   - `closed_by` (text, nullable)
3. (Optionnel) Restreins l'accès avec les politiques RLS adaptées à ton usage. Le bot utilise la clé service_role et interagit côté serveur uniquement.
4. Assure-toi que les colonnes `guild_id`, `user_id` et `channel_id` sont indexées si tu attends beaucoup de tickets pour garder des requêtes rapides.

## Démarrage local
```bash
python main.py
```
Le dashboard est disponible sur http://localhost:8000 et le bot se connecte à Discord.

## Déploiement Koyeb
- Service Web sur le port `8000` (variable `PORT`).
- Commande de démarrage : `python main.py`
- Health check HTTP `/health`.
- Volume persistant recommandé monté sur `/data` (SQLite).

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
