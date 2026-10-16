"""
ASGI entry point.

    uvicorn backend_api:app --port 8001          # development
    python run.py                                # production-style start

The application itself lives in ``src/agentic_chatbot/api/app.py``.
"""

import sys
from pathlib import Path

# Allow running from a source checkout without `pip install -e .`
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentic_chatbot.api.app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    import uvicorn

    from agentic_chatbot.core.settings import get_settings

    uvicorn.run("backend_api:app", host="0.0.0.0", port=8001, reload=not get_settings().is_production)
