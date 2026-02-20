"""
Logging configuration — reusable daily-rotating file + console logger.
"""

import logging
import logging.handlers
import os


def setup_logger(name: str, log_dir: str | None = None) -> logging.Logger:
    """Create a logger with daily rotating file handler and console output."""
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)

    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)

    if not log.handlers:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=os.path.join(log_dir, f"{name}.log"),
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
        file_handler.suffix = "%Y-%m-%d"

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(levelname)-8s  %(message)s"))

        log.addHandler(file_handler)
        log.addHandler(console_handler)

    return log
