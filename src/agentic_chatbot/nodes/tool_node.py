from langchain_core.messages import SystemMessage, HumanMessage

from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.tools.web_tool import web_search
from agentic_chatbot.prompts.web_search_prompt import (
    WEB_SEARCH_SYSTEM_PROMPT,
)
from agentic_chatbot.utils.message_builder import build_messages

llm = LLMLoader().load_llm()


def tool_node(state):
    messages = build_messages(state)

    question = state.messages[-1].content

    result = web_search.invoke({"query": question})

    if not result or result == "No results found.":
        print("[!] WARNING: web_search returned no results")

        final_response = llm.invoke([HumanMessage(content=f"""
I searched the web for:

{question}

No relevant results were found.

Politely inform the user.
""")])

        return {"messages": [final_response]}

    grounded_prompt = f"""
Question:
{question}

=== WEB SEARCH RESULTS ===
{result}
=== END OF RESULTS ===

Answer the question using ONLY the web search results above.
"""
    messages.append(SystemMessage(content=WEB_SEARCH_SYSTEM_PROMPT))
    messages.append(HumanMessage(content=grounded_prompt))
    final_response = llm.invoke(messages)

    return {"messages": [final_response]}
