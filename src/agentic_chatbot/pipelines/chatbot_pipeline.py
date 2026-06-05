from langgraph.graph import (
    StateGraph,
    START,
    END,
)

from agentic_chatbot.entity.chat_state import (
    Chatbot,
)

from agentic_chatbot.nodes.router_node import (
    router_node,
)

from agentic_chatbot.nodes.chat_node import (
    chat_node,
)

from agentic_chatbot.nodes.rag_node import (
    rag_node,
)

from agentic_chatbot.nodes.tool_node import (
    tool_node,
)

from agentic_chatbot.utils.summarizer import (
    summarize_conversation,
    should_summarize,
)



class ChatbotPipeline:

    def __init__(self, checkpointer=None):

        graph = StateGraph(Chatbot)

        graph.add_node(
            "router",
            router_node,
        )

        graph.add_node(
            "chat",
            chat_node,
        )

        graph.add_node(
            "rag",
            rag_node,
        )

        graph.add_node(
            "tool_node",
            tool_node,
        )

        graph.add_node(
            "summarize",
            summarize_conversation,
        )

        graph.add_edge(
            START,
            "router",
        )

        def route_decision(state):
            return state.route

        graph.add_conditional_edges(
            "router",
            route_decision,
            {
                "chat": "chat",
                "rag": "rag",
                "tool": "tool_node",
            },
        )

        graph.add_conditional_edges(
            "chat",
            lambda state:
            "summarize"
            if should_summarize(state)
            else END,
            {
                "summarize": "summarize",
                END: END,
            },
        )

        graph.add_conditional_edges(
            "rag",
            lambda state:
            "summarize"
            if should_summarize(state)
            else END,
            {
                "summarize": "summarize",
                END: END,
            },
        )

        graph.add_conditional_edges(
            "tool_node",
            lambda state:
            "summarize"
            if should_summarize(state)
            else END,
            {
                "summarize": "summarize",
                END: END,
            },
        )

        graph.add_edge(
            "summarize",
            END,
        )

        self.workflow = graph.compile(checkpointer=checkpointer)

    async def run(
        self,
        message,
        thread_id="rag_singh",
    ):

        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }

        # Use async invoke to handle async nodes
        result = await self.workflow.ainvoke(
            {
                "messages": [message]
            },
            config=config,
        )

        return result