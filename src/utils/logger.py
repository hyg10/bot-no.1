"""
Logging utility
"""
import logging
import sys
import os
from datetime import datetime


class Logger:
    """Custom logger — stdout + rotating file"""

    def __init__(self, name: str = "AdvancedBot", level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        self.logger.propagate = False  # 부모 logger로 전파 차단 (중복 출력 방지)

        self.logger.handlers = []

        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # ── Console handler (UTF-8 강제 — cp949 깨짐 방지) ─────────────
        import io
        utf8_stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        console_handler = logging.StreamHandler(utf8_stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # ── File handler ───────────────────────────────────────────────────
        try:
            log_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "logs"
            )
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "trading_bot.log")
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(getattr(logging, level.upper()))
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except Exception:
            pass  # 파일 핸들러 실패해도 콘솔 로그는 유지

    def _format_data(self, data):
        if isinstance(data, dict):
            items = [f"{k}={v}" for k, v in data.items()]
            return " | " + " | ".join(items)
        return f" | {data}"

    def debug(self, message: str, data: dict = None):
        msg = message + (self._format_data(data) if data else "")
        self.logger.debug(msg)

    def info(self, message: str, data: dict = None):
        msg = message + (self._format_data(data) if data else "")
        self.logger.info(msg)

    def warning(self, message: str, data: dict = None):
        msg = message + (self._format_data(data) if data else "")
        self.logger.warning(msg)

    def error(self, message: str, data: dict = None):
        msg = message + (self._format_data(data) if data else "")
        self.logger.error(msg)


from src.config.config import config
logger = Logger(level=config.log_level)
