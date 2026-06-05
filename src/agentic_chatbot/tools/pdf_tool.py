from langchain_core.tools import tool
from pypdf import PdfReader


@tool
def read_pdf(file_path: str) -> str:
    """Extract and return all text content from a PDF file given its absolute file path."""
    try:
        reader = PdfReader(file_path)
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages).strip()
        if not text:
            return "The PDF appears to be scanned or image-only — no extractable text found."
        return text
    except FileNotFoundError:
        return f"File not found: {file_path}"
    except Exception as e:
        return f"Failed to read PDF: {e}"
