# CalBot — Telegram → Grok → Google Calendar

Send natural language messages to your Telegram bot and events land directly in Google Calendar.

---

## How It Works

```
You (Telegram) → bot.py → grok_service.py (xAI Grok) → calendar_service.py → Google Calendar
```

Plain messages create events. Commands manage them.

| What you send | What happens |
|---|---|
| `ML exam May 5 at 10am 3 hours` | Creates event with 3h duration + reminders |
| `DSA submission this Friday 11:59pm` | Creates event at deadline time |
| `/events` | Lists next 10 upcoming events |
| `/delete` | Shows event picker → deletes selected |
| `/update` | Shows event picker → describe change in plain text |

---

## Project Structure

```
calbot/
├── bot.py               # Telegram bot, all handlers
├── grok_service.py      # xAI Grok API — NLP parsing
├── calendar_service.py  # Google Calendar CRUD
├── auth_setup.py        # One-time local OAuth helper
├── requirements.txt
├── Procfile             # Railway worker definition
└── .env.example
```

---

## Step 1 — Telegram Bot Token

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow prompts → copy the **HTTP API token**
3. Get your own Telegram user ID: message **@userinfobot** → note the `Id` field
   (used for `ALLOWED_USER_ID` so only you can use the bot)

---

## Step 2 — Grok API Key

1. Go to **https://console.x.ai**
2. Sign in → API Keys → **Create API Key**
3. Copy the key (starts with `xai-…`)

---

## Step 3 — Google Calendar API + OAuth

### 3a. Create a Google Cloud project

1. Go to **https://console.cloud.google.com**
2. Top bar → project dropdown → **New Project** → name it `calbot` → Create
3. Make sure the new project is selected

### 3b. Enable the Calendar API

1. Left sidebar → **APIs & Services** → **Library**
2. Search `Google Calendar API` → click it → **Enable**

### 3c. Create OAuth credentials

1. **APIs & Services** → **Credentials** → **+ Create Credentials** → **OAuth client ID**
2. If prompted for consent screen:
   - User Type: **External** → Create
   - App name: `CalBot`, your email for support
   - Scopes: click **Add or Remove Scopes** → find `Google Calendar API` → check `.../auth/calendar` → Save
   - Test users: add your own Google account email → Save
3. Back to Create OAuth client ID:
   - Application type: **Desktop app**
   - Name: `calbot-desktop`
   - **Create** → Download JSON → rename to `credentials.json`
4. Put `credentials.json` in the `calbot/` folder

### 3d. Run one-time local auth

```bash
cd calbot
pip install -r requirements.txt
python auth_setup.py
```

Your browser opens → log in with your Google account → allow access.

The script prints a long base64 string — **copy it**, you'll paste it as `GOOGLE_TOKEN_JSON` on Railway.

---

## Step 4 — Test Locally

Create `.env` from `.env.example` and fill in all values:

```bash
cp .env.example .env
# edit .env
```

```bash
python bot.py
```

Open Telegram → send your bot a message like `Physics exam next Monday 2pm 2 hours` → check Google Calendar.

---

## Step 5 — Push to GitHub

```bash
cd calbot
git init
echo "token.json" >> .gitignore
echo "credentials.json" >> .gitignore
echo ".env" >> .gitignore
git add .
git commit -m "initial calbot"
```

Create a new **private** repo on GitHub → push:

```bash
git remote add origin https://github.com/YOUR_USERNAME/calbot.git
git branch -M main
git push -u origin main
```

---

## Step 6 — Deploy on Railway

### 6a. Create the project

1. Go to **https://railway.com/dashboard**
2. **New Project** → **Deploy from GitHub repo**
3. Authorize Railway if prompted → select your `calbot` repo → **Deploy Now**

Railway auto-detects Python via Nixpacks and installs `requirements.txt`.

### 6b. Set the start command

1. Click your service → **Settings** tab
2. Under **Deploy** → **Start Command**, enter:
   ```
   python bot.py
   ```
   (The `Procfile` also handles this automatically — Railway reads it.)

### 6c. Add environment variables

1. Click your service → **Variables** tab → **+ New Variable** for each:

| Variable | Value |
|---|---|
| `TELEGRAM_TOKEN` | your BotFather token |
| `ALLOWED_USER_ID` | your Telegram user ID (from @userinfobot) |
| `GROK_API_KEY` | your xAI API key |
| `GOOGLE_CALENDAR_ID` | `primary` (or specific calendar ID) |
| `GOOGLE_TOKEN_JSON` | the base64 string from `auth_setup.py` |
| `TOKEN_PATH` | `/data/token.json` |

### 6d. Add a Volume (for token refresh persistence)

This prevents re-auth if the OAuth access token expires while the container is running.

1. **New** (top right of your project) → **Volume**
2. Mount path: `/data`
3. Attach it to your `calbot` service

### 6e. Redeploy

Railway auto-deploys on every push to `main`. To trigger manually:

1. **Deployments** tab → **Deploy** (or push a commit)

### 6f. Verify it's running

1. **Deployments** tab → click the latest deploy → **View Logs**
2. You should see: `Bot starting…`
3. Go to Telegram → message your bot → it should respond

---

## Token Refresh Notes

- The Google OAuth **refresh token** doesn't expire unless you revoke access or 6 months of inactivity.
- The **access token** expires every hour — the app auto-refreshes it using the refresh token.
- With the Railway Volume at `/data`, the refreshed token is written to `/data/token.json` and persists across container restarts.
- Without a Volume, it refreshes in-memory each startup from `GOOGLE_TOKEN_JSON` — still works fine.

---

## Updating the Bot

```bash
# make your changes locally, test, then:
git add .
git commit -m "your change"
git push
# Railway auto-redeploys
```

---

## Example Messages the Bot Understands

```
ML exam on May 5 at 10am
DSA assignment due this Friday at 11:59pm
Physics lab viva next Tuesday 2pm, 1 hour
OS quiz tomorrow 9am
Network security internals submission June 3
Project demo next Monday at 3:30pm, 45 minutes
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Bot doesn't respond | Check Railway logs; verify `TELEGRAM_TOKEN` is correct |
| "Couldn't extract event details" | Message is too vague — include date and time |
| Calendar event not created | Check `GOOGLE_TOKEN_JSON` is correct base64; verify Calendar API is enabled |
| Token expired error in logs | Re-run `auth_setup.py` locally → update `GOOGLE_TOKEN_JSON` env var on Railway |
| Unauthorized | `ALLOWED_USER_ID` doesn't match your actual Telegram ID — get it from @userinfobot |
