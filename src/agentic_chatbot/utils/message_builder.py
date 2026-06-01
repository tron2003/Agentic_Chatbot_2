from langchain_core.messages import SystemMessage


def build_messages(state):

    messages = []

    if state.summary:

        messages.append(SystemMessage(content=f"""
Conversation Summary:

{state.summary}
"""))

    messages.extend(state.messages[-10:])

    return messages
