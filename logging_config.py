import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            # Use record.created for accurate event time
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),

            # Useful operational context
            "process": record.process,
            "thread": record.threadName,
        }

        # Attach structured extra fields if present
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            base.update(extra)

        return json.dumps(base, separators=(",", ":"))

def setup_json_file_logger(app_name: str = "subscriber_app") -> logging.Logger:
    log_dir = Path(os.getenv("APP_LOG_DIR", "./logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(app_name)
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers (Flask reloader / gunicorn workers)
    if logger.handlers:
        return logger

    log_path = log_dir / "app.jsonl"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(JsonFormatter())

    logger.addHandler(handler)

    # Optional: stop logs propagating to root logger
    logger.propagate = False

    return logger

def new_request_id() -> str:
    return str(uuid.uuid4())
