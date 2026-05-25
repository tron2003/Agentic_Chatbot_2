from agentic_chatbot.components.llm_loader import (
    LLMLoader
)

from agentic_chatbot.entity.router import (
    Router
)


llm = (
    LLMLoader()
    .load_llm()
)


structured_llm = (
    llm.with_structured_output(
        Router
    )
)


def router_node(state):

    question = (

        state.messages[-1]
        .content
    )


    prompt = f"""
You are a routing classifier.

Return ONLY one route.

Routes:

chat:
- greetings
- casual conversation
- general knowledge answerable directly

rag:
- research papers
- uploaded PDFs
- documents
- "this paper"
- "attached file"
- information likely inside vector DB

memory:
- user preferences
- user facts
- previous conversations

tool:
- calculations
- APIs
- external tools

Question:

{question}
"""


    result = (

        structured_llm.invoke(
            prompt
        )
    )


    print(
        f"\nQuestion: {question}"
    )

    print(
        f"Route: {result.route}"
    )

    print(
        f"Reason: {result.reason}"
    )


    return {

        "route":
        result.route
    }