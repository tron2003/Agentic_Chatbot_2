from langchain_core.messages import (
    HumanMessage,
    RemoveMessage,
)

from agentic_chatbot.components.llm_loader import (
    LLMLoader,
)

llm = LLMLoader().load_llm()

KEEP_LAST_MESSAGES = 10


def summarize_conversation(state):

    existing_summary = state.summary or ""

    recent_messages = state.messages[-KEEP_LAST_MESSAGES:]

    if existing_summary:

        prompt = f"""
Existing conversation summary:

{existing_summary}

Update the summary using the recent conversation.

Preserve:
- User identity
- User preferences
- Important facts
- Ongoing projects
- Technical decisions
- Goals

Remove:
- Greetings
- Repeated information
- Temporary discussions

Return only the updated summary.
"""

    else:

        prompt = """
Create a conversation summary.

Keep:
- User name
- Preferences
- Important facts
- Ongoing projects
- Technical stack
- Goals
- Long-term context

Ignore:
- Greetings
- Small talk
- Temporary questions

Return only the summary.
"""

    response = llm.invoke(
        recent_messages
        + [
            HumanMessage(content=prompt)
        ]
    )

    messages_to_delete = state.messages[:-KEEP_LAST_MESSAGES]

    return {
        "summary": response.content,
        "messages": [
            RemoveMessage(id=m.id)
            for m in messages_to_delete
        ],
    }


def should_summarize(state):

    return len(state.messages) > 20