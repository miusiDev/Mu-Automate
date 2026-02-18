"""Logging setup with rotating file handler and colored console output."""

import logging
import os
from logging.handlers import RotatingFileHandler

import colorlog


def setup_logger(
    name: str = "mu_supervisor",
    log_dir: str = "logs",
    level: str = "INFO",
    file_max_bytes: int = 5_242_880,
    file_backup_count: int = 3,
) -> logging.Logger:
    """Configure and return a logger with file rotation and colored console output."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Rotating file handler
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{name}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=file_max_bytes,
        backupCount=file_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    logger.addHandler(file_handler)

    # Colored console handler
    color_format = (
        "%(log_color)s%(asctime)s | %(levelname)-8s%(reset)s | %(name)s | %(message)s"
    )
    console_handler = colorlog.StreamHandler()
    console_handler.setFormatter(
        colorlog.ColoredFormatter(
            color_format,
            datefmt=date_format,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
    )
    logger.addHandler(console_handler)

    return logger
