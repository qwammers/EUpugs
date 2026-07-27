# HostedPugs

HostedPugs is a Team Fortress 2 6v6 PUG platform consisting of:

- A React frontend deployed to GitHub Pages
- A FastAPI API and `discord.py` bot hosted together on AWS EC2
- A managed PostgreSQL database hosted on Amazon RDS
- Caddy providing HTTPS for the API through a DuckDNS hostname

## Project Layout

- `frontend/`: React, Vite, and TypeScript application
- `backend/`: FastAPI API, Discord bot, database models, migrations, and shared services
- `deploy/`: Caddy reverse-proxy configuration
- `.github/workflows/`: CI and GitHub Pages deployment

## Core Capabilities

- Discord OAuth login, guild membership validation, and Steam identity discovery
- Primary-class and flex-class TF2 6s queueing
- Three-minute pre-ready status and immediate 45-second ready checks
- Three-map voting and runner-controlled match creation
- Discord role-based class restrictions
- Temporary Discord match-role and voice-channel access
- Next-match queueing and audited live substitutions
- ETF2L v2 skill screening and runner review
- `logs.tf` ingestion, player profiles, class statistics, leaderboard, and match archive

## Local Development

### Backend

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```bash
   pip install -e .[dev]
   ```

3. Copy `backend/.env.example` to `backend/.env` and provide development values.
4. Run the API:

   ```bash
   uvicorn app.main:app --reload --app-dir backend
   ```

5. In a second terminal, run the Discord bot:

   ```bash
   python -m app.bot.runtime
   ```

### Frontend

1. Install dependencies:

   ```bash
   cd frontend
   npm install
   ```

2. Copy `frontend/.env.example` to `frontend/.env`.
3. Set `VITE_API_BASE_URL=http://localhost:8000`.
4. Start Vite:

   ```bash
   npm run dev
   ```

## AWS Architecture

- **EC2** runs Docker Compose services for the FastAPI API, Discord bot, and Caddy.
- **RDS PostgreSQL** stores authentication sessions, players, queue cycles, matches, logs, and statistics.
- **Caddy** forwards HTTPS requests from the public API hostname to the `api` container.
- **DuckDNS** supplies a free hostname such as `eupugs.duckdns.org` pointing to the EC2 public IP.
- **GitHub Pages** hosts only the static frontend and sends API requests to the DuckDNS URL.
- The Discord bot and API share the same code, RDS database, and environment configuration.

Only ports `22`, `80`, and `443` need to be exposed by the EC2 security group. RDS should not
be public; its security group should allow PostgreSQL port `5432` only from the EC2 security
group.

## AWS Deployment

### 1. Prepare RDS

Create a PostgreSQL RDS instance and database. Allow inbound PostgreSQL traffic from the EC2
security group, then construct the connection string:

```text
postgresql+psycopg://DATABASE_USER:DATABASE_PASSWORD@RDS_ENDPOINT:5432/DATABASE_NAME
```

URL-encode special characters in the username or password.

### 2. Prepare EC2

Use an Ubuntu EC2 instance with an Elastic IP where possible. Install Git and Docker:

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
```

Log out and reconnect after adding the Docker group, then clone the repository.

### 3. Configure DNS And Discord

Point the DuckDNS hostname at the EC2 Elastic IP. In the Discord Developer Portal:

- Set the OAuth redirect URI to `https://YOUR_HOSTNAME/auth/discord/callback`.
- Enable **Server Members Intent** and **Message Content Intent**.
- Give the bot `View Channels`, `Send Messages`, `Read Message History`, `Use Application
  Commands`, and `Manage Roles`.
- Place the bot role above the approved-member and temporary match roles.

### 4. Configure The Backend

Create `.env` in the repository root on EC2. Docker Compose passes this file to both Python
containers and uses `API_DOMAIN` when rendering the Caddy configuration:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@RDS_ENDPOINT:5432/DATABASE_NAME
API_DOMAIN=YOUR_HOSTNAME
SESSION_SECRET=replace_with_a_long_random_secret
SESSION_COOKIE_NAME=hostedpugs_session
SESSION_MAX_AGE_SECONDS=2592000

DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DISCORD_REDIRECT_URI=https://YOUR_HOSTNAME/auth/discord/callback
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
DISCORD_LOG_CHANNEL_ID=
DISCORD_ADMIN_ROLE_IDS=
DISCORD_MATCH1_RED_ROLE_ID=
DISCORD_MATCH1_RED_VOICE_CHANNEL_ID=
DISCORD_MATCH1_BLU_ROLE_ID=
DISCORD_MATCH1_BLU_VOICE_CHANNEL_ID=
DISCORD_MATCH2_RED_ROLE_ID=
DISCORD_MATCH2_RED_VOICE_CHANNEL_ID=
DISCORD_MATCH2_BLU_ROLE_ID=
DISCORD_MATCH2_BLU_VOICE_CHANNEL_ID=
DISCORD_APPROVED_ROLE_ID=
DISCORD_CLASS_RESTRICTIONS={"ROLE_ID":["medic"],"ANOTHER_ROLE_ID":["demo","soldier"]}

FRONTEND_ORIGIN=https://GITHUB_USERNAME.github.io
FRONTEND_URL=https://GITHUB_USERNAME.github.io/REPOSITORY_NAME
API_BASE_URL=https://YOUR_HOSTNAME

ENABLE_AUTO_MIGRATE=true
LOGSTF_SYNC_LIMIT=20
ETF2L_API_BASE_URL=https://api-v2.etf2l.org
ETF2L_HISTORY_PAGE_LIMIT=5
```

The bundled `deploy/Caddyfile` reads `API_DOMAIN` automatically. Start the stack:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 api bot caddy
```

Confirm the public API:

```bash
curl https://YOUR_HOSTNAME/health
```

With `ENABLE_AUTO_MIGRATE=true`, API startup applies pending Alembic migrations to RDS.
Revision `20260727_0005` converts the queue to match ownership, merges the old next queue,
seeds Elo from recognized Discord skill roles, and preserves existing matches, logs, and stats.

### 5. Deploy GitHub Pages

In the GitHub repository, create an Actions variable named `VITE_API_BASE_URL` with:

```text
https://YOUR_HOSTNAME
```

Enable GitHub Pages with **GitHub Actions** as its source, then run the Pages workflow or push
to the configured deployment branch.

### 6. Update Production

From the repository directory on EC2:

```bash
git pull
docker compose up -d --build
docker compose logs --tail=100 api bot caddy
```

## Verification

Run these checks before deployment:

```bash
python -m pytest
python -m ruff check backend
cd frontend
npm run build
```

Monitor production with:

```bash
docker compose ps
docker compose logs -f api bot caddy
```
