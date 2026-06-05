from langchain_core.messages import (
    SystemMessage,
)

from agentic_chatbot.components.llm_loader import (
    LLMLoader,
)

llm = LLMLoader().load_llm()


def chat_node(state):

    messages = []

    if state.summary:

        messages.append(SystemMessage(content=f"""
Conversation Summary:

{state.summary}

The summary contains older conversation
context and important user information.

Use it when answering.
"""))

    messages.extend(state.messages[-10:])

    response = llm.invoke(messages)

    return {"messages": [response]}
