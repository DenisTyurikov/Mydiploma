import asyncio
import logging
from aiogram import Bot, Dispatcher
from handlers import router  # Импортируем роутер из соседнего файла

# Вставьте сюда токен, который выдал BotFather
BOT_TOKEN = ""


async def main():
    # Включаем логирование, чтобы видеть в консоли, что происходит с ботом
    logging.basicConfig(level=logging.INFO)

    # Инициализируем бота и диспетчер
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем наш роутер к диспетчеру
    dp.include_router(router)

    print("Бот Luntara_testbot_v4 успешно запущен и готов к работе!")

    # Удаляем вебхуки (на всякий случай) и запускаем поллинг (постоянный опрос серверов Telegram)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Запуск асинхронного приложения
    asyncio.run(main())
