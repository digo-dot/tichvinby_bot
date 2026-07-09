import json
import logging
from datetime import date
from typing import Optional
import requests

logger = logging.getLogger(__name__)

API_URL = "https://azbyka.ru/worships/calendar/api"

MONTHS_RU = {
    1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
    5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
    9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
}


def get_holiday(target_date: date) -> Optional[str]:
    """
    Получить информацию о церковном празднике для указанной даты.
    Использует API: azbyka.ru/worships/calendar/api/YYYY-MM-DD/
    Возвращает строку с описанием или None, если не удалось получить.
    """
    day = target_date.day
    month = target_date.month
    year = target_date.year

    url = f"{API_URL}/{year}-{month:02d}-{day:02d}/"
    logger.info(f"Запрашиваю праздник: {url}")

    try:
        resp = requests.get(url, timeout=15)
        resp.encoding = 'utf-8'
        if resp.status_code != 200:
            logger.warning(f"HTTP {resp.status_code} для {url}")
            return None
    except requests.RequestException as e:
        logger.error(f"Ошибка запроса {url}: {e}")
        return None

    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError):
        logger.error(f"Ошибка парсинга JSON от {url}")
        return None

    month_ru = MONTHS_RU.get(month, '')
    date_line = f"📅 *{day} {month_ru} {year}*"

    lines = [date_line]

    # Седмица
    sedmica = data.get('sedmica', '')
    if sedmica:
        lines.append(f"\n📆 {sedmica}")

    # Питание
    food = data.get('food', '')
    if food:
        lines.append(f"🍽 {food}")

    # Глас
    tone = data.get('tone', '')
    if tone:
        lines.append(f"🎵 Глас {tone}")

    # События (праздники и память святых)
    events = data.get('events', [])
    if events:
        lines.append(f"\n📖 *Праздники и память святых:*")
        for ev in events:
            title = ev.get('title', '').strip()
            if title:
                lines.append(f"• {title}")

    # Чтения
    readings = data.get('ordinary_readings', [])
    if readings:
        lines.append(f"\n📖 *Чтения дня:*")
        for r in readings:
            r_title = r.get('title', '')
            apostle = r.get('apostle', '')
            gospel = r.get('gospel', '')
            parts = []
            if r_title:
                parts.append(r_title.capitalize())
            if apostle:
                parts.append(f"Ап.: {apostle}")
            if gospel:
                parts.append(f"Ев.: {gospel}")
            if parts:
                lines.append(f"• {' | '.join(parts)}")

    return '\n'.join(lines)
