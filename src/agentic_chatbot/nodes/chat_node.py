from langchain_core.messages import (
    SystemMessage
)

from agentic_chatbot.entity.chat_state import (
    Chatbot
)

from agentic_chatbot.components.llm_loader import (
    LLMLoader
)

from agentic_chatbot.nodes.rag_node import (
    rag_node
)

from agentic_chatbot.prompts.prompt import (
    SYSTEM_PROMPT
)


llm = (
    LLMLoader()
    .load_llm()
)


def chat_node(
    state: Chatbot
):

    messages=[]

    question=(
        state.messages[-1].content
    )

    retrieved_context=(

        rag_node(
            question
        )
    )

    # print(
    #     "\nRetrieved:\n",
    #     retrieved_context[:500]
    # )

    messages.append(

        SystemMessage(

            content=f"""

{SYSTEM_PROMPT}

Retrieved Context:

{retrieved_context}

Answer from retrieved
context when available.
"""
        )
    )

    messages.extend(
        state.messages
    )

    response=llm.invoke(
        messages
    )

    return {

        "messages":[
            response
        ]
    }