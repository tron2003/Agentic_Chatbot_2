from langchain_core.messages import (
    SystemMessage
)

from agentic_chatbot.components.vector_store_loader import (
    VectorStoreLoader
)

from agentic_chatbot.components.reranker import (
    Reranker
)

from agentic_chatbot.components.llm_loader import (
    LLMLoader
)


vector_db = (

    VectorStoreLoader()
    .load_vectorstore()
)


reranker = (

    Reranker()
)


llm = (

    LLMLoader()
    .load_llm()
)


def rag_node(state):


    question = (

        state.messages[-1]
        .content
    )


    docs = (

        vector_db.similarity_search(

            question,

            k=10
        )
    )


    reranked_docs = (

        reranker.rerank(

            question,

            docs,

            top_k=3
        )
    )


    context = "\n".join(

        doc.page_content

        for doc

        in reranked_docs
    )


    print(
        "\nReranked Results:\n"
    )


    for i, doc in enumerate(

        reranked_docs,

        start=1
    ):

        print(
            f"\n{i}."
        )

        print(
            doc.page_content[:300]
        )


    messages = []


    messages.append(

        SystemMessage(

            content=f"""

Retrieved Context:

{context}

Answer using retrieved
context if available.

"""
        )
    )


    messages.extend(

        state.messages
    )


    response = (

        llm.invoke(
            messages
        )
    )


    return {

        "messages":[
            response
        ]
    }