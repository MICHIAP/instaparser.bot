import os
import requests
import asyncio
import datetime
import time
import base64
import hashlib
import hmac
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ContentType, LabeledPrice

# === Загружаем .env ===
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

# === Читаем токены ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AUDD_API_KEY = os.getenv("AUDD_API_KEY")
ACR_HOST = os.getenv("ACR_HOST")
ACR_ACCESS_KEY = os.getenv("ACR_ACCESS_KEY")
ACR_ACCESS_SECRET = os.getenv("ACR_ACCESS_SECRET")
SHAZAM_KEY = os.getenv("SHAZAM_KEY")
FREE_LIMIT = int(os.getenv("FREE_LIMIT", 3))

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Лимиты и подписки
user_limits = {}
user_subscriptions = set()

# ======== ПОИСК В СЕРВИСАХ ========

# Audd.io
def get_all_matches_audd(file_path):
    data = {'api_token': AUDD_API_KEY, 'return': 'timecode,spotify,deezer'}
    with open(file_path, 'rb') as f:
        res = requests.post('https://api.audd.io/', data=data, files={'file': f}).json()

    results = []
    if res.get("result"):
        matches = res["result"] if isinstance(res["result"], list) else [res["result"]]
        for match in matches:
            line = f"{match['artist']} — {match['title']}"
            if match.get('spotify'):
                line += f" | [Spotify]({match['spotify']['external_urls']['spotify']})"
            if match.get('deezer'):
                line += f" | [Deezer]({match['deezer']['link']})"
            results.append(line)
    return results

# ACRCloud
def get_all_matches_acr(file_path):
    http_method = "POST"
    http_uri = "/v1/identify"
    data_type = "audio"
    signature_version = "1"
    timestamp = str(int(time.time()))

    string_to_sign = "\n".join([
        http_method,
        http_uri,
        ACR_ACCESS_KEY,
        data_type,
        signature_version,
        timestamp
    ])
    sign = base64.b64encode(hmac.new(
        ACR_ACCESS_SECRET.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        digestmod=hashlib.sha1
    ).digest()).decode('utf-8')

    files = [('sample', (os.path.basename(file_path), open(file_path, 'rb'), 'audio/mpeg'))]
    data = {
        'access_key': ACR_ACCESS_KEY,
        'data_type': data_type,
        'signature_version': signature_version,
        'signature': sign,
        'timestamp': timestamp
    }

    res = requests.post(f"http://{ACR_HOST}/v1/identify", files=files, data=data).json()
    results = []
    try:
        matches = res['metadata']['music']
        for match in matches:
            title = match['title']
            artist = match['artists'][0]['name']
            line = f"{artist} — {title}"
            results.append(line)
    except:
        pass
    return results

# Shazam API
def get_all_matches_shazam(file_path):
    url = "https://shazam.p.rapidapi.com/songs/v2/detect"
    headers = {
        "X-RapidAPI-Key": SHAZAM_KEY,
        "X-RapidAPI-Host": "shazam.p.rapidapi.com",
        "Content-Type": "application/octet-stream"
    }
    with open(file_path, "rb") as f:
        audio_data = f.read()

    results = []
    try:
        res = requests.post(url, headers=headers, data=audio_data).json()
        if "track" in res:
            title = res["track"]["title"]
            artist = res["track"]["subtitle"]
            line = f"{artist} — {title}"
            if "hub" in res["track"] and "actions" in res["track"]["hub"]:
                for action in res["track"]["hub"]["actions"]:
                    if action.get("uri"):
                        line += f" | [Слушать]({action['uri']})"
                        break
            results.append(line)
    except:
        pass
    return results

# ======== КОМАНДЫ БОТА ========

@dp.message(F.text == "/start")
async def start_cmd(message: types.Message):
    await message.answer(
        "🎧 Привет! Отправь мне .mp3 или голосовое — я найду все возможные совпадения.\n"
        f"Бесплатно: {FREE_LIMIT} запросов в день.\n"
        "Подписка (безлимит) — 299⭐ в месяц.\n"
        "Оплатить — /pay"
    )

@dp.message(F.text == "/pay")
async def pay_cmd(message: types.Message):
    prices = [LabeledPrice(label="Подписка 1 месяц", amount=299)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Подписка BeatScanner",
        description="1 месяц безлимитного поиска треков",
        payload="sub_month",
        provider_token="",
        currency="XTR",
        prices=prices
    )

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: types.Message):
    user_subscriptions.add(message.from_user.id)
    await message.answer("✅ Подписка активирована! Теперь запросы без ограничений.")

@dp.message(F.content_type.in_({ContentType.AUDIO, ContentType.VOICE}))
async def audio_handler(message: types.Message):
    user_id = message.from_user.id
    today = datetime.date.today()

    if user_id not in user_subscriptions:
        count = user_limits.get((user_id, today), 0)
        if count >= FREE_LIMIT:
            await message.answer("❌ Лимит бесплатных запросов исчерпан. Оплатите подписку — /pay")
            return
        user_limits[(user_id, today)] = count + 1

    await message.answer("🔍 Ищу совпадения... Это может занять 5–10 секунд.")

    file_id = message.audio.file_id if message.audio else message.voice.file_id
    file_info = await bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
    local_file = "temp.mp3"
    r = requests.get(file_url)
    with open(local_file, "wb") as f:
        f.write(r.content)

    all_results = []
    all_results.extend(get_all_matches_audd(local_file))
    all_results.extend(get_all_matches_acr(local_file))
    all_results.extend(get_all_matches_shazam(local_file))

    os.remove(local_file)

    if all_results:
        reply_text = "\n".join([f"{i+1}. {track}" for i, track in enumerate(all_results)])
        await message.reply(reply_text, disable_web_page_preview=True)
    else:
        await message.reply("❌ Трек не найден ни в одной базе.")

# === Запуск бота ===
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
