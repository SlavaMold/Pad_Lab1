import logging
from pathlib import Path

def get_logger(name: str = "grabber") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # чтобы не плодить дублирующиеся хендлеры при повторном вызове
        return logger

    logger.setLevel(logging.INFO)

    Path("logs").mkdir(exist_ok=True)

    # Вывод в файл
    file_handler = logging.FileHandler("logs/grabber.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    ))

    # Вывод в консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger