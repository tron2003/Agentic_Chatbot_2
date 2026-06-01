from agentic_chatbot.components.llm_loader import LLMLoader

llm = LLMLoader().load_llm()


def chat_node(state):

    response = llm.invoke(state.messages)

    return {"messages": [response]}
