from langchain_core.messages import SystemMessage, HumanMessage
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.prompts.router_prompt import SYSTEM_PROMPT
from agentic_chatbot.entity.router import Router

llm = LLMLoader().load_llm()

structured_llm = llm.with_structured_output(Router)

ROUTER_SYSTEM_PROMPT = f"""{SYSTEM_PROMPT}

ROUTING OPTIONS:
1. "chat" — Simple conversational response, general questions
2. "rag" — Query requires knowledge from ingested documents/knowledge base
3. "agent" — Complex multi-step tasks, requires tool use, research, verification

Choose "agent" for:
- Research tasks that need multiple tools/sources
- Complex problem-solving requiring step-by-step reasoning
- Tasks involving web search, file reading, or code analysis
- Verification tasks requiring multiple sources
- Any task needing transparency in reasoning steps"""


def router_node(state):
    try:
        question = state.messages[-1].content

        # Build context from recent conversation
        context_messages = [SystemMessage(content=ROUTER_SYSTEM_PROMPT)]

        # Include summary if available
        if state.summary:
            context_messages.append(
                SystemMessage(content=f"Conversation Summary:\n{state.summary}")
            )

        # Include last few messages for context
        recent = state.messages[-6:]
        context_messages.extend(recent)

        result = structured_llm.invoke(context_messages)

        print(f"\nQuestion: {question}")
        print(f"Route: {result.route}")
        print(f"Reason: {result.reason}")

        return {"route": result.route}

    except Exception as e:
        raise e

