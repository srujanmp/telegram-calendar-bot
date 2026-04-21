# Railway Deployment Guide

## ✅ Pre-Deployment Checklist

- [x] `.gitignore` created (excludes `.env`, credentials, tokens)
- [x] `Procfile` configured (`worker: python bot.py`)
- [x] `requirements.txt` updated with all dependencies
- [x] `.env.example` created with all required variables
- [x] Code ready for production (SSL verification conditional)

---

## 📋 Step-by-Step Deployment

### **Step 1: Commit Your Code**

```bash
cd ~/Documents/telegram-calendar-bot

git add .
git commit -m "Initial commit: Telegram calendar bot with all features"
git branch -M main
```

### **Step 2: Push to GitHub**

```bash
# Create a new GitHub repository (do this on github.com)
# Then run:

git remote add origin https://github.com/YOUR_USERNAME/telegram-calendar-bot.git
git push -u origin main
```

### **Step 3: Connect Railway**

1. Go to **https://railway.app**
2. Sign up / Log in
3. Click **"New Project"**
4. Select **"Deploy from GitHub"**
5. Connect your GitHub account
6. Select the `telegram-calendar-bot` repository
7. Choose `main` branch

### **Step 4: Configure Environment Variables**

In Railway dashboard, go to **Variables** and add:

```
TELEGRAM_TOKEN=<your_telegram_bot_token>
ALLOWED_USER_ID=<your_user_id>
GROQ_API_KEY=<your_grok_api_key>
GOOGLE_CALENDAR_ID=primary
GOOGLE_TOKEN_JSON=<base64_encoded_token_from_auth_setup.py>
TOKEN_PATH=/data/token.json
ENVIRONMENT=production
```

### **Step 5: Add Persistent Volume (Optional but Recommended)**

This allows the bot to persist the Google token across restarts:

1. In Railway dashboard → **Volumes**
2. Click **"New Volume"**
3. Set Mount Path: `/data`
4. This ensures tokens are saved between deployments

### **Step 6: Deploy**

1. Click **"Deploy"**
2. Watch the logs as Railway builds and deploys
3. Confirm bot is running: `Application started`

---

## 🧪 Testing After Deployment

Once deployed, test the bot in Telegram:

```
Test 1: "ML exam May 5 at 10am"
✓ Should create timed event

Test 2: "Birthday: Mom May 10"
✓ Should create yearly recurring all-day event

Test 3: "delete exam"
✓ Should delete matching events

Test 4: /events
✓ Should list upcoming events
```

---

## 📝 Environment Variables Reference

| Variable | Example | Notes |
|----------|---------|-------|
| `TELEGRAM_TOKEN` | `123:ABC...` | Get from @BotFather |
| `ALLOWED_USER_ID` | `2077630684` | Get from @userinfobot (leave empty to allow all) |
| `GROQ_API_KEY` | `gsk_...` | From https://console.x.ai |
| `GOOGLE_CALENDAR_ID` | `primary` | Default is your main calendar |
| `GOOGLE_TOKEN_JSON` | `eyJ0b2...` (base64) | From running `python auth_setup.py` locally |
| `TOKEN_PATH` | `/data/token.json` | Path inside container (with volume) |
| `ENVIRONMENT` | `production` | Set to `production` for Railway |

---

## 🔑 Getting `GOOGLE_TOKEN_JSON`

1. Ensure `credentials.json` is in your project folder
2. Run locally:
   ```bash
   python auth_setup.py
   ```
3. Browser opens → sign in with Google → allow access
4. Copy the printed base64 string
5. Paste into Railway as `GOOGLE_TOKEN_JSON`

---

## 🐛 Troubleshooting

### Bot not responding
- Check logs in Railway dashboard
- Verify `TELEGRAM_TOKEN` is correct
- Ensure `ALLOWED_USER_ID` matches your Telegram ID

### Google Calendar not syncing
- Verify `GOOGLE_TOKEN_JSON` is set
- Check `ENVIRONMENT=production` is set
- Token may need refresh: re-run `python auth_setup.py` locally

### Events not persisting between restarts
- Add a Volume mounted at `/data`
- Ensures `token.json` survives restarts

---

## 📊 Monitoring

In Railway dashboard:
- **Logs**: Real-time bot activity
- **Metrics**: CPU, Memory, Network usage
- **Deployments**: Version history and rollback

---

## ✅ Deployment Complete!

Your bot is now **live on Railway**! 🎉

- Runs 24/7
- Auto-restarts on failure
- Scales automatically with usage
- Integrates with Google Calendar in real-time

Send messages to your Telegram bot to test!
