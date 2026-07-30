import os
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, FileResponse
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

import anthropic

# ---- Config (set these as environment variables on your host) ----
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
PUBLIC_HOST = os.environ["PUBLIC_HOST"]  # e.g. https://your-app.onrender.com (no trailing slash)
MODEL_NAME = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

LOG_PATH = "run.jsonl"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Very simple in-memory per-chat conversation history.
# Good enough for short multi-turn question sequences during grading.
conversations: dict[int, list] = {}

SYSTEM_PROMPT = """You are a data analyst agent talking to a user over Telegram.
You will receive one or more messages building up a data-analysis question.
Only the LAST message is the actual question you must answer; earlier messages are context.

The question may reference a public dataset (e.g. MOSPI, data.gov.in, or similar open
government/public data sources). Use the web_search tool to find and read the actual
data you need - do not guess or make up numbers.

The question itself will specify exactly what shape the answer must take
(e.g. a state name, a number, a list, etc.) usually with a phrase like
'reply with ONLY ...'. Once you have computed the real answer, output ONLY that value -
no explanation, no extra words, no markdown, no surrounding JSON. Just the raw value,
shaped exactly as the question asked for it."""


def append_log(entry: dict) -> None:
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def compute_answer(chat_id: int, question: str) -> str:
    history = conversations.setdefault(chat_id, [])
    history.append({"role": "user", "content": question})

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=history,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )

    answer_text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    history.append({"role": "assistant", "content": answer_text})
    return answer_text


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    question = update.message.text

    try:
        answer = await compute_answer(chat_id, question)
    except Exception as e:
        answer = f"error: {e}"

    reply = {
        "answer": answer,
        "log_url": f"{PUBLIC_HOST}/log.jsonl",
    }

    append_log({"chat_id": chat_id, "question": question, "reply": reply})

    await update.message.reply_text(json.dumps(reply))


telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(url=f"{PUBLIC_HOST}/webhook")
    await telegram_app.start()
    yield
    await telegram_app.stop()
    await telegram_app.shutdown()


app = FastAPI(lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return PlainTextResponse("ok")


@app.get("/log.jsonl")
async def get_log():
    if not os.path.exists(LOG_PATH):
        open(LOG_PATH, "a").close()
    return FileResponse(LOG_PATH, media_type="application/x-ndjson")


@app.get("/")
async def health():
    return {"status": "running"}
