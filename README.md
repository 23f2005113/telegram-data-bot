# Telegram Data Analyst Bot

Answers data-analysis questions sent over Telegram with a single JSON reply:
`{"answer": ..., "log_url": "https://your-host/run.jsonl"}`

## 1. Create your Telegram bot

1. Open Telegram, message **@BotFather**
2. `/newbot` → choose a name → choose a **username ending in `bot`** (required by the assignment)
3. Copy the token it gives you (looks like `123456789:AAxxxx...`)

## 2. Get an Anthropic API key

Go to https://console.anthropic.com → API Keys → create one. This costs a small amount
per call (web search + generation) — keep an eye on usage during testing.

## 3. Push this code to a public GitHub repo

```bash
cd telegram_data_bot
git init
git add .
git commit -m "Data analyst telegram bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/telegram-data-bot.git
git push -u origin main
```

**Do not commit your `.env` file or real keys.** Only `.env.example` should be in the repo.

## 4. Deploy so it's always reachable

Any host that can run a long-lived Python web process works. Easiest free options:

### Option A: Render (recommended, simplest)
1. https://render.com → New → Web Service → connect your GitHub repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn bot:app --host 0.0.0.0 --port $PORT`
4. Add environment variables (from `.env.example`) in the Render dashboard —
   set `PUBLIC_HOST` to the `https://your-app.onrender.com` URL Render gives you
5. Deploy. Render will call your app's `/webhook` route once it's live, which
   auto-registers the Telegram webhook on startup (see `lifespan` in `bot.py`)

**Note:** Render's free tier sleeps after inactivity, which can delay your first
reply. Use a free uptime pinger (e.g. UptimeRobot hitting `/` every 5 min) during
the grading window to keep it warm.

### Option B: Railway
Same idea — connect repo, set the same env vars, same start command,
`PUBLIC_HOST` = the Railway-provided domain.

## 5. Test it yourself before submitting

Clone the grading pipeline mentioned in the assignment, add your own test
questions to `eval/questions.json`, and message your bot directly on Telegram
with a data-analysis question to confirm it replies with valid JSON like:

```json
{"answer": "Assam", "log_url": "https://your-app.onrender.com/log.jsonl"}
```

Then open `log_url` in a browser — it should show one JSON object per line,
newest at the bottom.

## 6. Register on the exam page

Submit, comma-separated:
```
https://github.com/YOUR_USERNAME/telegram-data-bot, your_bot_username_bot
```

## Known limitations to be aware of

- **Log persistence:** `run.jsonl` is written to local disk. On Render/Railway
  free tiers this resets on redeploy/restart (not on normal request handling,
  but do avoid redeploying once grading starts). For extra safety, consider
  adding a persistent disk (Render offers small paid disks) or writing log
  entries to a GitHub Gist via the GitHub API instead of local disk.
- **Conversation memory** is in-memory per chat — fine for a single grading
  session, but resets if the process restarts.
- **web_search tool cost:** each question may trigger 1+ searches; keep your
  Anthropic account funded during grading.
