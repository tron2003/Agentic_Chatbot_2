from langchain_core.messages import SystemMessage, HumanMessage
from agentic_chatbot.exception.exception import CustomException
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.prompts.router_prompt import SYSTEM_PROMPT
from agentic_chatbot.entity.router import Router

llm = LLMLoader().load_llm()

structured_llm = llm.with_structured_output(Router)


def router_node(state):
    try:

        question = state.messages[-1].content

        result = structured_llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)]
        )

        print(f"\nQuestion: {question}")
        print(f"Route: {result.route}")
        print(f"Reason: {result.reason}")

        return {"route": result.route}

    except Exception as e:
        CustomException(e)
        raise e
