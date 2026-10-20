import time
import functools
from .errors import SourceUnavailableError
from .logger import get_logger

logger = get_logger()

def retry_on_failure(max_attempts: int = 3, initial_delay: float = 2.0, backoff: float = 2.0):
    """
    Декоратор для повторных попыток при временных сбоях.
    max_attempts — сколько раз пробовать всего
    initial_delay — пауза перед первым повтором (в секундах)
    backoff — во сколько раз увеличивается пауза после каждой неудачи (exponential backoff)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except SourceUnavailableError as e:
                    last_exception = e
                    logger.warning(
                        f"Попытка {attempt}/{max_attempts} не удалась для {func.__name__}: {e}"
                    )
                    if attempt < max_attempts:
                        logger.info(f"Повтор через {delay:.1f} сек...")
                        time.sleep(delay)
                        delay *= backoff  # экспоненциально увеличиваем паузу: 2с → 4с → 8с

            logger.error(f"Все {max_attempts} попыток исчерпаны для {func.__name__}")
            raise last_exception

        return wrapper
    return decorator