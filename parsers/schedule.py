import re
import time
from datetime import date, timedelta, datetime
import requests
from bs4 import BeautifulSoup, Tag
from config import SCHEDULE_URL

MONTHS_RU = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
}
MONTHS_RU_NOM = {
    1: 'январь', 2: 'февраль', 3: 'март', 4: 'апрель', 5: 'май', 6: 'июнь',
    7: 'июль', 8: 'август', 9: 'сентябрь', 10: 'октябрь', 11: 'ноябрь', 12: 'декабрь'
}

WEEKDAYS_RU = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
WEEKDAYS_RU_EXTRA = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресение', 'воскресенье']

DATE_RE = re.compile(r'(\d{1,2})\s+([а-яё]+)')

_cache = {}
_CACHE_TTL = 3600


def _is_cache_valid():
    return bool(_cache) and (time.time() - _cache['ts'] < _CACHE_TTL)


def _extract_date_text(cell) -> str:
    for elem in cell.find_all(['p', 'div']):
        txt = elem.get_text(strip=True)
        if txt and DATE_RE.search(txt):
            return txt
    full_text = cell.get_text(' ', strip=True)
    m = DATE_RE.search(full_text)
    if m:
        return m.group(0)
    return ''


def _parse_date(text: str):
    m = DATE_RE.search(text)
    if not m:
        return None
    day_num = int(m.group(1))
    month_name = m.group(2).lower()
    month_num = MONTHS_RU.get(month_name)
    if month_num is None:
        return None
    return day_num, month_num


def _clean_service_text(text: str) -> str:
    """Подчистить текст службы: пробелы после времени, вокруг скобок."""
    text = re.sub(r'(\d{1,2}\.\d{2})([А-Яа-яA-Za-z])', r'\1 \2', text)
    text = re.sub(r'([.\w)])(\()', r'\1 \2', text)
    text = re.sub(r'(\))([А-Яа-яA-Za-z])', r'\1 \2', text)
    text = re.sub(r'(\)\.)([А-Яа-яA-Za-z])', r'\1 \2', text)
    return text


def _parse_row(row: Tag, year: int):
    """Распарсить одну строку таблицы. Вернуть словарь или None."""
    cells = row.find_all('td')
    if len(cells) < 2:
        return None

    date_text_raw = _extract_date_text(cells[0])
    parsed = _parse_date(date_text_raw)
    if parsed is None:
        return None

    day_num, month_num = parsed
    d = date(year, month_num, day_num)
    if d < date.today() - timedelta(days=180):
        d = date(year + 1, month_num, day_num)

    # --- Парсим содержимое второй ячейки ---
    td = cells[1]
    date_text_full = cells[0].get_text(' ', strip=True)

    # Извлекаем праздник (первый <p><strong>...</strong></p>)
    holiday = ''
    first_strong_p = td.find('p', recursive=True)
    if first_strong_p:
        strong = first_strong_p.find('strong')
        if strong:
            holiday = strong.get_text(' ', strip=True)

    # Извлекаем службы: все <p> содержащие <strong> со временем (X.XX)
    services = []
    for p in td.find_all('p', recursive=True):
        strong = p.find('strong')
        if not strong:
            continue
        time_text = strong.get_text(strip=True)
        # Проверяем, похоже ли на время (ЧЧ.ММ или Ч.ММ)
        if not re.match(r'^\d{1,2}\.\d{2}$', time_text):
            continue
        # Весь текст параграфа — это строка службы
        full_text = p.get_text(' ', strip=True)
        full_text = _clean_service_text(full_text)
        services.append(full_text)

    return {
        'date': d,
        'weekday': WEEKDAYS_RU[d.weekday()],
        'holiday': holiday,
        'services': services,
        'date_text': date_text_full,
    }


def parse_full_schedule() -> list:
    """
    Загрузить и распарсить всю страницу расписания.
    Возвращает список словарей:
    [{"date": datetime.date, "weekday": str, "holiday": str,
      "services": List[str], "date_text": str}, ...]
    Результат кешируется на 1 час.
    """
    if _is_cache_valid():
        return _cache['entries']

    try:
        html = requests.get(SCHEDULE_URL, timeout=15)
        html.encoding = 'utf-8'
    except requests.RequestException:
        raise RuntimeError("Ошибка при получении расписания с сайта.")

    soup = BeautifulSoup(html.text, 'html.parser')
    newsitem = soup.find('div', class_='newsitem_text')
    if not newsitem:
        raise RuntimeError("Не удалось найти расписание на сайте.")

    tables = newsitem.find_all('table')
    if not tables:
        raise RuntimeError("Не удалось найти таблицу с расписанием.")

    current_year = date.today().year
    entries = []

    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            parsed = _parse_row(row, current_year)
            if parsed:
                entries.append(parsed)

    _cache['ts'] = time.time()
    _cache['entries'] = entries
    return entries


# ===== Публичные функции на основе parse_full_schedule =====

def format_day_full(entry: dict) -> str:
    """Полный вывод дня: заголовок + праздник + все службы."""
    weekday_cap = entry['weekday'].capitalize()
    lines = [f"*{weekday_cap}, {entry['date_text']}*"]
    if entry['holiday']:
        lines.append(f"_{entry['holiday']}_")
    lines.append('')
    for svc in entry['services']:
        lines.append(f"🕰 {svc}")
    return '\n'.join(lines)


def format_day_short(entry: dict) -> str:
    """Краткий вывод дня: дата + праздник + все службы."""
    d = entry['date']
    weekday_short = entry['weekday'][:3]
    if not entry['services']:
        return f"▫️ *{d.day:02d}.{d.month:02d} ({weekday_short})* — _нет служб_"
    
    # Первая строка: дата и первая служба
    lines = [f"▫️ *{d.day:02d}.{d.month:02d} ({weekday_short})* — {entry['services'][0]}"]
    # Остальные службы — с новой строки и отступом
    for svc in entry['services'][1:]:
        lines.append(f"  🕰 {svc}")
    return '\n'.join(lines)


def format_day_short_with_holiday(entry: dict) -> str:
    """Краткий вывод дня: дата + праздник + все службы."""
    d = entry['date']
    weekday_short = entry['weekday'][:3]
    if not entry['services']:
        return f"▫️ *{d.day:02d}.{d.month:02d} ({weekday_short})* — _нет служб_"
    
    # Первая строка: дата + праздник (если есть) + первая служба
    day_line = f"▫️ *{d.day:02d}.{d.month:02d} ({weekday_short})*"
    if entry['holiday']:
        day_line += f" _{entry['holiday']}_"
    day_line += f" — {entry['services'][0]}"
    
    lines = [day_line]
    # Остальные службы — с новой строки и отступом
    for svc in entry['services'][1:]:
        lines.append(f"  🕰 {svc}")
    return '\n'.join(lines)


def get_month_entries_raw() -> list:
    """Возвращает список записей расписания за текущий месяц (сырые dict'ы)."""
    today = date.today()
    start = date(today.year, today.month, 1)
    if today.month == 12:
        end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(today.year, today.month + 1, 1) - timedelta(days=1)

    all_entries = parse_full_schedule()
    return [e for e in all_entries if start <= e['date'] <= end]


def get_schedule_for_date(target_date: date) -> str:
    try:
        entries = parse_full_schedule()
    except RuntimeError as e:
        return str(e)

    for entry in entries:
        if entry['date'] == target_date:
            return format_day_full(entry)

    return f"На {target_date.strftime('%d.%m.%Y')} расписания нет."


def get_schedule_for_today() -> str:
    return get_schedule_for_date(date.today())


def get_schedule_for_tomorrow() -> str:
    return get_schedule_for_date(date.today() + timedelta(days=1))


def get_schedule_for_weekday(weekday_name: str):
    target_num = None
    for idx, name in enumerate(WEEKDAYS_RU_EXTRA):
        if weekday_name.lower().startswith(name[:3]):
            target_num = idx % 7
            break
    if target_num is None:
        return None

    today = date.today()
    current_weekday = today.weekday()
    days_ahead = target_num - current_weekday
    if days_ahead <= 0:
        days_ahead += 7
    target_date = today + timedelta(days=days_ahead)
    return get_schedule_for_date(target_date)


def get_schedule_for_week() -> str:
    today = date.today()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)

    try:
        all_entries = parse_full_schedule()
    except RuntimeError as e:
        return str(e)

    week_entries = [e for e in all_entries if start <= e['date'] <= end]
    if not week_entries:
        return "На текущую неделю расписания нет."

    result = [f"📅 *Расписание на неделю* ({start.strftime('%d.%m')} – {end.strftime('%d.%m')})\n"]
    for entry in week_entries:
        result.append(format_day_full(entry))
        result.append('')

    return '\n'.join(result).strip()


def get_schedule_for_month() -> str:
    today = date.today()
    start = date(today.year, today.month, 1)
    if today.month == 12:
        end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(today.year, today.month + 1, 1) - timedelta(days=1)

    try:
        all_entries = parse_full_schedule()
    except RuntimeError as e:
        return str(e)

    month_entries = [e for e in all_entries if start <= e['date'] <= end]
    if not month_entries:
        month_name = MONTHS_RU_NOM.get(today.month, '')
        return f"На {month_name} расписания нет."

    month_name = MONTHS_RU_NOM.get(today.month, '')
    result = [f"📅 *Расписание на {month_name} {today.year}*\n"]
    for entry in month_entries:
        result.append(format_day_short(entry))

    return '\n'.join(result).strip()


# Совместимость со старым вызовом
get_schedule_for_today.__doc__ = "Расписание на сегодня (полный вывод)"
get_schedule_for_tomorrow.__doc__ = "Расписание на завтра"
get_schedule_for_weekday.__doc__ = "Расписание на ближайший день недели"
get_schedule_for_week.__doc__ = "Расписание на текущую неделю (полный вывод)"
get_schedule_for_month.__doc__ = "Расписание на текущий месяц (краткий вывод)"