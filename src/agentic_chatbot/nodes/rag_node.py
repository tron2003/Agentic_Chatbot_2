from langchain_core.messages import SystemMessage, HumanMessage
from agentic_chatbot.components.vector_store_loader import VectorStoreLoader
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.prompts.rag_prompt import RAG_PROMPT
from agentic_chatbot.utils.message_builder import build_messages

vector_db = VectorStoreLoader().load_vectorstore()
llm = LLMLoader().load_llm()


async def rag_node(state):
    question = state.messages[-1].content
    docs = vector_db.max_marginal_relevance_search(question, k=10, fetch_k=30)

    context = "\n".join(doc.page_content for doc in docs)

    filled_prompt = RAG_PROMPT.format(context=context)
    messages = build_messages(state)
    messages = [SystemMessage(content=filled_prompt), HumanMessage(content=question)]

    response = await llm.ainvoke(messages)
    return {"messages": [response]}
