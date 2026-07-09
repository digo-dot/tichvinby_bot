import asyncio
import json
import logging
from datetime import date, datetime
from telegram import Update
from telegram.ext import ContextTypes
from parsers.schedule import (
    get_schedule_for_today,
    get_schedule_for_tomorrow,
    get_schedule_for_weekday,
    get_schedule_for_date,
    get_schedule_for_week,
    get_month_entries_raw,
    format_day_short_with_holiday,
    MONTHS_RU_NOM,
)
from parsers.news import get_latest_news
from parsers.eparchy import get_eparchy_news
from parsers.holiday import get_holiday as fetch_holiday
from config import (
    CHURCH_ADDRESS,
    CHURCH_PHONE,
    CHURCH_EMAIL,
    CHURCH_SITE,
    CHURCH_SCHEDULE,
    SUNDAY_SCHOOL_INFO,
    QUOTES_FILE,
)

logger = logging.getLogger(__name__)

MAX_MSG_LEN = 4096

WEEKDAY_ALIASES = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс',
                   'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье',
                   'понедельника', 'вторника', 'среды', 'четверга', 'пятницы', 'субботы', 'воскресенья',
                   'воскресение', 'воскресенье']


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 Привет! Я бот храма Тихвинской иконы Божией Матери в г. Брест.\n\n"
        "Доступные команды:\n"
        "/schedule — расписание богослужений (с аргументами: завтра, день_недели, YYYY-MM-DD)\n"
        "/week — расписание на текущую неделю\n"
        "/month — расписание на текущий месяц\n"
        "/holiday [дата] — церковный праздник в этот день\n"
        "/info — адрес, телефон, время работы храма\n"
        "/school — информация о воскресной школе\n"
        "/news — последние новости прихода\n"
        "/eparchy — новости Брестской епархии\n"
        "/subscribe — подписаться на ежедневную рассылку цитат\n"
        "/unsubscribe — отписаться от рассылки\n"
        "/help — помощь"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 *Бот храма Тихвинской иконы Божией Матери*\n\n"
        "*Расписание:*\n"
        "/schedule [завтра|день_недели|ГГГГ-ММ-ДД] — расписание на день\n"
        "  Примеры:\n"
        "  /schedule — сегодня\n"
        "  /schedule завтра\n"
        "  /schedule понедельник\n"
        "  /schedule 2026-07-10\n"
        "/week — расписание на текущую неделю\n"
        "/month — расписание на текущий месяц\n\n"
        "*Праздники:*\n"
        "/holiday [ГГГГ-ММ-ДД] — церковный праздник в этот день (без даты — сегодня)\n\n"
        "*О храме:*\n"
        "/info — адрес, телефон, время работы\n"
        "/school — информация о воскресной школе\n"
        "/news — последние 5 новостей прихода\n"
        "/eparchy — последние 5 новостей Брестской епархии\n\n"
        "*Рассылка:*\n"
        "/subscribe — подписаться на ежедневную цитату дня в 8:00\n"
        "/unsubscribe — отписаться от рассылки\n\n"
        "/start — приветствие\n"
        "/help — эта справка"
    )


async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Загружаю расписание...")
    try:
        args = context.args
        if not args:
            text = get_schedule_for_today()
        else:
            arg = ' '.join(args).lower().strip()

            # завтра
            if arg in ('завтра', 'завтрашний'):
                text = get_schedule_for_tomorrow()

            # число в формате YYYY-MM-DD
            elif _is_date_format(arg):
                try:
                    target_date = datetime.strptime(arg[:10], '%Y-%m-%d').date()
                except ValueError:
                    target_date = None
                if target_date is None:
                    text = 'Неверный формат даты. Используйте ГГГГ-ММ-ДД.'
                else:
                    text = get_schedule_for_date(target_date)

            # день недели
            elif _is_weekday(arg):
                result = get_schedule_for_weekday(arg)
                if result is None:
                    text = f'Не удалось распознать день недели: {arg}'
                else:
                    text = result

            else:
                text = f'Не удалось распознать аргумент: {arg}. Используйте: завтра, день недели или дату в формате ГГГГ-ММ-ДД.'

    except Exception as e:
        text = f"Произошла ошибка при получении расписания: {e}"

    await update.message.reply_text(text, parse_mode='Markdown')


async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Загружаю расписание на неделю...")
    try:
        text = get_schedule_for_week()
    except Exception as e:
        text = f"Произошла ошибка: {e}"
    await update.message.reply_text(text, parse_mode='Markdown')


async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Загружаю расписание на месяц...")
    try:
        entries = get_month_entries_raw()
    except RuntimeError as e:
        await update.message.reply_text(f"Произошла ошибка: {e}")
        return
    except Exception as e:
        logger.exception("Ошибка при получении расписания на месяц")
        await update.message.reply_text(f"Произошла ошибка: {e}")
        return

    if not entries:
        today = date.today()
        month_name = MONTHS_RU_NOM.get(today.month, '')
        await update.message.reply_text(f"На {month_name} расписания нет.")
        return

    today = date.today()
    month_name = MONTHS_RU_NOM.get(today.month, '')

    # Формируем все строки дней (праздники уже включены в format_day_short_with_holiday)
    day_lines = [format_day_short_with_holiday(e) for e in entries]

    # Разбиваем на части по лимиту символов, а не по количеству дней
    parts = []
    current_chunk = []
    current_len = 0

    # Резервируем место под самый длинный заголовок (≈80 символов)
    header_reserve = 80

    for line in day_lines:
        line_len = len(line) + 1  # +1 за перевод строки
        # Если строка сама по себе больше лимита — режем её
        if line_len > MAX_MSG_LEN - header_reserve:
            # Разбиваем строку дня на части по 4000 символов
            for i in range(0, len(line), MAX_MSG_LEN - header_reserve):
                truncated = line[i:i + MAX_MSG_LEN - header_reserve]
                # Убедимся, что не режем посередине эмодзи/символа
                parts.append([truncated])
            continue

        # Если добавление строки превысит лимит — начинаем новую часть
        if current_len + line_len > MAX_MSG_LEN - header_reserve:
            if current_chunk:
                parts.append(current_chunk)
            current_chunk = [line]
            current_len = line_len
        else:
            current_chunk.append(line)
            current_len += line_len

    if current_chunk:
        parts.append(current_chunk)

    total_parts = len(parts)

    for idx, chunk in enumerate(parts):
        part_num = idx + 1
        header = f"📅 *Расписание на {month_name} {today.year} (часть {part_num}/{total_parts})*\n"
        body = '\n'.join(chunk)

        full_text = header + body

        # Финальная проверка длины (на случай, если заголовок длиннее резерва)
        if len(full_text) > MAX_MSG_LEN:
            # Отправляем без Markdown, если не влезает
            logger.warning(f"Часть {part_num}/{total_parts} превышает {MAX_MSG_LEN} символов, отправляю без Markdown")
            await update.message.reply_text(full_text)
        else:
            try:
                await update.message.reply_text(full_text, parse_mode='Markdown')
            except Exception as e:
                logger.warning(f"Ошибка Markdown в части {part_num}/{total_parts}: {e}, отправляю без форматирования")
                await update.message.reply_text(full_text)

        await asyncio.sleep(0.5)


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Загружаю новости...")
    try:
        text = get_latest_news(count=5)
    except Exception as e:
        text = f"Произошла ошибка при получении новостей: {e}"
    await update.message.reply_text(text, parse_mode='Markdown', disable_web_page_preview=True)


async def eparchy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает последние новости Брестской епархии."""
    await update.message.reply_text("⏳ Загружаю новости епархии...")
    try:
        text = get_eparchy_news(count=5)
    except Exception as e:
        text = f"Произошла ошибка при получении новостей епархии: {e}"
    await update.message.reply_text(text, parse_mode='Markdown', disable_web_page_preview=True)


def _is_weekday(arg: str) -> bool:
    for alias in WEEKDAY_ALIASES:
        if arg.startswith(alias[:2]):
            return True
    return False


def _is_date_format(arg: str) -> bool:
    # Проверяем, похоже ли на дату YYYY-MM-DD
    parts = arg.split('-')
    if len(parts) == 3:
        if all(p.isdigit() for p in parts):
            if len(parts[0]) == 4 and 1 <= int(parts[1]) <= 12 and 1 <= int(parts[2]) <= 31:
                return True
    return False


# ===== Вспомогательные функции для подписок =====

def _get_subscribers_file() -> str:
    """Путь к файлу с chat_id подписчиков."""
    return "subscribers.txt"


def _load_subscribers() -> set:
    """Загрузить set chat_id подписчиков из файла."""
    path = _get_subscribers_file()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return {int(line.strip()) for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def _save_subscribers(subscribers: set):
    """Сохранить set chat_id подписчиков в файл."""
    path = _get_subscribers_file()
    with open(path, 'w', encoding='utf-8') as f:
        for cid in subscribers:
            f.write(f"{cid}\n")


def _load_quotes() -> list:
    """Загрузить список цитат из quotes.json."""
    try:
        with open(QUOTES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [(q['text'], q['author']) for q in data]
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.error(f"Ошибка загрузки цитат: {e}")
        return []


def _get_daily_quote() -> str:
    """Выбрать цитату дня на основе текущей даты (детерминированно)."""
    quotes = _load_quotes()
    if not quotes:
        return "🙏 *Цитата дня*\n\nБог да благословит вас!"
    # Выбираем цитату по дню года, чтобы каждый день была разная
    day_of_year = date.today().timetuple().tm_yday
    idx = (day_of_year - 1) % len(quotes)
    text, author = quotes[idx]
    return f"🙏 *Цитата дня*\n\n«{text}»\n\n— {author}"


# ===== Команды =====

async def holiday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает церковный праздник в указанную дату."""
    await update.message.reply_text("⏳ Ищу праздник...")
    try:
        args = context.args
        if args:
            arg = ' '.join(args).strip()
            if _is_date_format(arg):
                target_date = datetime.strptime(arg[:10], '%Y-%m-%d').date()
            else:
                await update.message.reply_text(
                    "Неверный формат. Используйте: /holiday ГГГГ-ММ-ДД\n"
                    "Например: /holiday 2026-07-07"
                )
                return
        else:
            target_date = date.today()

        result = await asyncio.to_thread(fetch_holiday, target_date)
        if result:
            await update.message.reply_text(result, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                f"Не удалось получить информацию о празднике на {target_date.strftime('%d.%m.%Y')}."
            )
    except Exception as e:
        logger.exception("Ошибка в команде /holiday")
        await update.message.reply_text(f"Произошла ошибка: {e}")


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает адрес, телефон, время работы храма."""
    text = (
        f"🏛 *{CHURCH_SCHEDULE.split(chr(10))[0]}*\n\n"
        f"📍 *Адрес:* {CHURCH_ADDRESS}\n"
        f"📞 *Телефон:* {CHURCH_PHONE}\n"
        f"🌐 *Сайт:* {CHURCH_SITE}\n\n"
        f"{CHURCH_SCHEDULE}"
    )
    await update.message.reply_text(text, parse_mode='Markdown', disable_web_page_preview=True)


async def school(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о воскресной школе."""
    await update.message.reply_text(SUNDAY_SCHOOL_INFO, parse_mode='Markdown')


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписаться на ежедневную рассылку цитат."""
    user_id = update.effective_user.id
    subscribers = _load_subscribers()
    if user_id in subscribers:
        await update.message.reply_text("✅ Вы уже подписаны на ежедневную рассылку цитат.")
        return
    subscribers.add(user_id)
    _save_subscribers(subscribers)
    logger.info(f"Пользователь {user_id} подписался на рассылку")
    await update.message.reply_text(
        "✅ Вы подписались на ежедневную рассылку цитат святых отцов!\n"
        "Каждое утро в 8:00 я буду присылать вам вдохновляющую цитату. 🙏"
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отписаться от ежедневной рассылки цитат."""
    user_id = update.effective_user.id
    subscribers = _load_subscribers()
    if user_id not in subscribers:
        await update.message.reply_text("❌ Вы не были подписаны на рассылку.")
        return
    subscribers.discard(user_id)
    _save_subscribers(subscribers)
    logger.info(f"Пользователь {user_id} отписался от рассылки")
    await update.message.reply_text(
        "❌ Вы отписались от ежедневной рассылки цитат.\n"
        "Если захотите возобновить — просто напишите /subscribe 🙏"
    )


async def send_daily_quotes(app):
    """
    Ежедневная рассылка цитат всем подписанным пользователям.
    Вызывается из JobQueue.
    """
    subscribers = _load_subscribers()
    if not subscribers:
        logger.info("Нет подписчиков для ежедневной рассылки")
        return

    quote_text = _get_daily_quote()
    logger.info(f"Рассылаю цитату дня {len(subscribers)} подписчикам")

    for chat_id in subscribers:
        try:
            await app.bot.send_message(chat_id=chat_id, text=quote_text, parse_mode='Markdown')
            await asyncio.sleep(0.05)  # небольшая задержка между отправками
        except Exception as e:
            logger.warning(f"Не удалось отправить цитату пользователю {chat_id}: {e}")
            # Если пользователь заблокировал бота — отписываем
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                subscribers.discard(chat_id)
                logger.info(f"Пользователь {chat_id} удалён из подписчиков (бот заблокирован)")

    _save_subscribers(subscribers)
    logger.info("Рассылка цитат завершена")
