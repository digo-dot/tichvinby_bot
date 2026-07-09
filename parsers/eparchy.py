import re
import requests
from bs4 import BeautifulSoup
from config import PRAVBREST_URL


def get_eparchy_news(count: int = 5) -> str:
    """Парсит последние новости с сайта Брестской епархии (pravbrest.by)."""
    try:
        html = requests.get(PRAVBREST_URL, timeout=15)
        html.encoding = 'utf-8'
    except requests.RequestException:
        return "Ошибка при получении новостей епархии."

    soup = BeautifulSoup(html.text, 'html.parser')
    articles = soup.find_all('div', class_='post-details')

    if not articles:
        return "Новости епархии не найдены."

    result_lines = []
    for i, article in enumerate(articles):
        if i >= count:
            break

        # Заголовок
        title_tag = article.find('h2', class_='post-title')
        if not title_tag:
            continue

        link_tag = title_tag.find('a')
        if link_tag:
            title = link_tag.get_text(strip=True)
            href = link_tag.get('href', '')
        else:
            title = title_tag.get_text(strip=True)
            href = ''

        # Дата
        date_span = article.find('span', class_='date')
        date_str = date_span.get_text(strip=True) if date_span else ''

        # Краткое описание
        excerpt_p = article.find('p', class_='post-excerpt')
        snippet = ''
        if excerpt_p:
            snippet = excerpt_p.get_text(strip=True)

        # Очищаем от лишних пробелов
        snippet = re.sub(r'\s+', ' ', snippet).strip()
        if len(snippet) > 150:
            snippet = snippet[:147] + '...'

        result_lines.append(f"🔹 *{title}*")
        if date_str:
            result_lines.append(f"   📅 {date_str}")
        if href:
            result_lines.append(f"   [Читать]({href})")
        if snippet:
            result_lines.append(f"   _{snippet}_")
        result_lines.append('')

    if not result_lines:
        return "Новости епархии не найдены."

    header = f"📰 *Новости Брестской епархии*\n\n"
    return header + '\n'.join(result_lines)