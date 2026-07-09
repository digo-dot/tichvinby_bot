#!/usr/bin/env python3
import logging
import os
import threading
from telegram import BotCommand
from telegram.ext import Application, CommandHandler
from flask import Flask, jsonify
from config import TELEGRAM_TOKEN, QUOTE_SEND_TIME, TZ
from handlers.commands import (
    start,
    help_command,
    schedule,
    week,
    month,
    news,
    eparchy,
    holiday,
    info,
    school,
    subscribe,
    unsubscribe,
    send_daily_quotes,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== Flask health-check сервер для Render =====
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return jsonify({"status": "ok", "bot": "running"})

@flask_app.route('/health')
def health_check():
    return jsonify({"status": "ok"})

def run_flask():
    """Запускает Flask-сервер на порту $PORT (Render)."""
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Flask health-check сервер запущен на порту {port}")
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
# =====


async def post_init(app: Application):
    """Установка меню команд при запуске бота."""
    commands = [
        BotCommand("start", "Приветствие 🙏"),
        BotCommand("help", "Помощь и справка"),
        BotCommand("schedule", "Расписание богослужений"),
        BotCommand("week", "Расписание на неделю"),
        BotCommand("month", "Расписание на месяц"),
        BotCommand("holiday", "Церковный праздник"),
        BotCommand("news", "Последние новости прихода"),
        BotCommand("eparchy", "Новости Брестской епархии"),
        BotCommand("info", "Информация о храме"),
        BotCommand("school", "Воскресная школа"),
        BotCommand("subscribe", "Подписаться на рассылку"),
        BotCommand("unsubscribe", "Отписаться от рассылки"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info(f"Установлено {len(commands)} команд в меню бота")


def main():
    # Запускаем Flask в отдельном потоке (он нужен только для health-check)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("schedule", schedule))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("month", month))
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CommandHandler("eparchy", eparchy))
    app.add_handler(CommandHandler("holiday", holiday))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("school", school))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))

    # Ежедневная рассылка цитат в 8:00 по минскому времени
    job_queue = app.job_queue
    hour, minute = QUOTE_SEND_TIME
    job_queue.run_daily(
        callback=lambda ctx: send_daily_quotes(ctx.application),
        time=__import__('datetime').time(hour, minute, 0),
        name="daily_quotes",
    )

    logger.info(f"Бот запущен и готов к работе! Ежедневная рассылка в {hour:02d}:{minute:02d}")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()