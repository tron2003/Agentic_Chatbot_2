import sys
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.prompts.router_prompt import SYSTEM_PROMPT
from agentic_chatbot.entity.router import Router
from agentic_chatbot.exception.exception import LLMException
from agentic_chatbot.logging.logging_utils import ExecutionTimer, get_correlation_id

logger = logging.getLogger(__name__)

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
    """
    Route incoming query to appropriate handler (chat, rag, or agent).
    """
    correlation_id = get_correlation_id()

    with ExecutionTimer("router_node", correlation_id, logger):
        try:
            if not state.messages:
                logger.error(
                    "No messages in state", extra={"correlation_id": correlation_id}
                )
                raise LLMException(
                    "No messages provided for routing",
                    sys,
                    correlation_id=correlation_id,
                    error_code="NO_MESSAGES_ERROR",
                )

            question = state.messages[-1].content
            logger.debug(
                f"Routing query: {question[:100]}...",
                extra={"correlation_id": correlation_id},
            )

            # Build context from recent conversation
            context_messages = [SystemMessage(content=ROUTER_SYSTEM_PROMPT)]

            # Include summary if available
            if state.summary:
                logger.debug(
                    "Including conversation summary in routing context",
                    extra={"correlation_id": correlation_id},
                )
                context_messages.append(
                    SystemMessage(content=f"Conversation Summary:\n{state.summary}")
                )

            # Include last few messages for context
            recent = state.messages[-6:]
            context_messages.extend(recent)

            logger.debug(
                f"Router context prepared with {len(context_messages)} messages",
                extra={"correlation_id": correlation_id},
            )

            result = structured_llm.invoke(context_messages)

            logger.info(
                f"Route decision: {result.route}",
                extra={
                    "correlation_id": correlation_id,
                    "route": result.route,
                    "reason": result.reason,
                },
            )

            print(f"\nQuestion: {question}")
            print(f"Route: {result.route}")
            print(f"Reason: {result.reason}")

            return {"route": result.route}

        except LLMException:
            raise
        except Exception as e:
            logger.error(
                f"Router node failed: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                f"Failed to route query: {str(e)}", sys, correlation_id=correlation_id
            )
