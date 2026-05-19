import logging
import sys
from pathlib import Path
from datetime import datetime


LOG_DIR = Path("artifacts/logs")

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True
)

LOG_FILE = LOG_DIR / (
    f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.log"
)

LOG_FORMAT = (
    "[%(asctime)s] "
    "[%(levelname)s] "
    "[%(filename)s:%(lineno)d] "
    "%(message)s"
)


logger = logging.getLogger(
    "agentic_chatbot"
)

logger.setLevel(
    logging.INFO
)


if not logger.handlers:

    formatter = logging.Formatter(
        LOG_FORMAT
    )

    console_handler = logging.StreamHandler(
        sys.stdout
    )

    console_handler.setFormatter(
        formatter
    )

    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8"
    )

    file_handler.setFormatter(
        formatter
    )

    logger.addHandler(
        console_handler
    )

    logger.addHandler(
        file_handler
    )

logger.propagate = False