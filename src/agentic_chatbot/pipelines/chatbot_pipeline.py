from langgraph.graph import StateGraph, START, END

from agentic_chatbot.nodes.tool_node import tool_node
from agentic_chatbot.entity.chat_state import Chatbot

from agentic_chatbot.nodes.router_node import router_node

from agentic_chatbot.nodes.chat_node import chat_node

from agentic_chatbot.nodes.rag_node import rag_node


from agentic_chatbot.utils.summarizer import summarize_conversation

from agentic_chatbot.components.memory import MemoryLoader


class ChatbotPipeline:

    def __init__(self):

        graph = StateGraph(Chatbot)

        graph.add_node("router", router_node)

        graph.add_node("chat", chat_node)

        graph.add_node("rag", rag_node)

        graph.add_node("tool_node", tool_node)
        graph.add_node("summarize", summarize_conversation)

        graph.add_edge(START, "router")

        def route_decision(state):

            return state.route

        graph.add_conditional_edges(
            "router",
            route_decision,
            {"chat": "chat", "rag": "rag", "tool": "tool_node"},
        )
        graph.add_edge("chat", END)
        graph.add_edge("tool_node", END)

        graph.add_edge("rag", END)

        self.memory_context = MemoryLoader().load_memory()

        self.memory = self.memory_context.__enter__()

        self.memory.setup()

        self.workflow = graph.compile(checkpointer=self.memory)

    def run(self, message, thread_id="rag_singh"):

        config = {"configurable": {"thread_id": thread_id}}

        result = self.workflow.invoke({"messages": [message]}, config=config)
        # print(self.workflow.get_graph().draw_mermaid())

        return result
