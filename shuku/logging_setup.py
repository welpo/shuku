import logging
from typing import Any, Optional

# Custom SUCCESS level.
SUCCESS = 25  # between INFO (20) and WARNING (30)


LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "success": SUCCESS,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}
DEFAULT_LOG_LEVEL_NAME = "info"
DEFAULT_LOG_LEVEL = LOG_LEVELS[DEFAULT_LOG_LEVEL_NAME]


def addLoggingLevel(
    levelName: str, levelNum: int, methodName: Optional[str] = None
) -> None:
    if not methodName:
        methodName = levelName.lower()

    if hasattr(logging, levelName):
        raise AttributeError(f"{levelName} already defined in logging module")
    if hasattr(logging, methodName):
        raise AttributeError(f"{methodName} already defined in logging module")
    if hasattr(logging.getLoggerClass(), methodName):
        raise AttributeError(f"{methodName} already defined in logger class")

    def logForLevel(
        self: logging.Logger, message: Any, *args: Any, **kwargs: Any
    ) -> None:
        if self.isEnabledFor(levelNum):
            self._log(levelNum, message, args, **kwargs)

    def logToRoot(message: Any, *args: Any, **kwargs: Any) -> None:
        logging.log(levelNum, message, *args, **kwargs)

    logging.addLevelName(levelNum, levelName)
    setattr(logging, levelName, levelNum)
    setattr(logging.getLoggerClass(), methodName, logForLevel)
    setattr(logging, methodName, logToRoot)


addLoggingLevel("SUCCESS", SUCCESS)


class CuteFormatter(logging.Formatter):
    def format(self, record):
        emoji = {
            logging.DEBUG: "🐛",
            logging.INFO: "💬️",
            SUCCESS: "✅",
            logging.WARNING: "⚠️ ",
            logging.ERROR: "❌",
            logging.CRITICAL: "🚨",
        }.get(record.levelno, "💬️")

        return f"[{self.formatTime(record, '%H:%M:%S')}] {emoji} {record.getMessage()}"


def setup_initial_logging(
    initial_loglevel: Optional[str] = None,
    log_file: Optional[str] = None,
) -> None:
    if initial_loglevel:
        initial_level = LOG_LEVELS.get(initial_loglevel.lower(), DEFAULT_LOG_LEVEL)
    else:
        initial_level = DEFAULT_LOG_LEVEL
    root_logger = logging.getLogger()
    root_logger.setLevel(initial_level)
    cute_formatter = CuteFormatter()
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(cute_formatter)
    root_logger.addHandler(console_handler)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(cute_formatter)
            root_logger.addHandler(file_handler)
            logging.info(f"File logging enabled. Log file: {log_file}")
        except Exception as e:
            logging.error(f"Failed to set up file logging to {log_file}: {str(e)}")


def update_logging_level(loglevel: str) -> None:
    loglevel = loglevel.lower()
    if loglevel not in LOG_LEVELS:
        raise ValueError(
            f"Invalid loglevel level: '{loglevel}'. Choose from {', '.join(LOG_LEVELS.keys())}."
        )
    logging.getLogger().setLevel(LOG_LEVELS[loglevel])
