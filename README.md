# HostedPugs

HostedPugs is a monorepo for a Team Fortress 2 6v6 pug platform with:

- A static React frontend deployed to GitHub Pages
- A FastAPI + `discord.py` backend deployed to bot-hosting.net
- PostgreSQL for queue state, player identity, match state, and cached `logs.tf` stats

## Project Layout

- `frontend/`: React + Vite + TypeScript app
- `backend/`: FastAPI API, Discord bot, database models, and services
- `.github/workflows/`: CI and GitHub Pages deployment

## Core Capabilities

- Discord OAuth login with guild membership verification
- Steam identity discovery from Discord connections
- TF2 6s queueing with multi-class preferences
- Admin-controlled match creation and state changes
- Match log attachment and `logs.tf` stat ingestion
- Player profiles, leaderboard, and next-match queue opt-in

## Local Development

### Backend

1. Create a Python virtual environment.
2. Install dependencies:
   - `pip install -e .[dev]`
3. Copy [backend/.env.example](/C:/Users/Admin/Documents/hostedpugs/backend/.env.example) to `backend/.env`.
4. Run the API:
   - `uvicorn app.main:app --reload --app-dir backend`
5. Run the bot separately when needed:
   - `python -m app.bot.runtime`

### Frontend

1. Install dependencies:
   - `npm install`
2. Copy [frontend/.env.example](/C:/Users/Admin/Documents/hostedpugs/frontend/.env.example) to `frontend/.env`.
3. Start the dev server:
   - `npm run dev`

## Deployment

### GitHub Pages

- The frontend builds with Vite and deploys through `.github/workflows/pages.yml`.
- Set `VITE_API_BASE_URL` to the public backend URL.

### bot-hosting.net

- Import this repository on bot-hosting.net.
- Provision:
  - One Python deployment for the API + bot
  - One managed PostgreSQL database
- Startup command example:
  - `uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend`
- For the bot, either:
  - Run a second Python deployment with `python -m app.bot.runtime`
  - Or run a process manager command that starts both

## Required Environment Variables

Backend:

- `DATABASE_URL`
- `SESSION_SECRET`
- `DISCORD_CLIENT_ID`
- `DISCORD_CLIENT_SECRET`
- `DISCORD_REDIRECT_URI`
- `DISCORD_BOT_TOKEN`
- `DISCORD_GUILD_ID`
- `DISCORD_LOG_CHANNEL_ID`
- `DISCORD_ADMIN_ROLE_IDS`
- `FRONTEND_ORIGIN`
- `API_BASE_URL`

Frontend:

- `VITE_API_BASE_URL`

