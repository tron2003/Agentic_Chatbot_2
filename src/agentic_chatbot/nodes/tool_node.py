from langchain_core.messages import SystemMessage, HumanMessage

from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.tools.web_tool import web_search
from agentic_chatbot.prompts.web_search_prompt import (
    WEB_SEARCH_SYSTEM_PROMPT,
)

llm = LLMLoader().load_llm()


def tool_node(state):
    print("\n========== TOOL NODE START ==========")

    question = state.messages[-1].content
    print(f"\n[1] Calling web_search for: {question}")

    result = web_search.invoke({"query": question})
    print(f"\n[2] Tool result preview: {str(result)[:500]}")

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

    print("\n[3] Sending grounded prompt to LLM...")

    final_response = llm.invoke(
        [
            SystemMessage(content=WEB_SEARCH_SYSTEM_PROMPT),
            HumanMessage(content=grounded_prompt),
        ]
    )

    print(f"\n[4] Final response: {str(final_response.content)[:500]}")
    print("========== TOOL NODE END ==========\n")

    return {"messages": [final_response]}
