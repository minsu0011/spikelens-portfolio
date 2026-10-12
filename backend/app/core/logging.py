import json
import logging
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        message = record.getMessage()
        try:
            payload = json.loads(message)
            if not isinstance(payload, dict):
                payload = {"message": message}
        except (ValueError, TypeError):
            payload = {"message": message}
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                **payload,
            }
        )


def configure_logger():
    logger = logging.getLogger("spikelens")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    return logger
