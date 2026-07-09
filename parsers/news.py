import re
import requests
from bs4 import BeautifulSoup
from config import NEWS_URL


def get_latest_news(count: int = 5) -> str:
    try:
        html = requests.get(NEWS_URL, timeout=15)
        html.encoding = 'utf-8'
    except requests.RequestException:
        return "Ошибка при получении новостей с сайта."

    soup = BeautifulSoup(html.text, 'html.parser')
    news_block = soup.find('div', class_='yjsg-newsitems')
    if not news_block:
        return "Не удалось найти новости на сайте."

    articles = news_block.find_all('div', class_='yjsgarticle')
    if not articles:
        return "Новости не найдены."

    result_lines = []
    for i, article in enumerate(articles):
        if i >= count:
            break

        title_tag = article.find('h2', class_='article_title')
        if not title_tag:
            title_tag = article.find('h2')
        if not title_tag:
            continue

        link_tag = title_tag.find('a')
        if link_tag:
            title = link_tag.get_text(strip=True)
            href = link_tag.get('href', '')
            if href and not href.startswith('http'):
                href = NEWS_URL.rstrip('/') + '/' + href.lstrip('/')
        else:
            title = title_tag.get_text(strip=True)
            href = ''

        text_div = article.find('div', class_='newsitem_text')
        snippet = ''
        if text_div:
            for p in text_div.find_all('p', recursive=True):
                txt = p.get_text(strip=True)
                if txt and len(txt) > 20:
                    snippet = txt
                    break
            if not snippet:
                snippet = text_div.get_text(strip=True)[:200]

        # Очищаем от лишних пробелов
        snippet = re.sub(r'\s+', ' ', snippet).strip()
        if len(snippet) > 150:
            snippet = snippet[:147] + '...'

        result_lines.append(f"🔹 *{title}*")
        if href:
            result_lines.append(f"   [Читать]({href})")
        if snippet:
            result_lines.append(f"   _{snippet}_")
        result_lines.append('')

    if not result_lines:
        return "Новости не найдены."

    header = f"📰 *Последние новости*\n\n"
    return header + '\n'.join(result_lines)