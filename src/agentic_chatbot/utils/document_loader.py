from pathlib import Path

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
)

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
)


# Extensions treated as plain text
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".py", ".js", ".ts",
    ".jsx", ".tsx", ".html", ".css", ".xml", ".yaml", ".yml",
    ".toml", ".log", ".sql", ".sh", ".bat", ".cfg", ".ini",
    ".env", ".gitignore", ".editorconfig", ".rst", ".r", ".go",
    ".java", ".c", ".cpp", ".h", ".hpp", ".rb", ".php",
}

PDF_EXTENSIONS = {".pdf"}


class DocumentLoader:

    @staticmethod
    def _get_loader(file_path: str):
        """Return the appropriate LangChain loader based on file extension."""
        ext = Path(file_path).suffix.lower()

        if ext in PDF_EXTENSIONS:
            return PyPDFLoader(file_path)
        elif ext in TEXT_EXTENSIONS:
            return TextLoader(file_path, encoding="utf-8")
        else:
            # Fallback: try reading as text
            return TextLoader(file_path, encoding="utf-8")

    @staticmethod
    def supported_extensions():
        """Return all supported file extensions."""
        return PDF_EXTENSIONS | TEXT_EXTENSIONS

    def load_documents(self, file_path):
        loader = self._get_loader(file_path)
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=200,
        )

        split_docs = splitter.split_documents(docs)
        return split_docs