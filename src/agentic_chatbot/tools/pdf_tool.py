"""Read a PDF from the workspace folder.

Paths are confined to ``WORKSPACE_DIR`` so a prompt can't make the agent read
arbitrary files on the server (e.g. ``/etc/passwd`` or ``.env``).
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from agentic_chatbot.core.settings import get_settings

MAX_CHARS = 40_000


def resolve_in_workspace(file_path: str) -> Path | None:
    root = get_settings().workspace_dir.resolve()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None
    return resolved if resolved.is_relative_to(root) else None


@tool
def read_pdf(file_path: str) -> str:
    """Extract the text of a PDF stored in the workspace folder. Pass a path relative to the workspace, e.g. "reports/q3.pdf"."""
    path = resolve_in_workspace(file_path)
    if path is None:
        return "Access denied: only files inside the workspace folder can be read."
    if not path.exists():
        return f"File not found in workspace: {file_path}"
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [f"[Page {i}]\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages, start=1)]
        text = "\n\n".join(pages).strip()
    except Exception as exc:
        return f"Failed to read PDF: {exc}"
    if not text:
        return "The PDF has no extractable text (it may be scanned)."
    return text[:MAX_CHARS] + ("\n\n[truncated]" if len(text) > MAX_CHARS else "")
