from langchain_core.messages import SystemMessage
from agentic_chatbot.components.vector_store_loader import VectorStoreLoader
# from agentic_chatbot.components.reranker import Reranker
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.prompts.rag_prompt import RAG_PROMPT

vector_db = VectorStoreLoader().load_vectorstore()
# reranker = Reranker()
llm = LLMLoader().load_llm()


def rag_node(state):
    question = state.messages[-1].content
    docs = vector_db.max_marginal_relevance_search(question, k=10, fetch_k=30)

    # docs = vector_db.similarity_search(question, k=10)

    context = "\n".join(doc.page_content for doc in docs)  # fix 1: space

    # print("\nReranked Results:\n")
    # for i, doc in enumerate(reranked_docs, start=1):
    #     print(f"\n{i}.")
    #     print(doc.page_content[:300])

    filled_prompt = RAG_PROMPT.format(context=context)  # fix 3: inject context here

    messages = [SystemMessage(content=filled_prompt)]  # fix 2: correct variable name
    messages.extend(state.messages)

    response = llm.invoke(messages)
    return {"messages": [response]}
