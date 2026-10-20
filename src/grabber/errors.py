class GrabberError(Exception):
    """Базовая ошибка граббера."""
    pass

class SourceUnavailableError(GrabberError):
    """Источник временно недоступен (сеть, таймаут, 5xx-ошибка сервера) — стоит повторить попытку."""
    pass

class SourceNotFoundError(GrabberError):
    """Источник не существует (404, файл удалён) — повторять бессмысленно."""
    pass

class ParsingError(GrabberError):
    """Контент получен, но не удалось его распарсить/прочитать."""
    pass
class SourceForbiddenError(GrabberError):
    """Доступ к источнику запрещён (403) — обычно блокировка бота, повторять бессмысленно."""
    pass
class ConversionError(GrabberError):
    """Не удалось сконвертировать .doc в .docx через LibreOffice."""
    pass