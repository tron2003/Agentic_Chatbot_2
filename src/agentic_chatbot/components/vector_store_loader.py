from langchain_postgres import (
    PGVector
)

from agentic_chatbot.components.embedding_loader import (
    EmbeddingLoader
)


class VectorStoreLoader:

    def load_vectorstore(self):

        embeddings = (

            EmbeddingLoader()

            .load_embeddings()
        )

        return PGVector(

            embeddings=
            embeddings,

            collection_name=
            "chatbot_docs",

            connection=
            "postgresql://postgres:postgres@localhost:5442/project_chatbot"
        )