
import re
import instaloader
import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from io import BytesIO
import os
import base64
import instaloader

# Загружаем session из переменной среды
session_data = os.getenv("SESSION_B64")

if session_data:
    with open("session-instagram", "wb") as f:
        f.write(base64.b64decode(session_data))

    L = instaloader.Instaloader()
    L.load_session_from_file("session-instagram")
else:
    print("❌ SESSION_B64 не задан — авторизация невозможна.")

# Подключаем Instaloader с авторизацией
L = instaloader.Instaloader()
TOKEN = os.getenv("TOKEN")
loader = instaloader.Instaloader()

def extract_emails_and_phones(text):
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    phone_pattern = r"(\+\d[\d\s().-]{7,}\d)"
    emails = re.findall(email_pattern, text)
    phones = re.findall(phone_pattern, text)
    return emails, phones

def clean_usernames(text: str):
    raw_usernames = re.split(r"[,\s\n]+", text.strip())
    return [u.lstrip("@") for u in raw_usernames if u]

async def start(update: Update, context):
    await update.message.reply_text("Отправь список Instagram-юзернеймов через запятую или с новой строки.")

async def handle_message(update: Update, context):
    usernames = clean_usernames(update.message.text)
    results = []

    for username in usernames:
        try:
            profile = instaloader.Profile.from_username(loader.context, username)
            bio = profile.biography
            emails, phones = extract_emails_and_phones(bio)
            results.append({"username": username, "emails": emails, "phones": phones})
        except Exception as e:
            results.append({"username": username, "emails": [], "phones": [], "error": str(e)})

    df = pd.DataFrame(results)
    excel_buffer = BytesIO()
    df.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)
    await update.message.reply_document(document=excel_buffer, filename="results.xlsx")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
