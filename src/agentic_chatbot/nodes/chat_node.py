from langchain_core.messages import SystemMessage
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.prompts.prompt import SYSTEM_PROMPT

llm = LLMLoader().load_llm()


async def chat_node(state):
    # Format the detailed system prompt with the summary (if it exists)
    summary_text = state.summary if state.summary else "No previous conversation summary."
    filled_prompt = SYSTEM_PROMPT.format(summary=summary_text)

    # The prompt now contains the instructions to remember facts + the summary context
    messages = [SystemMessage(content=filled_prompt)]

    # Append the recent conversation history
    messages.extend(state.messages[-10:])

    response = await llm.ainvoke(messages)

    return {"messages": [response]}

