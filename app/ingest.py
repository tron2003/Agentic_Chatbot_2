from pathlib import Path

from agentic_chatbot.utils.document_loader import (
    DocumentLoader
)

from agentic_chatbot.components.vector_store_loader import (
    VectorStoreLoader
)


PDF_FOLDER = (
    "ingest"
)


document_loader = (
    DocumentLoader()
)

vector_db = (
    VectorStoreLoader()
    .load_vectorstore()
)


all_docs = []


pdf_files = (

    Path(
        PDF_FOLDER
    )

    .glob(
        "*.pdf"
    )
)


for pdf in pdf_files:

    print(
        f"Loading: {pdf.name}"
    )

    docs = (

        document_loader
        .load_documents(
            str(pdf)
        )
    )

    all_docs.extend(
        docs
    )


if all_docs:

    vector_db.add_documents(
        all_docs
    )

    print(

        f"\nAdded {len(all_docs)} chunks"
    )

else:

    print(
        "\nNo PDF files found"
    )