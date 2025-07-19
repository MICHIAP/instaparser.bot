import asyncio
import os
from instagrapi import Client
from openpyxl import Workbook

# Загружаем сессионный ключ из переменной окружения
SESSION_B64 = os.getenv("SESSION_B64")

# Запрашиваем username у пользователя
target_username = input("Введите username Instagram-аккаунта для парсинга: ")

async def main():
    # Подключение к Instagram
    cl = Client()
    cl.load_settings({})
    cl.set_locale('en_US')
    cl.set_timezone_offset(10800)
    cl.set_country_code(1)

    # Авторизация по session
    cl.set_device(cl.generate_device())
    cl.load_settings({})
    cl.login_by_sessionid(SESSION_B64)

    print(f"🔍 Парсим активную аудиторию с @{target_username}...")

    user_id = cl.user_id_from_username(target_username)
    medias = cl.user_medias(user_id, 10)

    active_users = set()

    for media in medias:
        # Сбор лайков
        likers = cl.media_likers(media.id)
        for liker in likers:
            active_users.add(liker.username)

        # Сбор комментариев
        comments = cl.media_comments(media.id, amount=100)
        for comment in comments:
            active_users.add(comment.user.username)

    print(f"✅ Найдено активных пользователей: {len(active_users)}")

    # Сбор email из bios
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Username", "Email"])

    for username in active_users:
        try:
            user_info = cl.user_info_by_username(username)
            bio = user_info.biography
            if "@" in bio:
                parts = bio.split()
                for part in parts:
                    if "@" in part and "." in part:
                        email = part.strip(",. \n")
                        sheet.append([username, email])
                        break
        except Exception as e:
            continue

    workbook.save("Результаты.xlsx")
    print("💾 Сохранено в файл Результаты.xlsx")

asyncio.run(main())
