from langchain_core.messages import (
    HumanMessage,
    RemoveMessage
)

from agentic_chatbot.components.llm_loader import (
    LLMLoader
)


llm = (
    LLMLoader()
    .load_llm()
)


def summarize_conversation(state):

    existing_summary = state.summary


    recent_messages = (
        state.messages[-8:]
    )


    if existing_summary:

        prompt = f"""
        Existing summary:

        {existing_summary}

        Extend this summary with the
        new messages.
        """

    else:

        prompt = """
        Summarize the important
        information from this conversation.

        Keep:
        - user name
        - preferences
        - facts
        - important context
        """


    messages = (

        recent_messages +

        [

            HumanMessage(
                content=prompt
            )

        ]
    )


    response = llm.invoke(
        messages
    )


    messages_to_delete = (

        state.messages[:-4]

    )


    return {

        "summary":
        response.content,

        "messages":[

            RemoveMessage(
                id=m.id
            )

            for m in messages_to_delete
        ]
    }



def should_summarize(state):

    return len(
        state.messages
    ) > 8