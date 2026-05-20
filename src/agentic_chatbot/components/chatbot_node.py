from langchain_core.messages import (
    SystemMessage
)
from agentic_chatbot.entity.chat_state import Chatbot

from agentic_chatbot.components.llm_loader import (
    LLMLoader
)


llm = (
    LLMLoader()
    .load_llm()
)


def chat_node(state:Chatbot):

    messages = []

    if state.summary:

        messages.append(

            SystemMessage(
                content=f"""
You are a personal AI assistant.

Conversation summary:
{state.summary}

Rules:
1. Use previous conversation history.
2. Remember user facts.
3. Remember preferences:
   - name
   - favorite game
   - favorite movie
   - hobbies
4. If information exists in memory,
   answer directly.
5. Do not say "I don't know"
   if the information exists.
"""
            )
        )


    messages.extend(
        state.messages
    )


    response = llm.invoke(
        messages
    )


    return {

        "messages":[
            response
        ]
    }