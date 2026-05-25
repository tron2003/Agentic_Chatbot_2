from langchain_core.messages import (
    SystemMessage
)

from agentic_chatbot.entity.chat_state import (
    Chatbot
)

from agentic_chatbot.components.llm_loader import (
    LLMLoader
)

from agentic_chatbot.prompts.prompt import (
    SYSTEM_PROMPT
)


llm = (
    LLMLoader()
    .load_llm()
)


def chat_node(state: Chatbot):

    messages = []

    system_prompt = SYSTEM_PROMPT.format(
        summary=state.summary or "No previous summary available."
    )

    messages.append(

        SystemMessage(
            content=system_prompt
        )

    )

    messages.extend(
        state.messages
    )

    response = llm.invoke(
        messages
    )

    return {

        "messages": [
            response
        ]
    }