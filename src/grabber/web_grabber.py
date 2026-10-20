import requests
from bs4 import BeautifulSoup
from pathlib import Path
import trafilatura

from .errors import SourceForbiddenError, SourceUnavailableError, SourceNotFoundError, ParsingError
from .retry import retry_on_failure
from .logger import get_logger
from .models import RawDocument
from .registry import Registry

logger = get_logger()

RAW_WEB_DIR = Path("data/raw/web")
RAW_WEB_DIR.mkdir(parents=True, exist_ok=True)
TRAILING_BOILERPLATE_MARKERS = [
    "похожие рецепты",
    "видео рецепт",
    "оценить рецепт",
    "категории рецепта",
    "показать все комментарии",
    "добавить комментарий",
    "все права на материалы",
    "смотреть ещё лучшие рецепты",
    "запомнить и поделиться",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Educational RAG project; recipe-grabber/1.0)"
}

stats = {"new_web": 0, "new_docx": 0, "new_doc": 0, "skipped_unchanged": 0, "skipped_failed": 0, "errors": 0}

def _trim_leading_boilerplate(text: str, title: str) -> str:
    """Обрезает всё до первого вхождения заголовка - убирает меню/навигацию в начале."""
    if not title:
        return text
    idx = text.find(title)
    return text[idx:] if idx > 0 else text


def _trim_trailing_boilerplate(text: str) -> str:
    """Обрезает текст на первом найденном маркере 'хвостового' мусора."""
    lower = text.lower()
    positions = [lower.find(m) for m in TRAILING_BOILERPLATE_MARKERS]
    positions = [p for p in positions if p != -1]
    return text[:min(positions)].strip() if positions else text



@retry_on_failure(max_attempts=3, initial_delay=2.0)
def fetch_page(url: str) -> str:
    """Скачивает сырой HTML по URL. Поднимает SourceUnavailableError для временных сбоев."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
    except requests.exceptions.Timeout:
        raise SourceUnavailableError(f"Таймаут при запросе {url}")
    except requests.exceptions.ConnectionError:
        raise SourceUnavailableError(f"Ошибка соединения с {url}")

    if response.status_code == 403:
        raise SourceForbiddenError(f"Доступ запрещён (403), вероятно блокировка бота: {url}")
    if response.status_code == 404:
        raise SourceNotFoundError(f"Страница не найдена (404): {url}")
    if response.status_code == 429 or response.status_code >= 500:
        raise SourceUnavailableError(f"Сервер вернул {response.status_code} для {url}")

    response.raise_for_status()  # на случай других 4xx кодов — упадёт сразу, без retry
    return response.text


def parse_recipe_html(html: str, url: str) -> tuple[str, str]:
    try:
        clean_text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            # favor_precision убрали - ломал recall на russianfood.com
        )
        metadata = trafilatura.extract_metadata(html)
        title = metadata.title.strip() if metadata and metadata.title else None
        if not title:
            soup = BeautifulSoup(html, "html.parser")
            title_tag = soup.find("h1") or soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else url

        if not clean_text or len(clean_text) < 50:
            raise ParsingError(f"Слишком мало текста извлечено из {url}")

        clean_text = _trim_leading_boilerplate(clean_text, title)
        clean_text = _trim_trailing_boilerplate(clean_text)

        if len(clean_text) < 50:
            raise ParsingError(f"После очистки от шаблонного мусора осталось мало текста: {url}")

        return title, clean_text.strip()

    except ParsingError:
        raise
    except Exception as e:
        raise ParsingError(f"Не удалось распарсить {url}: {e}")
    

def grab_web_source(url: str, registry: Registry) -> RawDocument | None:
    """
    Полный цикл для одного веб-источника:
    скачать -> распарсить -> проверить дубликат -> сохранить.
    Возвращает RawDocument, если документ новый/изменился, иначе None.
    """
    try:
        html = fetch_page(url)
        title, clean_text = parse_recipe_html(html, url)
    except (SourceUnavailableError, SourceNotFoundError, ParsingError) as e:
        logger.error(f"Пропускаю источник {url}: {e}")
        return None
    except (SourceUnavailableError, SourceNotFoundError, SourceForbiddenError, ParsingError) as e:
        logger.error(f"Пропускаю источник {url}: {e}")
        return None

    # Проверка через реестр: новый ли контент?
    if not registry.is_new_or_changed(source_id=url, content=clean_text):
        logger.info(f"Без изменений, пропускаю: {url}")
        return None

    # Сохранение на диск: имя файла делаем безопасным через hash URL
    safe_filename = registry.compute_hash(url)[:16] + ".txt"
    raw_path = RAW_WEB_DIR / safe_filename

    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(clean_text)

    doc = RawDocument(
        source_id=url,
        source_type="web",
        title=title,
        content=clean_text,
        content_hash=registry.compute_hash(clean_text),
        raw_path=str(raw_path),
        extra_metadata={"url": url},
    )

    registry.update(source_id=url, content=clean_text, raw_path=str(raw_path))
    logger.info(f"Сохранён новый/изменённый документ: {title} ({url})")

    return doc