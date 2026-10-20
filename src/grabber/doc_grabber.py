import re
import shutil
import subprocess
from pathlib import Path
from docx import Document as DocxDocument

from .errors import SourceNotFoundError, ParsingError, ConversionError
from .logger import get_logger
from .models import RawDocument
from .registry import Registry

logger = get_logger()

RAW_DOC_DIR = Path("data/raw/doc")
RAW_DOC_DIR.mkdir(parents=True, exist_ok=True)

TEMP_CONVERTED_DIR = Path("data/temp_converted")
TEMP_CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

SOFFICE_PATH = shutil.which("soffice") or r"C:\Program Files\LibreOffice\program\soffice.exe"


# ---------- Конвертация .doc -> .docx ----------

def convert_doc_to_docx(doc_path: str) -> str:
    if not Path(SOFFICE_PATH).exists() and shutil.which("soffice") is None:
        raise ConversionError(
            f"LibreOffice не найден ({SOFFICE_PATH}). Установи LibreOffice или поправь SOFFICE_PATH."
        )

    try:
        result = subprocess.run(
            [SOFFICE_PATH, "--headless", "--convert-to", "docx",
             "--outdir", str(TEMP_CONVERTED_DIR), doc_path],
            capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        raise ConversionError(f"Таймаут конвертации {doc_path}")

    if result.returncode != 0:
        raise ConversionError(f"Ошибка конвертации {doc_path}: {result.stderr}")

    converted_path = TEMP_CONVERTED_DIR / (Path(doc_path).stem + ".docx")
    if not converted_path.exists():
        raise ConversionError(f"Файл не появился после конвертации: {converted_path}")

    return str(converted_path)


# ---------- Извлечение текста из текстовых блоков (карточек) ----------

def get_text(element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{W_NS}t"))


def significant_words(text: str) -> set:
    return set(re.findall(r"[а-яё]{4,}", text.lower()))


def extract_recipe_cards(docx_path: str) -> list[dict]:
    """
    Извлекает рецепты из docx, где текст хранится в text box'ах (карточки).
    Возвращает список {"title": str, "ingredients": str, "instructions": str}.
    """
    doc = DocxDocument(docx_path)
    raw_blocks = list(doc.element.iter(f"{W_NS}txbxContent"))

    if not raw_blocks:
        raise ParsingError(f"В файле не найдено текстовых блоков (карточек): {docx_path}")

    # Дедупликация: AlternateContent даёт по 2 копии каждого блока
    unique_blocks = []
    seen_texts = set()
    for block in raw_blocks:
        full_text = get_text(block).strip()
        if full_text and full_text not in seen_texts:
            seen_texts.add(full_text)
            unique_blocks.append((block, full_text))

    title_cards = []
    prep_texts = []

    i = 0
    while i < len(unique_blocks):
        block, text = unique_blocks[i]

        if text.startswith("Приготовление"):
            clean = text.replace("Приготовление:", "").replace("Приготовление", "").lstrip(": ").strip()
            prep_texts.append({"text": clean, "used": False})
            i += 1
            continue

        paragraphs = list(block.iter(f"{W_NS}p"))
        para_texts = [get_text(p) for p in paragraphs]
        para_texts = [p for p in para_texts if p.strip()]
        title = para_texts[0] if para_texts else "Без названия"
        ingredients = " ".join(para_texts[1:])

        # Быстрый путь: следующий блок сразу - инструкция
        instructions = ""
        if i + 1 < len(unique_blocks) and unique_blocks[i + 1][1].startswith("Приготовление"):
            next_text = unique_blocks[i + 1][1]
            instructions = next_text.replace("Приготовление:", "").replace("Приготовление", "").lstrip(": ").strip()
            prep_texts.append({"text": instructions, "used": True})
            i += 1

        title_cards.append({
            "title": title.strip(),
            "ingredients": ingredients.strip(),
            "instructions": instructions.strip(),
        })
        i += 1

    # Fallback: сопоставление "разъехавшихся" карточек по ключевым словам
    for card in title_cards:
        if card["instructions"]:
            continue
        ing_words = significant_words(card["ingredients"] + " " + card["title"])
        best_score, best_idx = 0, None
        for idx, prep in enumerate(prep_texts):
            if prep["used"]:
                continue
            score = len(ing_words & significant_words(prep["text"]))
            if score > best_score:
                best_score, best_idx = score, idx
        if best_idx is not None and best_score >= 2:
            card["instructions"] = prep_texts[best_idx]["text"]
            prep_texts[best_idx]["used"] = True
            logger.info(f"Fallback-сопоставление для '{card['title']}' (score={best_score})")

    for card in title_cards:
        if not card["instructions"]:
            logger.warning(f"Не найдена инструкция для рецепта: {card['title']}")

    return title_cards


# ---------- Полный цикл для одного .doc файла ----------

def grab_doc_source(file_path: str, registry: Registry) -> list[RawDocument]:
    path = Path(file_path)
    if not path.exists():
        logger.error(f"Файл не найден: {file_path}")
        return []

    try:
        docx_path = convert_doc_to_docx(file_path)
        recipes = extract_recipe_cards(docx_path)
    except (ConversionError, ParsingError) as e:
        logger.error(f"Пропускаю файл {file_path}: {e}")
        return []

    saved_docs = []

    for recipe in recipes:
        title = recipe["title"]
        content = f"{title}\n\n## Состав\n{recipe['ingredients']}\n\n## Приготовление\n{recipe['instructions']}"

        source_id = f"{file_path}::{title}"

        if not registry.is_new_or_changed(source_id=source_id, content=content):
            logger.info(f"Без изменений, пропускаю: {source_id}")
            continue

        safe_filename = registry.compute_hash(source_id)[:16] + ".txt"
        raw_path = RAW_DOC_DIR / safe_filename

        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(content)

        raw_doc = RawDocument(
            source_id=source_id,
            source_type="doc",
            title=title,
            content=content,
            content_hash=registry.compute_hash(content),
            raw_path=str(raw_path),
            extra_metadata={"source_file": file_path},
        )

        registry.update(source_id=source_id, content=content, raw_path=str(raw_path))
        logger.info(f"Сохранён новый/изменённый рецепт: {title} (из {file_path})")
        saved_docs.append(raw_doc)

    return saved_docs