from pydoc import doc

import yaml
from pathlib import Path
from collections import defaultdict

from .registry import Registry
from .web_grabber import grab_web_source
from .docx_grabber import grab_docx_source
from .logger import get_logger
from .doc_grabber import grab_doc_source

logger = get_logger()

CONFIG_PATH = Path("config/sources.yaml")
REGISTRY_PATH = Path("registry.json")
stats = {"new_web": 0, "new_docx": 0, "new_doc": 0, "skipped_unchanged": 0, "skipped_failed": 0, "errors": 0}


def load_sources(config_path: Path = CONFIG_PATH) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Не найден файл конфигурации {config_path}. "
            f"Создай его по примеру из config/sources.yaml"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run():
    logger.info("=== Запуск Grabber ===")

    sources = load_sources()
    web_sources = sources.get("web_sources", []) or []
    docx_sources = sources.get("docx_sources", []) or []
    doc_sources = sources.get("doc_sources", []) or []

    registry = Registry(str(REGISTRY_PATH))

    # defaultdict(int) - новые ключи появляются автоматически со значением 0,
    # такой баг больше не повторится ни для одного нового счётчика
    stats = defaultdict(int)

    # --- Веб-источники ---
    for url in web_sources:
        try:
            doc = grab_web_source(url, registry)
            if doc is not None:
                stats["new_web"] += 1
            elif registry.data.get(url) is not None:
                stats["skipped_unchanged"] += 1
            else:
                stats["skipped_failed"] += 1
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при обработке {url}: {e}")
            stats["errors"] += 1

    # --- Docx-источники ---
    for file_path in docx_sources:
        try:
            docs = grab_docx_source(file_path, registry)
            stats["new_docx"] += len(docs)
            if not docs:
                stats["skipped_unchanged"] += 1
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при обработке {file_path}: {e}")
            stats["errors"] += 1

    # --- Doc-источники ---
    for file_path in doc_sources:
        try:
            docs = grab_doc_source(file_path, registry)
            stats["new_doc"] += len(docs)
            if not docs:
                stats["skipped_unchanged"] += 1
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при обработке {file_path}: {e}")
            stats["errors"] += 1

    registry.save()

    logger.info(
        f"=== Готово. Новых веб-документов: {stats['new_web']}, "
        f"новых рецептов из docx: {stats['new_docx']}, "
        f"новых рецептов из doc: {stats['new_doc']}, "
        f"пропущено (без изменений): {stats['skipped_unchanged']}, "
        f"пропущено (ошибка обработки): {stats['skipped_failed']}, "
        f"ошибок: {stats['errors']} ==="
    )
    return dict(stats)


if __name__ == "__main__":
    run()