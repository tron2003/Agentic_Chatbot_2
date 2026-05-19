import sys
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agentic_chatbot.logging.logger import logger
from src.agentic_chatbot.exception.exception import CustomException


logger.info("Chatbot Started")


try:

    x = 10/0

except Exception as e:

    logger.error(e)

    raise CustomException(
        e,
        sys
    )