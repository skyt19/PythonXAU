"""
Logging Configuration
Structured logging setup with file rotation and credential redaction.
"""
import logging
import logging.handlers
import re
import sys
from pathlib import Path
from typing import Any, Dict

import structlog


class CredentialRedactingFormatter(logging.Formatter):
    """Formatter that redacts credentials from log messages."""

    PATTERNS = [
        (re.compile(r"password['\"]?\s*[:=]\s*['\"]?([^'\"}\s,]+)", re.I), "password=***REDACTED***"),
        (re.compile(r"login['\"]?\s*[:=]\s*['\"]?(\d+)", re.I), "login=***REDACTED***"),
        (re.compile(r"MT5_PASSWORD['\"]?\s*[:=]\s*['\"]?([^'\"}\s,]+)", re.I), "MT5_PASSWORD=***REDACTED***"),
        (re.compile(r"MT5_LOGIN['\"]?\s*[:=]\s*['\"]?(\d+)", re.I), "MT5_LOGIN=***REDACTED***"),
        (re.compile(r"(server|host|port)['\"]?\s*[:=]\s*['\"]?([^'\"}\s,]+)", re.I), lambda m: f"{m.group(1)}={m.group(2)[:4]}***"),
    ]

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with credential redaction."""
        # Redact credentials from message
        msg = record.getMessage()
        for pattern, replacement in self.PATTERNS:
            if callable(replacement):
                msg = pattern.sub(replacement, msg)
            else:
                msg = pattern.sub(replacement, msg)
        record.msg = msg
        record.args = ()
        return super().format(record)


def add_app_context(
    logger: logging.Logger, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Add application context to log events."""
    event_dict["app"] = "farming_hq"
    event_dict["environment"] = "production"  # Could be env-dependent
    return event_dict


def setup_logging(log_level: str = "INFO", log_file: Path = Path("logs/farming_hq.log")) -> None:
    """
    Setup structured logging with file rotation and credential redaction.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file
    """
    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            add_app_context,
            structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    # Configure standard logging
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.getLevelName(log_level))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler (with colors in terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.getLevelName(log_level))
    console_formatter = CredentialRedactingFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler (with rotation)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # Always log everything to file
    file_formatter = CredentialRedactingFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Log startup
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level={log_level}, file={log_file}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


# Convenience function for structured logging
def get_structlog() -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger()
