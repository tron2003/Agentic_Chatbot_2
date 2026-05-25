from langchain_ollama import (
    OllamaEmbeddings
)


class EmbeddingLoader:

    def load_embeddings(self):

        return OllamaEmbeddings(

            model=
            "qwen3-embedding:4b",

            base_url=
            "http://127.0.0.1:11434"

        )