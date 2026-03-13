import logging
import os
import re
import sys
from datetime import datetime

_STATUS_RE = re.compile(r'(?<=") (\d{3})\b')

class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG:    "\033[33m",
        logging.INFO:     "\033[32m",
        logging.WARNING:  "\033[38;5;208m",
        logging.ERROR:    "\033[31m",
        logging.CRITICAL: "\033[1;31m",
    }
    STATUS_COLORS = {
        2: "\033[32m",   # Green
        3: "\033[36m",   # Cyan
        4: "\033[33m",   # Yellow
        5: "\033[31m",   # Red
    }
    RESET = "\033[0m"

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created)
        s = dt.strftime(datefmt or "%H:%M:%S")
        return f"{s}.{record.msecs:03.0f}"

    def _colorize_status(self, match):
        code = match.group(1)
        color = self.STATUS_COLORS.get(int(code[0]), self.RESET)
        return f" {color}{code}{self.RESET}"

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        original = record.levelname
        record.levelname = f"{color}{original}{self.RESET}"
        result = super().format(record)
        record.levelname = original

        if record.name == "uvicorn.access":
            result = _STATUS_RE.sub(self._colorize_status, result)

        return result

class UvicornLevelFilter(logging.Filter):
    def filter(self, record):
        if record.name.startswith("uvicorn") and record.levelno == logging.INFO:
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        
        if record.levelno < logging.getLogger().level:
            return False
            
        return True

def setup_logging(level=None):
    if level is None:
        level = logging.DEBUG if os.getenv("BLOMBOORU_DEBUG") else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s"
    ))
    handler.addFilter(UvicornLevelFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

setup_logging()
logger = logging.getLogger("blombooru")
