"""Load and chunk files for the knowledge base."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".log", ".sql", ".html", ".htm", ".css",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".sh", ".bat", ".ps1", ".r", ".kt", ".swift", ".scala",
}
PDF_EXTENSIONS = {".pdf"}
EXCEL_EXTENSIONS = {".xlsx", ".xlsm"}  # needs openpyxl; old binary .xls isn't supported
WORD_EXTENSIONS = {".docx"}  # needs python-docx; old binary .doc isn't supported
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | EXCEL_EXTENSIONS | WORD_EXTENSIONS


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.10g}"
    if hasattr(value, "isoformat"):
        return value.isoformat()  # dates and times
    return str(value).strip()


def _load_excel(path: Path) -> list[Document]:
    """One document per sheet; each row as `a | b | c`, with computed values rather than formulas."""
    import warnings

    with warnings.catch_warnings():
        # openpyxl warns about unsupported extras ("Data Validation extension is not
        # supported"); they don't affect the cell values, so keep the logs quiet.
        warnings.simplefilter("ignore", UserWarning)
        return _read_excel(path)


def _read_excel(path: Path) -> list[Document]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    docs = []
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                cells = [_cell_text(v) for v in row]
                while cells and not cells[-1]:
                    cells.pop()
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                docs.append(Document(page_content=f"Sheet: {sheet.title}\n" + "\n".join(rows), metadata={"sheet": sheet.title}))
    finally:
        workbook.close()
    return docs


def _load_word(path: Path) -> list[Document]:
    """Paragraphs in order, then each table with rows as `a | b | c`."""
    import docx

    document = docx.Document(str(path))
    parts = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    text = "\n".join(parts)
    return [Document(page_content=text, metadata={})] if text else []


def safe_filename(name: str, max_length: int = 120) -> str:
    """Strip directories and unsafe characters from an uploaded filename.

    ``../../etc/passwd`` -> ``passwd``; ``my report (v2).pdf`` -> ``my report (v2).pdf``.
    """
    name = unicodedata.normalize("NFKC", name or "")
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ()\[\]]+", "_", name).strip(" .")
    if not name:
        name = "upload"
    stem, dot, ext = name.rpartition(".")
    if dot and len(ext) <= 10:
        return f"{stem[: max_length - len(ext) - 1]}.{ext}"
    return name[:max_length]


class DocumentLoader:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150):
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    @staticmethod
    def supported_extensions() -> set[str]:
        return SUPPORTED_EXTENSIONS

    @staticmethod
    def is_supported(filename: str) -> bool:
        return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS

    def _load(self, path: Path) -> list[Document]:
        ext = path.suffix.lower()
        if ext in PDF_EXTENSIONS:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            docs = []
            for i, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    docs.append(Document(page_content=text, metadata={"page": i}))
            return docs
        if ext in EXCEL_EXTENSIONS:
            return _load_excel(path)
        if ext in WORD_EXTENSIONS:
            return _load_word(path)
        raw = path.read_bytes()
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if "\x00" in text[:2000]:
            return []  # binary file with a text-looking extension
        return [Document(page_content=text, metadata={})] if text.strip() else []

    def load_documents(self, file_path: str | Path) -> list[Document]:
        path = Path(file_path)
        return self.splitter.split_documents(self._load(path))
