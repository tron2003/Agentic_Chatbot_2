from langchain_community.document_loaders import (
    PyPDFLoader
)

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter
)


class DocumentLoader:

    def load_documents(

        self,

        file_path
    ):

        loader = (

            PyPDFLoader(
                file_path
            )
        )

        docs = loader.load()

        splitter = (

            RecursiveCharacterTextSplitter(

                chunk_size=800,

                chunk_overlap=200
            )
        )

        split_docs = (

            splitter.split_documents(
                docs
            )
        )

        return split_docs