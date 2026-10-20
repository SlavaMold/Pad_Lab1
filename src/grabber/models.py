from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class RawDocument:
    source_id: str        # уникальный ID источника (например, URL или путь к файлу)
    source_type: str      # "web" или "docx"
    title: str            # заголовок рецепта/страницы
    content: str           # сырой текст, который потом пойдёт в processing
    content_hash: str      # SHA-256 хэш содержимого — для дедупликации
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    raw_path: str = ""     # куда сохранили файл на диске
    extra_metadata: dict = field(default_factory=dict)  # например, автор рецепта, дата публикации