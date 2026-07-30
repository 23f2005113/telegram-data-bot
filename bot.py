import os
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import google.generativeai as genai

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, FileResponse
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ---- Config (set these as environment variables on your host) ----
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
PUBLIC_HOST = os.environ["PUBLIC_HOST"]  # e.g. https://your-app.onrender.com (no trailing slash)
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

LOG_PATH = "run.jsonl"

genai.configure(api_key=GEMINI_API_KEY)
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Very simple in-memory per-chat session store.
# Good enough for short multi-turn question sequences during grading.
sessions: dict[int, "genai.ChatSession"] = {}

SYSTEM_PROMPT = """You are a data analyst agent talking to a user over Telegram.
You will receive one or more messages building up a data-analysis question.
Only the LAST message is the actual question you must answer; earlier messages are context.

The question may reference a public dataset (e.g. MOSPI, data.gov.in, or similar open
government/public data sources). Use the web_search tool to find relevant pages, and the
fetch_page tool to read their actual content - do not guess or make up numbers.

The question itself will specify exactly what shape the answer must take
(e.g. a state name, a number, a list, etc.) usually with a phrase like
'reply with ONLY ...'. Once you have computed the real answer, output ONLY that value -
no explanation, no extra words, no markdown, no surrounding JSON. Just the raw value,
shaped exactly as the question asked for it."""


def web_search(query: str) -> str:
    """Search the web for a query and return top result titles, URLs, and snippets as JSON."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        return json.dumps(results)
    except Exception as e:
        return f"search error: {e}"


def fetch_page(url: str) -> str:
    """Fetch a webpage by URL and return its visible text content (truncated to 6000 chars)."""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        return text[:6000]
    except Exception as e:
        return f"fetch error: {e}"


def get_session(chat_id: int):
    if chat_id not in sessions:
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=SYSTEM_PROMPT,
            tools=[web_search, fetch_page],
        )
        sessions[chat_id] = model.start_chat(enable_automatic_function_calling=True)
    return sessions[chat_id]


def append_log(entry: dict) -> None:
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def compute_answer(chat_id: int, question: str) -> str:
    chat = get_session(chat_id)
    response = chat.send_message(question)
    return response.text.strip()


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
