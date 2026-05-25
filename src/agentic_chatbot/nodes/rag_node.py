from agentic_chatbot.components.vector_store_loader import (
    VectorStoreLoader
)

vector_db = (
    VectorStoreLoader()
    .load_vectorstore()
)


def rag_node(question):

    docs = (

        vector_db.similarity_search(

            question,

            k=5
        )
    )

    context = "\n".join(

        doc.page_content

        for doc in docs
    )

    # print(
    #     "\nRetrieved Context:\n"
    # )

    # print(
    #     context[:1000]
    # )

    return context