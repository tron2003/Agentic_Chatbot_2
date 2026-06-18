import sys
import logging
from langchain_core.messages import SystemMessage
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.prompts.prompt import SYSTEM_PROMPT
from agentic_chatbot.exception.exception import LLMException
from agentic_chatbot.logging.logging_utils import (
    ExecutionTimer,
    get_correlation_id,
    log_async,
)

logger = logging.getLogger(__name__)

llm = LLMLoader().load_llm()


@log_async()
async def chat_node(state):
    """
    Simple chat node for conversational responses.
    Formats system prompt with conversation summary and invokes LLM.
    """
    correlation_id = get_correlation_id()

    with ExecutionTimer("chat_node", correlation_id, logger):
        try:
            logger.debug(
                "Starting chat node processing",
                extra={"correlation_id": correlation_id},
            )

            # Format the detailed system prompt with the summary (if it exists)
            summary_text = (
                state.summary if state.summary else "No previous conversation summary."
            )
            filled_prompt = SYSTEM_PROMPT.format(summary=summary_text)

            # The prompt now contains the instructions to remember facts + the summary context
            messages = [SystemMessage(content=filled_prompt)]

            # Append the recent conversation history
            recent_messages = state.messages[-10:]
            messages.extend(recent_messages)

            logger.debug(
                f"Chat node context prepared with {len(messages)} messages",
                extra={"correlation_id": correlation_id},
            )

            response = await llm.ainvoke(messages)

            logger.info(
                "Chat response generated successfully",
                extra={
                    "correlation_id": correlation_id,
                    "response_length": (
                        len(response.content) if hasattr(response, "content") else 0
                    ),
                },
            )

            return {"messages": [response]}

        except LLMException:
            raise
        except Exception as e:
            logger.error(
                f"Chat node failed: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                f"Failed to generate chat response: {str(e)}",
                sys,
                correlation_id=correlation_id,
            )
