# Secure Discord Bot + Dashboard

Bot Discord (discord.js v14) avec protections anti-raid / anti-nuke et dashboard Express simple.

## Prérequis
- Node.js 18+
- Créez un bot Discord, récupérez `DISCORD_TOKEN`, `CLIENT_ID`, `GUILD_ID`.

## Installation
```bash
npm install
```

## Configuration
Créer un fichier `.env` à la racine :
```
DISCORD_TOKEN=VotreToken
CLIENT_ID=VotreClientId
GUILD_ID=ServeurDeTest
DASHBOARD_PORT=3000
ADMIN_PASSWORD=motdepassefort
SESSION_SECRET=sessionSecret
PORT=8080
JWT_SECRET=change_me
FRONTEND_URL=http://localhost:5173
```
Optionnel : remplissez `config/defaultConfig.js` ou passez par le dashboard.

L'API expose également `GET /health` pour les health checks (Koyeb/Kubernetes) et des routes REST modernes sous `/api/*` (auth, config, stats, whitelist, logs, guilds) protégées par JWT + rate-limit.

## Démarrage
```bash
npm run start
```
Le bot démarre et le dashboard écoute sur `http://localhost:3000` (ou le port défini).

## Structure
- `index.js` : point d'entrée, lance bot + dashboard.
- `config/defaultConfig.js` : seuils par défaut.
- `src/db/database.js` : stockage JSON (`data/data.json`).
- `src/bot/security/*` : anti-raid, anti-nuke, niveaux de confiance.
- `src/bot/events/*` : hooks Discord (joins, bans, suppressions, etc.).
- `src/dashboard/*` : Express (login, config, whitelist, stats).

## Fonctionnalités clés
- **Anti-raid** : détection joins massifs 60s, comptes récents, lockdown automatique, quarantaine/kick.
- **Anti-nuke** : suivi audit logs (salons, rôles, bans, webhooks), seuils configurables, strip rôles / ban.
- **Whitelist / Trust** : OWNER, TRUSTED_ADMIN, NORMAL_ADMIN, DEFAULT_USER.
- **Dashboard** : login mot de passe, stats, édition des seuils, gestion whitelist.

## Notes
- Les commandes slash `/lockdown enable|disable` sont enregistrées sur le serveur `GUILD_ID`.
- Les logs de sécurité sont envoyés dans le salon `logChannelId` (configurable dans le dashboard).
- Le stockage JSON est le plus simple ; remplacez `src/db/database.js` si vous migrez vers SQLite/Mongo.

## Améliorations possibles
- Snapshot complet des rôles/salons pour restauration avancée.
- Web UI plus riche (charting, AJAX) et authentification OAuth2.
